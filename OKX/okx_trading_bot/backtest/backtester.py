import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from ..utils.logger import setup_logger


class Backtester:
    """回测引擎"""

    def __init__(self, config: Dict):
        self.config = config
        self.logger = setup_logger("Backtester")

        # 回测参数
        self.initial_capital = config.get('initial_capital', 10000)
        self.commission_rate = config.get('commission_rate', 0.0005)

        # 回测结果
        self.balance = self.initial_capital
        self.equity_curve = []
        self.trades = []
        self.positions = []
        self.current_position = None

    def load_historical_data(self, api_client, inst_id: str, bar: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        加载历史K线数据

        Args:
            api_client: API客户端
            inst_id: 产品ID
            bar: K线周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            K线数据DataFrame
        """
        try:
            self.logger.info(f"加载历史数据: {inst_id}, {bar}, {start_date} - {end_date}")

            # 调用API获取历史数据
            result = api_client.get_candles(inst_id, bar, limit=300)

            if result['code'] == '0' and result['data']:
                # 转换为DataFrame
                df = pd.DataFrame(result['data'], columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'
                ])

                # 数据类型转换
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['open'] = df['open'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)

                # 按时间排序
                df = df.sort_values('timestamp')
                df = df.reset_index(drop=True)

                self.logger.info(f"加载了 {len(df)} 条K线数据")
                return df
            else:
                self.logger.error(f"加载数据失败: {result.get('msg', 'Unknown error')}")
                return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"加载历史数据异常: {e}")
            return pd.DataFrame()

    def simulate_grid_strategy(self, df: pd.DataFrame, grid_config: Dict) -> Dict:
        """
        模拟网格交易策略

        Args:
            df: K线数据
            grid_config: 网格配置

        Returns:
            回测结果
        """
        self.logger.info("开始回测网格策略...")

        # 重置回测状态
        self.balance = self.initial_capital
        self.equity_curve = []
        self.trades = []
        self.positions = []
        self.current_position = None

        # 获取网格参数
        price_upper = grid_config.get('price_upper')
        price_lower = grid_config.get('price_lower')
        grid_num = grid_config.get('grid_num')
        investment = grid_config.get('investment', self.initial_capital)

        # 计算网格档位
        grid_levels = np.linspace(price_lower, price_upper, grid_num)

        # 初始化网格状态
        grid_positions = {}  # 记录每个网格的持仓
        pending_buy_orders = {}  # 待执行的买单
        pending_sell_orders = {}  # 待执行的卖单

        # 计算每个网格的投资金额
        per_grid_investment = investment / grid_num

        # 遍历K线数据
        for idx, row in df.iterrows():
            timestamp = row['timestamp']
            open_price = row['open']
            high_price = row['high']
            low_price = row['low']
            close_price = row['close']

            # 检查挂单是否成交
            for i, grid_price in enumerate(grid_levels):
                # 检查买单
                if i not in grid_positions and low_price <= grid_price:
                    # 买入成交
                    size = per_grid_investment / grid_price
                    commission = size * grid_price * self.commission_rate
                    cost = size * grid_price + commission

                    if self.balance >= cost:
                        self.balance -= cost
                        grid_positions[i] = {
                            'price': grid_price,
                            'size': size,
                            'side': 'buy'
                        }

                        self.trades.append({
                            'timestamp': timestamp,
                            'side': 'buy',
                            'price': grid_price,
                            'size': size,
                            'commission': commission,
                            'balance': self.balance
                        })

                        self.logger.debug(f"{timestamp} - 买入成交: 档位{i}, 价格{grid_price:.2f}, 数量{size:.6f}")

                # 检查卖单
                elif i in grid_positions and high_price >= grid_levels[min(i + 1, len(grid_levels) - 1)]:
                    # 卖出成交
                    position = grid_positions[i]
                    sell_price = grid_levels[min(i + 1, len(grid_levels) - 1)]
                    size = position['size']
                    commission = size * sell_price * self.commission_rate
                    revenue = size * sell_price - commission

                    self.balance += revenue
                    profit = revenue - (position['price'] * size)

                    self.trades.append({
                        'timestamp': timestamp,
                        'side': 'sell',
                        'price': sell_price,
                        'size': size,
                        'commission': commission,
                        'profit': profit,
                        'balance': self.balance
                    })

                    del grid_positions[i]

                    self.logger.debug(f"{timestamp} - 卖出成交: 档位{i}, 价格{sell_price:.2f}, 数量{size:.6f}, 利润{profit:.2f}")

            # 计算当前总权益
            position_value = sum(pos['price'] * pos['size'] for pos in grid_positions.values())
            total_equity = self.balance + position_value

            self.equity_curve.append({
                'timestamp': timestamp,
                'balance': self.balance,
                'position_value': position_value,
                'total_equity': total_equity
            })

        # 计算回测指标
        results = self._calculate_metrics()

        self.logger.info("回测完成")
        return results

    def _calculate_metrics(self) -> Dict:
        """计算回测指标"""
        if not self.equity_curve:
            return {}

        # 转换为DataFrame
        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        # 最终权益
        final_equity = equity_df['total_equity'].iloc[-1]

        # 总收益和收益率
        total_profit = final_equity - self.initial_capital
        total_return = (final_equity - self.initial_capital) / self.initial_capital

        # 交易次数
        total_trades = len(self.trades)
        buy_trades = len([t for t in self.trades if t['side'] == 'buy'])
        sell_trades = len([t for t in self.trades if t['side'] == 'sell'])

        # 盈利交易统计
        profitable_trades = [t for t in self.trades if t.get('profit', 0) > 0]
        losing_trades = [t for t in self.trades if t.get('profit', 0) < 0]

        win_rate = len(profitable_trades) / sell_trades if sell_trades > 0 else 0
        avg_profit = np.mean([t['profit'] for t in profitable_trades]) if profitable_trades else 0
        avg_loss = np.mean([t['profit'] for t in losing_trades]) if losing_trades else 0

        # 最大回撤
        equity_df['peak'] = equity_df['total_equity'].cummax()
        equity_df['drawdown'] = (equity_df['peak'] - equity_df['total_equity']) / equity_df['peak']
        max_drawdown = equity_df['drawdown'].max()

        # 夏普比率（简化计算）
        if len(equity_df) > 1:
            returns = equity_df['total_equity'].pct_change().dropna()
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0

        return {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'total_profit': total_profit,
            'total_return': total_return,
            'total_trades': total_trades,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'equity_curve': equity_df
        }

    def print_results(self, results: Dict):
        """打印回测结果"""
        self.logger.info("=" * 60)
        self.logger.info("回测结果:")
        self.logger.info("=" * 60)
        self.logger.info(f"初始资金: {results['initial_capital']:.2f} USDT")
        self.logger.info(f"最终权益: {results['final_equity']:.2f} USDT")
        self.logger.info(f"总盈亏: {results['total_profit']:.2f} USDT")
        self.logger.info(f"收益率: {results['total_return']:.2%}")
        self.logger.info(f"总交易次数: {results['total_trades']}")
        self.logger.info(f"买入次数: {results['buy_trades']}")
        self.logger.info(f"卖出次数: {results['sell_trades']}")
        self.logger.info(f"胜率: {results['win_rate']:.2%}")
        self.logger.info(f"平均盈利: {results['avg_profit']:.2f} USDT")
        self.logger.info(f"平均亏损: {results['avg_loss']:.2f} USDT")
        self.logger.info(f"最大回撤: {results['max_drawdown']:.2%}")
        self.logger.info(f"夏普比率: {results['sharpe_ratio']:.2f}")
        self.logger.info("=" * 60)

    def export_results(self, results: Dict, filename: str = "backtest_results.csv"):
        """导出回测结果"""
        try:
            equity_df = results.get('equity_curve')
            if equity_df is not None and not equity_df.empty:
                equity_df.to_csv(filename, index=False)
                self.logger.info(f"回测结果已导出到: {filename}")
        except Exception as e:
            self.logger.error(f"导出结果失败: {e}")
