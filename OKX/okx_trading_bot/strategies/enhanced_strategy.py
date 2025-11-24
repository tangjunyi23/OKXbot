"""
增强版量化策略 - 多指标组合
整合: MACD + KDJ + RSI + 布林带 + 动态仓位管理 + 智能止盈止损
"""
import time
import statistics
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from .base_strategy import BaseStrategy
from ..utils.logger import setup_logger


class EnhancedStrategy(BaseStrategy):
    """增强版多指标组合策略"""

    def __init__(self, config: Dict, api_client):
        super().__init__(config)
        self.api_client = api_client
        self.logger = setup_logger("EnhancedStrategy")

        # 基础参数
        self.symbol = config.get('symbol', 'BTC-USDT-SWAP')
        self.base_position_size = config.get('position_size', 0.1)
        self.leverage = config.get('leverage', 20)

        # 止盈止损
        self.base_stop_loss = config.get('base_stop_loss', 0.02)
        self.base_take_profit = config.get('base_take_profit', 0.04)
        self.trailing_stop = config.get('trailing_stop', True)
        self.trailing_distance = config.get('trailing_distance', 0.015)

        # 技术指标参数
        self.macd_fast = config.get('macd_fast', 12)
        self.macd_slow = config.get('macd_slow', 26)
        self.macd_signal = config.get('macd_signal', 9)

        self.kdj_n = config.get('kdj_n', 9)
        self.kdj_m1 = config.get('kdj_m1', 3)
        self.kdj_m2 = config.get('kdj_m2', 3)

        self.rsi_period = config.get('rsi_period', 14)
        self.bb_period = config.get('bb_period', 20)

        # 合约信息
        self.contract_value = 0.01
        self.min_size = 0.01
        self.lot_size = 0.01
        self._load_instrument_info()

        # 数据缓存
        self.price_history = []
        self.high_history = []
        self.low_history = []
        self.close_history = []

        # 交易状态
        self.current_position = None
        self.trade_history = []
        self.total_trades = 0
        self.winning_trades = 0
        self.highest_profit_price = None

        self.last_check_time = 0

        self.logger.info("=" * 60)
        self.logger.info("🚀 增强版多指标策略初始化")
        self.logger.info("=" * 60)
        self.logger.info(f"交易对: {self.symbol}")
        self.logger.info(f"杠杆: {self.leverage}x")
        self.logger.info(f"技术指标: MACD + KDJ + RSI + 布林带")
        self.logger.info("=" * 60)

    def _load_instrument_info(self):
        """加载合约信息"""
        try:
            instruments = self.api_client.get_instruments('SWAP')
            if instruments['code'] == '0':
                for inst in instruments['data']:
                    if inst['instId'] == self.symbol:
                        self.contract_value = float(inst.get('ctVal', 0.01))
                        self.min_size = float(inst.get('minSz', 0.01))
                        self.lot_size = float(inst.get('lotSz', 0.01))
                        break
        except Exception as e:
            self.logger.warning(f"获取合约信息失败: {e}")

    def calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """计算EMA（指数移动平均）"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def calculate_macd(self, prices: List[float]) -> Optional[Tuple[float, float, float]]:
        """
        计算MACD指标
        返回: (MACD值, 信号线, 柱状图)
        """
        if len(prices) < self.macd_slow:
            return None

        # 快线EMA
        ema_fast = self.calculate_ema(prices, self.macd_fast)
        # 慢线EMA
        ema_slow = self.calculate_ema(prices, self.macd_slow)

        if ema_fast is None or ema_slow is None:
            return None

        # MACD = 快线 - 慢线
        macd = ema_fast - ema_slow

        # 信号线 = MACD的9日EMA
        macd_list = []
        for i in range(self.macd_slow, len(prices) + 1):
            ema_f = self.calculate_ema(prices[:i], self.macd_fast)
            ema_s = self.calculate_ema(prices[:i], self.macd_slow)
            if ema_f and ema_s:
                macd_list.append(ema_f - ema_s)

        if len(macd_list) < self.macd_signal:
            return None

        signal = self.calculate_ema(macd_list, self.macd_signal)
        if signal is None:
            return None

        # 柱状图 = MACD - 信号线
        histogram = macd - signal

        return macd, signal, histogram

    def calculate_kdj(self, high_list: List[float], low_list: List[float],
                     close_list: List[float]) -> Optional[Tuple[float, float, float]]:
        """
        计算KDJ指标
        返回: (K值, D值, J值)
        """
        if len(high_list) < self.kdj_n or len(low_list) < self.kdj_n or len(close_list) < self.kdj_n:
            return None

        # 取最近N天的数据
        recent_high = high_list[-self.kdj_n:]
        recent_low = low_list[-self.kdj_n:]
        recent_close = close_list[-self.kdj_n:]

        # 计算RSV (未成熟随机值)
        highest = max(recent_high)
        lowest = min(recent_low)
        current_close = recent_close[-1]

        if highest == lowest:
            rsv = 50
        else:
            rsv = (current_close - lowest) / (highest - lowest) * 100

        # K值 = RSV的M1日移动平均
        # D值 = K值的M2日移动平均
        # J值 = 3K - 2D

        # 简化计算：使用SMA平滑
        if not hasattr(self, 'kdj_k_history'):
            self.kdj_k_history = []
            self.kdj_d_history = []

        # K值
        if len(self.kdj_k_history) == 0:
            k = rsv
        else:
            k = (self.kdj_k_history[-1] * (self.kdj_m1 - 1) + rsv) / self.kdj_m1

        self.kdj_k_history.append(k)
        if len(self.kdj_k_history) > 50:
            self.kdj_k_history.pop(0)

        # D值
        if len(self.kdj_d_history) == 0:
            d = k
        else:
            d = (self.kdj_d_history[-1] * (self.kdj_m2 - 1) + k) / self.kdj_m2

        self.kdj_d_history.append(d)
        if len(self.kdj_d_history) > 50:
            self.kdj_d_history.pop(0)

        # J值
        j = 3 * k - 2 * d

        return k, d, j

    def calculate_rsi(self, prices: List[float]) -> Optional[float]:
        """计算RSI指标"""
        if len(prices) < self.rsi_period + 1:
            return None

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

        avg_gain = sum(gains[-self.rsi_period:]) / self.rsi_period
        avg_loss = sum(losses[-self.rsi_period:]) / self.rsi_period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_bollinger_bands(self, prices: List[float]) -> Optional[Tuple[float, float, float]]:
        """计算布林带"""
        if len(prices) < self.bb_period:
            return None

        recent = prices[-self.bb_period:]
        ma = sum(recent) / self.bb_period
        std = statistics.stdev(recent)

        upper = ma + (2 * std)
        lower = ma - (2 * std)

        return upper, ma, lower

    def calculate_signal_score(self, side: str) -> float:
        """
        计算综合信号评分 (0-100)

        使用多指标组合:
        - MACD金叉/死叉 (25分)
        - KDJ超买超卖 (25分)
        - RSI确认 (20分)
        - 布林带位置 (20分)
        - 趋势确认 (10分)
        """
        score = 0
        details = []

        # 1. MACD指标 (25分)
        macd_result = self.calculate_macd(self.price_history)
        if macd_result:
            macd, signal, histogram = macd_result

            if side == 'long':
                # MACD金叉：MACD > Signal 且柱状图为正
                if macd > signal and histogram > 0:
                    score += 25
                    details.append("MACD金叉(+25)")
                elif macd > signal:
                    score += 15
                    details.append("MACD向上(+15)")
            else:  # short
                # MACD死叉：MACD < Signal 且柱状图为负
                if macd < signal and histogram < 0:
                    score += 25
                    details.append("MACD死叉(+25)")
                elif macd < signal:
                    score += 15
                    details.append("MACD向下(+15)")

        # 2. KDJ指标 (25分)
        if len(self.high_history) >= self.kdj_n:
            kdj_result = self.calculate_kdj(self.high_history, self.low_history, self.close_history)
            if kdj_result:
                k, d, j = kdj_result

                if side == 'long':
                    # K值上穿D值，且在超卖区（K<20）
                    if k < 20 and k > d:
                        score += 25
                        details.append(f"KDJ超卖反转(+25, K={k:.1f})")
                    elif k > d:
                        score += 15
                        details.append(f"KDJ金叉(+15, K={k:.1f})")
                else:  # short
                    # K值下穿D值，且在超买区（K>80）
                    if k > 80 and k < d:
                        score += 25
                        details.append(f"KDJ超买反转(+25, K={k:.1f})")
                    elif k < d:
                        score += 15
                        details.append(f"KDJ死叉(+15, K={k:.1f})")

        # 3. RSI指标 (20分)
        rsi = self.calculate_rsi(self.price_history)
        if rsi:
            if side == 'long':
                if rsi < 30:
                    score += 20
                    details.append(f"RSI超卖(+20, {rsi:.1f})")
                elif rsi < 50:
                    score += 10
                    details.append(f"RSI偏低(+10, {rsi:.1f})")
            else:  # short
                if rsi > 70:
                    score += 20
                    details.append(f"RSI超买(+20, {rsi:.1f})")
                elif rsi > 50:
                    score += 10
                    details.append(f"RSI偏高(+10, {rsi:.1f})")

        # 4. 布林带指标 (20分)
        bb = self.calculate_bollinger_bands(self.price_history)
        if bb and self.price_history:
            upper, middle, lower = bb
            current_price = self.price_history[-1]

            if side == 'long':
                # 价格接近下轨
                if current_price <= lower:
                    score += 20
                    details.append("价格触及下轨(+20)")
                elif current_price < middle:
                    score += 10
                    details.append("价格低于中轨(+10)")
            else:  # short
                # 价格接近上轨
                if current_price >= upper:
                    score += 20
                    details.append("价格触及上轨(+20)")
                elif current_price > middle:
                    score += 10
                    details.append("价格高于中轨(+10)")

        # 5. 趋势确认 (10分)
        if len(self.price_history) >= 20:
            ma_short = sum(self.price_history[-5:]) / 5
            ma_long = sum(self.price_history[-20:]) / 20

            if side == 'long' and ma_short > ma_long:
                score += 10
                details.append("短期趋势向上(+10)")
            elif side == 'short' and ma_short < ma_long:
                score += 10
                details.append("短期趋势向下(+10)")

        # 记录得分详情
        self.logger.info(f"   信号评分: {score}/100")
        if details:
            self.logger.info(f"   详情: {', '.join(details)}")

        return score

    def calculate_dynamic_position_size(self, signal_strength: float) -> float:
        """
        动态仓位管理 (Kelly公式改进)

        考虑因素:
        1. 信号强度 (70-100分用大仓位，60-70中等，<60小仓位)
        2. 历史胜率
        3. 连续盈亏
        """
        base = self.base_position_size
        multiplier = 1.0

        # 1. 信号强度调整
        if signal_strength >= 80:
            multiplier *= 1.5  # 强信号，加仓50%
        elif signal_strength >= 70:
            multiplier *= 1.2  # 中强信号，加仓20%
        elif signal_strength < 60:
            multiplier *= 0.7  # 弱信号，减仓30%

        # 2. 胜率调整
        if self.total_trades >= 10:
            win_rate = self.winning_trades / self.total_trades
            if win_rate >= 0.6:
                multiplier *= 1.3
            elif win_rate < 0.4:
                multiplier *= 0.6

        # 限制范围
        multiplier = max(0.5, min(2.0, multiplier))

        return base * multiplier

    def on_tick(self, ticker_data: Dict):
        """处理行情数据"""
        try:
            if not ticker_data:
                return

            current_price = float(ticker_data[0].get('last', 0))
            if current_price <= 0:
                return

            # 更新价格历史
            self.price_history.append(current_price)
            self.close_history.append(current_price)

            # 获取K线数据更新高低价
            self._update_kline_data()

            if len(self.price_history) > 200:
                self.price_history.pop(0)
                self.close_history.pop(0)

            # 每30秒检查一次
            current_time = time.time()
            if current_time - self.last_check_time < 30:
                return
            self.last_check_time = current_time

            # 更新持仓
            self._update_position()

            # 检查交易信号
            if self.current_position:
                self._check_exit_conditions()
            else:
                self._check_entry_signals()

        except Exception as e:
            self.logger.error(f"处理行情异常: {e}")

    def _update_kline_data(self):
        """更新K线数据（高低价）"""
        try:
            candles = self.api_client.get_candles(self.symbol, bar='15m', limit=50)
            if candles['code'] == '0' and candles['data']:
                self.high_history = [float(c[2]) for c in reversed(candles['data'])]
                self.low_history = [float(c[3]) for c in reversed(candles['data'])]
        except:
            pass

    def _check_entry_signals(self):
        """检查入场信号"""
        try:
            if len(self.price_history) < 50:
                return

            # 做多信号评分
            long_score = self.calculate_signal_score('long')
            # 做空信号评分
            short_score = self.calculate_signal_score('short')

            # 信号强度阈值：70分以上开仓
            if long_score >= 70:
                self.logger.info(f"🟢 检测到做多信号 (强度: {long_score}/100)")
                self._open_position('long', long_score)
            elif short_score >= 70:
                self.logger.info(f"🔴 检测到做空信号 (强度: {short_score}/100)")
                self._open_position('short', short_score)

        except Exception as e:
            self.logger.error(f"检查入场信号异常: {e}")

    def _open_position(self, side: str, signal_strength: float):
        """开仓"""
        try:
            position_size = self.calculate_dynamic_position_size(signal_strength)
            contracts = position_size / self.contract_value
            contracts = round(contracts / self.lot_size) * self.lot_size

            if contracts < self.min_size:
                contracts = self.min_size

            order_side = 'buy' if side == 'long' else 'sell'

            self.logger.info(f"开仓: {side.upper()}, 数量={contracts}张, 信号强度={signal_strength:.1f}")

            result = self.api_client.place_order(
                inst_id=self.symbol,
                side=order_side,
                order_type='market',
                size=str(contracts),
                pos_side='net',
                td_mode='cross'
            )

            if result['code'] == '0':
                self.logger.info(f"✅ 开仓成功")
                self.highest_profit_price = None
                time.sleep(1)
                self._update_position()
            else:
                self.logger.error(f"开仓失败: {result.get('msg')}")

        except Exception as e:
            self.logger.error(f"开仓异常: {e}")

    def _check_exit_conditions(self):
        """检查退出条件"""
        if not self.current_position:
            return

        try:
            entry_price = self.current_position['entry_price']
            side = self.current_position['side']
            current_price = self.price_history[-1] if self.price_history else None

            if not current_price:
                return

            # 计算盈亏率
            if side == 'long':
                profit_rate = (current_price - entry_price) / entry_price
            else:
                profit_rate = (entry_price - current_price) / entry_price

            # 移动止盈
            if self.trailing_stop and profit_rate > self.trailing_distance:
                if self.highest_profit_price is None:
                    self.highest_profit_price = current_price
                    self.logger.info(f"🎯 启动移动止盈")

                if side == 'long' and current_price > self.highest_profit_price:
                    self.highest_profit_price = current_price
                elif side == 'short' and current_price < self.highest_profit_price:
                    self.highest_profit_price = current_price

                # 检查回撤
                if side == 'long':
                    drawdown = (self.highest_profit_price - current_price) / self.highest_profit_price
                else:
                    drawdown = (current_price - self.highest_profit_price) / self.highest_profit_price

                if drawdown >= self.trailing_distance:
                    self.logger.info(f"📈 移动止盈触发")
                    self._close_position(profit_rate, "移动止盈")
                    return

            # 固定止盈
            if profit_rate >= self.base_take_profit:
                self.logger.info(f"🎯 触发止盈: {profit_rate*100:.2f}%")
                self._close_position(profit_rate, "固定止盈")
            # 止损
            elif profit_rate <= -self.base_stop_loss:
                self.logger.info(f"🛑 触发止损: {profit_rate*100:.2f}%")
                self._close_position(profit_rate, "止损")

        except Exception as e:
            self.logger.error(f"检查退出条件异常: {e}")

    def _close_position(self, profit_rate: float, reason: str):
        """平仓"""
        if not self.current_position:
            return

        try:
            side = self.current_position['side']
            contracts = float(self.current_position['contracts'])
            order_side = 'sell' if side == 'long' else 'buy'

            self.logger.info(f"平仓: {reason}, 收益率={profit_rate*100:.2f}%")

            result = self.api_client.place_order(
                inst_id=self.symbol,
                side=order_side,
                order_type='market',
                size=str(contracts),
                pos_side='net',
                td_mode='cross'
            )

            if result['code'] == '0':
                self.logger.info(f"✅ 平仓成功")

                self.total_trades += 1
                if profit_rate > 0:
                    self.winning_trades += 1

                win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
                self.logger.info(f"📊 统计: 总{self.total_trades}次, 胜率{win_rate:.1f}%")

                self.current_position = None
                self.highest_profit_price = None
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
        pass

    def get_status(self) -> Dict:
        """获取策略状态"""
        return {
            'symbol': self.symbol,
            'position': self.current_position,
            'total_trades': self.total_trades,
            'win_rate': self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        }

    def print_status(self):
        """打印策略状态"""
        status = self.get_status()
        self.logger.info("=" * 60)
        self.logger.info(f"增强策略状态")
        self.logger.info(f"总交易: {status['total_trades']}次, 胜率{status['win_rate']*100:.1f}%")
        if status['position']:
            pos = status['position']
            self.logger.info(f"持仓: {pos['side'].upper()}, {pos['contracts']}张")
        self.logger.info("=" * 60)
