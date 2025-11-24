"""
智能利润最大化策略

核心优化：
1. 信号强度评分 - 只做高质量交易
2. 动态仓位管理 - 根据胜率和账户调整
3. 移动止盈 - 让利润奔跑
4. 波动率自适应 - 根据市场调整参数
5. 时间过滤 - 只在高波动时段交易
6. 智能加减仓 - 连胜加仓，连亏减仓
"""

import time
from typing import Dict, List, Optional
from datetime import datetime, time as dt_time
from .base_strategy import BaseStrategy
from ..utils.logger import setup_logger
import statistics


class SmartProfitStrategy(BaseStrategy):
    """智能利润最大化策略"""

    def __init__(self, config: Dict, api_client):
        super().__init__(config)
        self.api_client = api_client
        self.logger = setup_logger("SmartProfitStrategy")

        # 基础参数
        self.symbol = config.get('symbol', 'ETH-USDT-SWAP')
        self.base_position_size = config.get('position_size', 0.1)
        self.base_stop_loss = config.get('stop_loss_rate', 0.02)
        self.base_take_profit = config.get('take_profit_rate', 0.045)
        self.leverage = config.get('leverage', 50)

        # 智能优化参数
        self.use_trailing_stop = config.get('use_trailing_stop', True)  # 移动止盈
        self.trailing_stop_trigger = config.get('trailing_stop_trigger', 0.02)  # 2%后启动追踪
        self.trailing_stop_distance = config.get('trailing_stop_distance', 0.01)  # 追踪距离1%

        self.use_dynamic_position = config.get('use_dynamic_position', True)  # 动态仓位
        self.use_signal_filter = config.get('use_signal_filter', True)  # 信号过滤
        self.use_time_filter = config.get('use_time_filter', True)  # 时间过滤
        self.use_volatility_adapt = config.get('use_volatility_adapt', True)  # 波动率自适应

        # 合约信息
        self.contract_value = 0.1
        self.min_size = 0.01
        self.lot_size = 0.01

        try:
            instruments = self.api_client.get_instruments('SWAP')
            if instruments['code'] == '0':
                for inst in instruments['data']:
                    if inst['instId'] == self.symbol:
                        self.contract_value = float(inst.get('ctVal', 0.1))
                        self.min_size = float(inst.get('minSz', 0.01))
                        self.lot_size = float(inst.get('lotSz', 0.01))
                        break
        except Exception as e:
            self.logger.warning(f"获取合约信息失败: {e}")

        # 状态变量
        self.current_price = None
        self.current_position = None
        self.price_history = []
        self.last_check_time = 0

        # 交易记录
        self.trade_history = []  # 历史交易记录
        self.consecutive_wins = 0  # 连续盈利次数
        self.consecutive_losses = 0  # 连续亏损次数
        self.total_trades = 0
        self.winning_trades = 0

        # 移动止盈追踪
        self.trailing_stop_active = False
        self.highest_profit_price = None

        # 技术指标参数
        self.ma_short_period = config.get('ma_short_period', 5)
        self.ma_long_period = config.get('ma_long_period', 20)
        self.rsi_period = config.get('rsi_period', 14)
        self.min_signal_strength = config.get('min_signal_strength', 60)
        self.rsi_history = []

        self.logger.info("=" * 60)
        self.logger.info("智能利润最大化策略初始化")
        self.logger.info("=" * 60)
        self.logger.info(f"交易对: {self.symbol}")
        self.logger.info(f"基础仓位: {self.base_position_size} ETH")
        self.logger.info(f"杠杆: {self.leverage}x")
        self.logger.info(f"优化功能:")
        self.logger.info(f"  移动止盈: {'开启' if self.use_trailing_stop else '关闭'}")
        self.logger.info(f"  动态仓位: {'开启' if self.use_dynamic_position else '关闭'}")
        self.logger.info(f"  信号过滤: {'开启' if self.use_signal_filter else '关闭'}")
        self.logger.info(f"  时间过滤: {'开启' if self.use_time_filter else '关闭'}")
        self.logger.info(f"  波动率自适应: {'开启' if self.use_volatility_adapt else '关闭'}")
        self.logger.info("=" * 60)

    def calculate_ma(self, period: int) -> Optional[float]:
        """计算移动平均"""
        if len(self.price_history) < period:
            return None
        return sum(self.price_history[-period:]) / period

    def calculate_rsi(self) -> Optional[float]:
        """计算RSI指标"""
        if len(self.price_history) < self.rsi_period + 1:
            return None

        prices = self.price_history[-(self.rsi_period + 1):]
        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / self.rsi_period
        avg_loss = sum(losses) / self.rsi_period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_volatility(self) -> float:
        """计算价格波动率"""
        if len(self.price_history) < 20:
            return 0.04  # 默认4%

        recent_prices = self.price_history[-20:]
        returns = [(recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1]
                   for i in range(1, len(recent_prices))]

        if len(returns) < 2:
            return 0.04

        return statistics.stdev(returns)

    def is_trading_time(self) -> bool:
        """检查是否在推荐交易时段"""
        if not self.use_time_filter:
            return True

        # UTC时间高波动时段
        # 12:00-16:00 (亚洲)
        # 20:00-00:00 (欧美)
        now = datetime.utcnow()
        hour = now.hour

        # 亚洲时段或欧美时段
        return (12 <= hour < 16) or (20 <= hour < 24) or (0 <= hour < 2)

    def calculate_signal_strength(self, side: str, ma_short: float, ma_long: float,
                                   rsi: Optional[float]) -> float:
        """
        计算信号强度 (0-100)

        考虑因素：
        1. MA差距 (趋势强度)
        2. RSI确认
        3. 价格位置
        4. 波动率
        """
        score = 0

        # 1. MA差距评分 (0-40分)
        ma_diff = abs(ma_short - ma_long) / self.current_price
        if ma_diff > 0.005:  # 0.5%以上
            score += 40
        elif ma_diff > 0.003:  # 0.3-0.5%
            score += 30
        elif ma_diff > 0.001:  # 0.1-0.3%
            score += 20
        else:
            score += 10

        # 2. RSI确认 (0-30分)
        if rsi:
            if side == 'long':
                if rsi < 30:  # 超卖后做多
                    score += 30
                elif rsi < 50:
                    score += 20
                elif rsi < 70:
                    score += 10
            else:  # short
                if rsi > 70:  # 超买后做空
                    score += 30
                elif rsi > 50:
                    score += 20
                elif rsi > 30:
                    score += 10

        # 3. 价格位置 (0-20分)
        if side == 'long' and self.current_price > ma_short:
            score += 20
        elif side == 'short' and self.current_price < ma_short:
            score += 20
        else:
            score += 10

        # 4. 时间过滤 (0-10分)
        if self.is_trading_time():
            score += 10
        else:
            score += 0

        return score

    def calculate_dynamic_position_size(self) -> float:
        """
        动态计算仓位大小

        考虑因素：
        1. 胜率
        2. 连续盈亏
        3. 账户余额
        """
        if not self.use_dynamic_position:
            return self.base_position_size

        position_multiplier = 1.0

        # 1. 根据胜率调整
        if self.total_trades >= 5:
            win_rate = self.winning_trades / self.total_trades
            if win_rate >= 0.6:
                position_multiplier *= 1.5  # 胜率高，加仓50%
            elif win_rate >= 0.5:
                position_multiplier *= 1.2  # 胜率中等，加仓20%
            elif win_rate < 0.4:
                position_multiplier *= 0.7  # 胜率低，减仓30%

        # 2. 根据连续盈亏调整
        if self.consecutive_wins >= 3:
            position_multiplier *= 1.3  # 连赢3次，加仓30%
        elif self.consecutive_wins >= 2:
            position_multiplier *= 1.1  # 连赢2次，加仓10%

        if self.consecutive_losses >= 3:
            position_multiplier *= 0.5  # 连亏3次，减仓50%
        elif self.consecutive_losses >= 2:
            position_multiplier *= 0.7  # 连亏2次，减仓30%

        # 限制范围
        position_multiplier = max(0.5, min(2.0, position_multiplier))

        return self.base_position_size * position_multiplier

    def calculate_adaptive_stops(self) -> tuple:
        """
        根据波动率自适应调整止盈止损

        波动率高 → 止盈止损放宽
        波动率低 → 止盈止损收紧
        """
        if not self.use_volatility_adapt:
            return self.base_stop_loss, self.base_take_profit

        volatility = self.calculate_volatility()

        # 基准波动率 4%
        base_volatility = 0.04
        volatility_ratio = volatility / base_volatility

        # 调整止损 (1.5%-3%)
        adjusted_sl = self.base_stop_loss * volatility_ratio
        adjusted_sl = max(0.015, min(0.03, adjusted_sl))

        # 调整止盈 (3%-6%)
        adjusted_tp = self.base_take_profit * volatility_ratio
        adjusted_tp = max(0.03, min(0.06, adjusted_tp))

        return adjusted_sl, adjusted_tp

    def on_tick(self, ticker_data: Dict):
        """处理行情更新"""
        try:
            if not ticker_data:
                return

            last_price = float(ticker_data[0].get('last', 0))
            if last_price <= 0:
                return

            self.current_price = last_price
            self.price_history.append(last_price)

            if len(self.price_history) > 100:
                self.price_history.pop(0)

            # 每30秒检查一次
            current_time = time.time()
            if current_time - self.last_check_time < 30:
                return
            self.last_check_time = current_time

            # 更新持仓
            self._update_position()

            # 如果有持仓，检查退出条件
            if self.current_position:
                self._check_exit_conditions()
            else:
                # 检查入场信号
                self._check_entry_signals()

        except Exception as e:
            self.logger.error(f"处理行情异常: {e}")

    def _check_entry_signals(self):
        """检查入场信号"""
        try:
            if len(self.price_history) < self.ma_long_period:
                self.logger.info(f"数据不足: {len(self.price_history)}/{self.ma_long_period}, 等待更多数据...")
                return

            ma_short = self.calculate_ma(self.ma_short_period)
            ma_long = self.calculate_ma(self.ma_long_period)
            rsi = self.calculate_rsi()

            if ma_short is None or ma_long is None:
                self.logger.info(f"均线计算失败: MA{self.ma_short_period}={ma_short}, MA{self.ma_long_period}={ma_long}")
                return

            # 打印市场状态
            rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
            self.logger.info(f"📊 市场分析: 价格=${self.current_price:.8f}, MA{self.ma_short_period}={ma_short:.8f}, MA{self.ma_long_period}={ma_long:.8f}, RSI={rsi_str}")

            # 做多信号
            if ma_short > ma_long and self.current_price > ma_short:
                signal_strength = self.calculate_signal_strength('long', ma_short, ma_long, rsi)

                if self.use_signal_filter and signal_strength < self.min_signal_strength:
                    self.logger.info(f"做多信号强度不足: {signal_strength:.1f}/{self.min_signal_strength}, 跳过")
                    return

                self.logger.info(f"检测到做多信号 (强度: {signal_strength:.1f}/100)")
                rsi_display = f"{rsi:.1f}" if rsi is not None else "N/A"
                self.logger.info(f"  价格={self.current_price:.2f}, MA{self.ma_short_period}={ma_short:.2f}, "
                               f"MA{self.ma_long_period}={ma_long:.2f}, RSI={rsi_display}")
                self._open_position('long', signal_strength)

            # 做空信号
            elif ma_short < ma_long and self.current_price < ma_short:
                signal_strength = self.calculate_signal_strength('short', ma_short, ma_long, rsi)

                if self.use_signal_filter and signal_strength < self.min_signal_strength:
                    self.logger.info(f"做空信号强度不足: {signal_strength:.1f}/{self.min_signal_strength}, 跳过")
                    return

                self.logger.info(f"检测到做空信号 (强度: {signal_strength:.1f}/100)")
                rsi_display = f"{rsi:.1f}" if rsi is not None else "N/A"
                self.logger.info(f"  价格={self.current_price:.2f}, MA{self.ma_short_period}={ma_short:.2f}, "
                               f"MA{self.ma_long_period}={ma_long:.2f}, RSI={rsi_display}")
                self._open_position('short', signal_strength)

        except Exception as e:
            self.logger.error(f"检查入场信号异常: {e}")

    def _open_position(self, side: str, signal_strength: float):
        """开仓"""
        try:
            # 动态计算仓位
            position_size = self.calculate_dynamic_position_size()
            contracts = position_size / self.contract_value
            contracts = round(contracts / self.lot_size) * self.lot_size

            if contracts < self.min_size:
                contracts = self.min_size

            order_side = 'buy' if side == 'long' else 'sell'

            self.logger.info(f"开仓: {side}, 数量={contracts}张 ({contracts * self.contract_value:.4f} ETH), "
                           f"信号强度={signal_strength:.1f}")

            result = self.api_client.place_order(
                inst_id=self.symbol,
                side=order_side,
                order_type='market',
                size=str(contracts),
                pos_side='net',
                td_mode='cross'
            )

            if result['code'] == '0' and result['data']:
                order_id = result['data'][0]['ordId']
                self.logger.info(f"✅ 开仓成功: {side}, 订单ID: {order_id}")

                # 重置移动止盈
                self.trailing_stop_active = False
                self.highest_profit_price = None

                time.sleep(1)
                self._update_position()
            else:
                self.logger.error(f"开仓失败: {result.get('msg', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"开仓异常: {e}")

    def _check_exit_conditions(self):
        """检查退出条件（止盈止损）"""
        if not self.current_position:
            return

        try:
            entry_price = self.current_position['entry_price']
            side = self.current_position['side']

            # 获取自适应止盈止损
            stop_loss, take_profit = self.calculate_adaptive_stops()

            if side == 'long':
                profit_rate = (self.current_price - entry_price) / entry_price

                # 移动止盈逻辑
                if self.use_trailing_stop:
                    if profit_rate >= self.trailing_stop_trigger:
                        if not self.trailing_stop_active:
                            self.trailing_stop_active = True
                            self.highest_profit_price = self.current_price
                            self.logger.info(f"🎯 启动移动止盈! 当前价格: {self.current_price:.2f}")

                        if self.current_price > self.highest_profit_price:
                            self.highest_profit_price = self.current_price

                        # 检查是否回撤到追踪距离
                        drawdown = (self.highest_profit_price - self.current_price) / self.highest_profit_price
                        if drawdown >= self.trailing_stop_distance:
                            self.logger.info(f"📈 移动止盈触发! 最高价={self.highest_profit_price:.2f}, "
                                           f"当前价={self.current_price:.2f}, 回撤={drawdown*100:.2f}%")
                            self._close_position(profit_rate, reason="移动止盈")
                            return

                # 固定止盈
                if profit_rate >= take_profit:
                    self.logger.info(f"🎯 触发止盈: {profit_rate*100:.2f}% >= {take_profit*100:.2f}%")
                    self._close_position(profit_rate, reason="固定止盈")
                # 止损
                elif profit_rate <= -stop_loss:
                    self.logger.info(f"🛑 触发止损: {profit_rate*100:.2f}% <= -{stop_loss*100:.2f}%")
                    self._close_position(profit_rate, reason="止损")

            else:  # short
                profit_rate = (entry_price - self.current_price) / entry_price

                # 移动止盈逻辑
                if self.use_trailing_stop:
                    if profit_rate >= self.trailing_stop_trigger:
                        if not self.trailing_stop_active:
                            self.trailing_stop_active = True
                            self.highest_profit_price = self.current_price
                            self.logger.info(f"🎯 启动移动止盈! 当前价格: {self.current_price:.2f}")

                        if self.current_price < self.highest_profit_price:
                            self.highest_profit_price = self.current_price

                        # 检查是否回撤
                        drawdown = (self.current_price - self.highest_profit_price) / self.highest_profit_price
                        if drawdown >= self.trailing_stop_distance:
                            self.logger.info(f"📈 移动止盈触发! 最低价={self.highest_profit_price:.2f}, "
                                           f"当前价={self.current_price:.2f}, 回撤={drawdown*100:.2f}%")
                            self._close_position(profit_rate, reason="移动止盈")
                            return

                # 固定止盈
                if profit_rate >= take_profit:
                    self.logger.info(f"🎯 触发止盈: {profit_rate*100:.2f}% >= {take_profit*100:.2f}%")
                    self._close_position(profit_rate, reason="固定止盈")
                # 止损
                elif profit_rate <= -stop_loss:
                    self.logger.info(f"🛑 触发止损: {profit_rate*100:.2f}% <= -{stop_loss*100:.2f}%")
                    self._close_position(profit_rate, reason="止损")

        except Exception as e:
            self.logger.error(f"检查退出条件异常: {e}")

    def _close_position(self, profit_rate: float, reason: str = "平仓"):
        """平仓"""
        if not self.current_position:
            return

        try:
            side = self.current_position['side']
            contracts = float(self.current_position['contracts'])  # 改为float避免截断
            order_side = 'sell' if side == 'long' else 'buy'

            self.logger.info(f"平仓: {reason}, {side}, 数量={contracts}张, 收益率={profit_rate*100:.2f}%")

            result = self.api_client.place_order(
                inst_id=self.symbol,
                side=order_side,
                order_type='market',
                size=str(contracts),  # 转为字符串，保留小数
                pos_side='net',
                td_mode='cross'
            )

            if result['code'] == '0':
                self.logger.info(f"✅ 平仓成功: {reason}")

                # 更新交易统计
                self.total_trades += 1
                if profit_rate > 0:
                    self.winning_trades += 1
                    self.consecutive_wins += 1
                    self.consecutive_losses = 0
                else:
                    self.consecutive_wins = 0
                    self.consecutive_losses += 1

                # 记录交易
                self.trade_history.append({
                    'time': datetime.now(),
                    'side': side,
                    'profit_rate': profit_rate,
                    'reason': reason
                })

                self.logger.info(f"📊 交易统计: 总{self.total_trades}次, 胜{self.winning_trades}次, "
                               f"胜率={self.winning_trades/self.total_trades*100:.1f}%, "
                               f"连胜{self.consecutive_wins}次, 连亏{self.consecutive_losses}次")

                self.current_position = None
                self.trailing_stop_active = False
            else:
                self.logger.error(f"平仓失败: {result.get('msg')}")

        except Exception as e:
            self.logger.error(f"平仓异常: {e}")

    def _update_position(self):
        """更新持仓"""
        try:
            positions = self.api_client.get_positions(inst_id=self.symbol)
            if positions['code'] == '0' and positions['data']:
                for pos in positions['data']:
                    pos_size = float(pos.get('pos', 0))
                    if pos_size != 0:
                        self.current_position = {
                            'side': 'long' if pos_size > 0 else 'short',
                            'size': abs(pos_size),
                            'entry_price': float(pos.get('avgPx', 0)),
                            'contracts': abs(pos_size)
                        }
                        return
            self.current_position = None
        except Exception as e:
            self.logger.error(f"更新持仓失败: {e}")

    def on_order_update(self, order_data: Dict):
        """处理订单更新"""
        pass

    def generate_signals(self) -> List[Dict]:
        """生成交易信号"""
        return []

    def cancel_all_orders(self):
        """取消所有订单"""
        self.logger.info("策略使用市价单，无需取消订单")

    def get_status(self) -> Dict:
        """获取策略状态"""
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'position': self.current_position,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': self.winning_trades / self.total_trades if self.total_trades > 0 else 0,
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses,
            'trailing_stop_active': self.trailing_stop_active,
        }

    def print_status(self):
        """打印策略状态"""
        status = self.get_status()
        self.logger.info("=" * 60)
        self.logger.info(f"智能策略状态")
        self.logger.info(f"当前价格: {status['current_price']:.2f}" if status['current_price'] else "N/A")
        self.logger.info(f"交易统计: {status['total_trades']}次, 胜率{status['win_rate']*100:.1f}%")
        self.logger.info(f"连续盈亏: 连胜{status['consecutive_wins']}次, 连亏{status['consecutive_losses']}次")

        if status['position']:
            pos = status['position']
            self.logger.info(f"持仓: {pos['side'].upper()}, {pos['contracts']}张")
            if status['trailing_stop_active']:
                self.logger.info(f"移动止盈: 已激活 🎯")
        self.logger.info("=" * 60)
