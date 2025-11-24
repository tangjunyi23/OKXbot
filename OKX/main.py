"""
OKX 量化交易机器人 - 主程序

使用方法:
1. 修改 okx_trading_bot/config/config.yaml 中的配置
2. 运行: python main.py --mode [live/backtest/test]
"""

import sys
import time
import signal
import argparse
from datetime import datetime

from okx_trading_bot.config import Config
from okx_trading_bot.api import OKXClient, OKXWebSocket
from okx_trading_bot.strategies import GridStrategy, PositionStrategy, SmartProfitStrategy, AdvancedStrategy, EnhancedStrategy
from okx_trading_bot.risk_manager import RiskManager
from okx_trading_bot.backtest import Backtester
from okx_trading_bot.utils import setup_logger


class TradingBot:
    """交易机器人主类"""

    def __init__(self, config_path: str = None):
        # 加载配置
        self.config = Config(config_path)
        self.logger = setup_logger("TradingBot",
                                   self.config.get('notification.log_file', 'logs/trading_bot.log'),
                                   self.config.get('notification.log_level', 'INFO'))

        # 初始化API客户端
        okx_config = self.config.get_okx_config()
        self.api_client = OKXClient(
            api_key=okx_config['api_key'],
            secret_key=okx_config['secret_key'],
            passphrase=okx_config['passphrase'],
            is_simulated=okx_config.get('is_simulated', True),
            proxy=okx_config.get('proxy')
        )

        # WebSocket客户端
        self.ws_client = None

        # 初始化策略
        strategy_type = self.config.get('trading.strategy_type', 'position')  # 默认使用position策略
        trading_config = self.config.get_trading_config()

        if strategy_type == 'grid':
            # 网格策略
            strategy_config = {
                **trading_config,
                **self.config.get_grid_config()
            }
            self.strategy = GridStrategy(strategy_config, self.api_client)
        elif strategy_type == 'smart':
            # 智能利润最大化策略
            strategy_config = {
                **trading_config,
                'position_size': self.config.get('smart_strategy.position_size', 0.1),
                'base_stop_loss': self.config.get('smart_strategy.base_stop_loss', 0.02),
                'base_take_profit': self.config.get('smart_strategy.base_take_profit', 0.045),
                'trailing_stop_trigger': self.config.get('smart_strategy.trailing_stop_trigger', 0.02),
                'trailing_stop_distance': self.config.get('smart_strategy.trailing_stop_distance', 0.01),
                'ma_short_period': self.config.get('smart_strategy.ma_short_period', 5),
                'ma_long_period': self.config.get('smart_strategy.ma_long_period', 15),
                'rsi_period': self.config.get('smart_strategy.rsi_period', 14),
                'min_signal_strength': self.config.get('smart_strategy.min_signal_strength', 60),
                'volatility_window': self.config.get('smart_strategy.volatility_window', 20),
                'time_filter_enabled': self.config.get('smart_strategy.time_filter_enabled', True)
            }
            self.strategy = SmartProfitStrategy(strategy_config, self.api_client)
        elif strategy_type == 'advanced':
            # 高级利润最大化策略
            strategy_config = {
                **trading_config,
                'position_size': self.config.get('advanced_strategy.position_size', 5000000),
                'base_stop_loss': self.config.get('advanced_strategy.base_stop_loss', 0.025),
                'use_multi_timeframe': self.config.get('advanced_strategy.use_multi_timeframe', True),
                'use_orderbook': self.config.get('advanced_strategy.use_orderbook', True),
                'use_funding_rate': self.config.get('advanced_strategy.use_funding_rate', True),
                'use_volume_confirm': self.config.get('advanced_strategy.use_volume_confirm', True)
            }
            self.strategy = AdvancedStrategy(strategy_config, self.api_client)
        elif strategy_type == 'enhanced':
            # 增强策略 (MACD+KDJ+RSI+BB组合)
            strategy_config = {
                **trading_config,
                'position_size': self.config.get('enhanced_strategy.position_size', 0.1),
                'base_stop_loss': self.config.get('enhanced_strategy.base_stop_loss', 0.02),
                'macd_fast': self.config.get('enhanced_strategy.macd_fast', 12),
                'macd_slow': self.config.get('enhanced_strategy.macd_slow', 26),
                'macd_signal': self.config.get('enhanced_strategy.macd_signal', 9),
                'kdj_n': self.config.get('enhanced_strategy.kdj_n', 9),
                'kdj_m1': self.config.get('enhanced_strategy.kdj_m1', 3),
                'kdj_m2': self.config.get('enhanced_strategy.kdj_m2', 3),
                'rsi_period': self.config.get('enhanced_strategy.rsi_period', 14),
                'bb_period': self.config.get('enhanced_strategy.bb_period', 20),
                'bb_std': self.config.get('enhanced_strategy.bb_std', 2),
                'min_signal_score': self.config.get('enhanced_strategy.min_signal_score', 60)
            }
            self.strategy = EnhancedStrategy(strategy_config, self.api_client)
        else:
            # 做多做空仓位策略
            strategy_config = {
                **trading_config,
                'position_size': self.config.get('position_strategy.position_size', 0.1),
                'stop_loss_rate': self.config.get('position_strategy.stop_loss_rate', 0.03),
                'take_profit_rate': self.config.get('position_strategy.take_profit_rate', 0.05),
                'ma_short_period': self.config.get('position_strategy.ma_short_period', 5),
                'ma_long_period': self.config.get('position_strategy.ma_long_period', 20)
            }
            self.strategy = PositionStrategy(strategy_config, self.api_client)

        # 初始化风险管理
        risk_config = self.config.get_risk_config()
        self.risk_manager = RiskManager(risk_config)

        # 运行标志
        self.is_running = False

        self.logger.info("=" * 60)
        self.logger.info("OKX 量化交易机器人初始化完成")
        self.logger.info("=" * 60)

    def run_live(self):
        """运行实盘/模拟盘交易"""
        try:
            self.logger.info("启动实时交易模式...")
            self.is_running = True

            # 设置杠杆
            trading_config = self.config.get_trading_config()
            symbol = trading_config['symbol']
            leverage = trading_config['leverage']
            margin_mode = trading_config['margin_mode']

            self.logger.info(f"设置杠杆: {symbol}, {leverage}x, {margin_mode}")
            result = self.api_client.set_leverage(
                inst_id=symbol,
                lever=leverage,
                mgn_mode=margin_mode
            )

            if result['code'] != '0':
                self.logger.error(f"设置杠杆失败: {result.get('msg', 'Unknown error')}")
                return

            # 获取账户余额
            balance_result = self.api_client.get_balance()
            if balance_result['code'] == '0' and balance_result['data']:
                balance_data = balance_result['data'][0]
                total_equity = float(balance_data.get('totalEq', 0))
                self.risk_manager.update_balance(total_equity)
                self.logger.info(f"当前账户权益: {total_equity:.2f} USDT")

            # 初始化策略
            strategy_type = self.config.get('trading.strategy_type', 'position')
            if strategy_type == 'grid':
                # 网格策略需要初始化网格
                self.strategy.initialize_grid()

            # 连接WebSocket
            okx_config = self.config.get_okx_config()
            self.ws_client = OKXWebSocket(
                api_key=okx_config['api_key'],
                secret_key=okx_config['secret_key'],
                passphrase=okx_config['passphrase'],
                is_simulated=okx_config.get('is_simulated', True)
            )

            self.ws_client.connect()

            # 订阅行情数据
            self.ws_client.subscribe_ticker(symbol, self.on_ticker)

            # 订阅订单更新（需要登录）
            # self.ws_client.subscribe_orders(callback=self.on_order_update)

            self.logger.info("WebSocket已连接，开始监听市场数据...")

            # 主循环
            while self.is_running:
                try:
                    # 定期检查订单状态
                    time.sleep(5)

                    # 获取待成交订单
                    orders = self.api_client.get_pending_orders(inst_id=symbol)
                    if orders['code'] == '0':
                        self.strategy.on_order_update(orders.get('data', []))

                    # 打印策略状态
                    if int(time.time()) % 60 == 0:  # 每分钟打印一次
                        strategy_type = self.config.get('trading.strategy_type', 'position')
                        if strategy_type == 'grid':
                            self.strategy.print_grid_status()
                        else:
                            self.strategy.print_status()
                        self.logger.info(self.risk_manager.get_risk_report())

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.logger.error(f"主循环异常: {e}")
                    time.sleep(1)

        except Exception as e:
            self.logger.error(f"运行实时交易异常: {e}")
        finally:
            self.stop()

    def run_backtest(self):
        """运行回测"""
        try:
            self.logger.info("启动回测模式...")

            # 初始化回测引擎
            backtest_config = self.config.get_backtest_config()
            backtester = Backtester(backtest_config)

            # 加载历史数据
            trading_config = self.config.get_trading_config()
            symbol = trading_config['symbol']

            df = backtester.load_historical_data(
                self.api_client,
                symbol,
                '1H',
                backtest_config['start_date'],
                backtest_config['end_date']
            )

            if df.empty:
                self.logger.error("无法加载历史数据")
                return

            # 运行回测
            grid_config = self.config.get_grid_config()
            results = backtester.simulate_grid_strategy(df, grid_config)

            # 打印结果
            backtester.print_results(results)

            # 导出结果
            backtester.export_results(results)

        except Exception as e:
            self.logger.error(f"回测异常: {e}")

    def test_connection(self):
        """测试API连接"""
        try:
            self.logger.info("测试API连接...")

            # 测试获取行情
            symbol = self.config.get('trading.symbol')
            ticker = self.api_client.get_ticker(symbol)

            if ticker['code'] == '0' and ticker['data']:
                data = ticker['data'][0]
                self.logger.info(f"行情获取成功:")
                self.logger.info(f"产品: {data['instId']}")
                self.logger.info(f"最新价: {data['last']}")
                self.logger.info(f"24h最高: {data.get('high24h', 'N/A')}")
                self.logger.info(f"24h最低: {data.get('low24h', 'N/A')}")
                self.logger.info(f"24h成交量: {data.get('vol24h', 'N/A')}")
            else:
                self.logger.error(f"获取行情失败: {ticker.get('msg', 'Unknown error')}")

            # 测试获取账户余额
            balance = self.api_client.get_balance()
            if balance['code'] == '0' and balance['data']:
                self.logger.info(f"账户余额获取成功:")
                for detail in balance['data'][0].get('details', []):
                    ccy = detail.get('ccy')
                    avail_eq = detail.get('availEq')
                    self.logger.info(f"{ccy}: {avail_eq}")
            else:
                self.logger.error(f"获取余额失败: {balance.get('msg', 'Unknown error')}")

            self.logger.info("连接测试完成")

        except Exception as e:
            self.logger.error(f"连接测试失败: {e}")

    def on_ticker(self, data):
        """处理行情数据"""
        try:
            self.strategy.on_tick(data)
        except Exception as e:
            self.logger.error(f"处理行情数据异常: {e}")

    def on_order_update(self, data):
        """处理订单更新"""
        try:
            self.strategy.on_order_update(data)
        except Exception as e:
            self.logger.error(f"处理订单更新异常: {e}")

    def stop(self):
        """停止机器人"""
        self.logger.info("正在停止交易机器人...")
        self.is_running = False

        # 取消所有订单
        try:
            self.strategy.cancel_all_orders()
        except Exception as e:
            self.logger.error(f"取消订单失败: {e}")

        # 断开WebSocket
        if self.ws_client:
            try:
                self.ws_client.disconnect()
            except Exception as e:
                self.logger.error(f"断开WebSocket失败: {e}")

        self.logger.info("交易机器人已停止")


def signal_handler(sig, frame):
    """信号处理器"""
    print("\n接收到中断信号，正在退出...")
    sys.exit(0)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='OKX 量化交易机器人')
    parser.add_argument('--mode', type=str, default='test',
                       choices=['live', 'backtest', 'test'],
                       help='运行模式: live=实盘, backtest=回测, test=测试连接')
    parser.add_argument('--config', type=str, default=None,
                       help='配置文件路径')

    args = parser.parse_args()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)

    # 创建机器人实例
    bot = TradingBot(args.config)

    # 根据模式运行
    if args.mode == 'live':
        bot.run_live()
    elif args.mode == 'backtest':
        bot.run_backtest()
    elif args.mode == 'test':
        bot.test_connection()


if __name__ == '__main__':
    main()
