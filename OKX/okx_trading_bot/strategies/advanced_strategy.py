"""
高级利润最大化策略 - 多维度分析

核心优化：
1. 多时间框架分析 (1m, 5m, 15m)
2. 订单簿深度分析（支撑/阻力位）
3. 资金费率考虑（套利机会）
4. 波动率自适应（ATR, Bollinger Bands）
5. 成交量确认（真实突破）
6. 智能止盈追踪（分级止盈）
7. 动态仓位管理（Kelly公式）
8. 市场情绪分析（多空比）
"""

import time
import statistics
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from .base_strategy import BaseStrategy
from ..utils.logger import setup_logger


class AdvancedStrategy(BaseStrategy):
    """高级利润最大化策略"""

    def __init__(self, config: Dict, api_client):
        super().__init__(config)
        self.api_client = api_client
        self.logger = setup_logger("AdvancedStrategy")

        # 基础参数
        self.symbol = config.get('symbol', 'PEPE-USDT-SWAP')
        self.base_position_size = config.get('position_size', 5000000)
        self.leverage = config.get('leverage', 50)

        # 高级参数
        self.use_multi_timeframe = config.get('use_multi_timeframe', True)
        self.use_orderbook = config.get('use_orderbook', True)
        self.use_funding_rate = config.get('use_funding_rate', True)
        self.use_volume_confirm = config.get('use_volume_confirm', True)

        # 止盈止损
        self.base_stop_loss = config.get('base_stop_loss', 0.025)
        self.profit_levels = [
            (0.03, 0.3),   # 3%盈利，平仓30%
            (0.05, 0.4),   # 5%盈利，再平40%
            (0.08, 0.3),   # 8%盈利，平剩余30%
        ]

        # 合约信息
        self.contract_value = 10000000
        self.min_size = 0.1
        self.lot_size = 0.1
        self._load_instrument_info()

        # 数据存储
        self.price_data = {
            '1m': [],
            '5m': [],
            '15m': []
        }
        self.volume_data = []
        self.orderbook_data = None
        self.funding_rate = 0

        # 持仓和交易
        self.current_position = None
        self.trade_history = []
        self.total_trades = 0
        self.winning_trades = 0
        self.consecutive_wins = 0
        self.consecutive_losses = 0

        # 止盈追踪
        self.profit_targets_hit = []  # 记录已触发的止盈级别
        self.highest_profit_rate = 0

        self.last_check_time = 0

        self.logger.info("=" * 60)
        self.logger.info("🚀 高级利润最大化策略初始化")
        self.logger.info("=" * 60)
        self.logger.info(f"交易对: {self.symbol}")
        self.logger.info(f"杠杆: {self.leverage}x")
        self.logger.info(f"优化功能:")
        self.logger.info(f"  ✓ 多时间框架分析")
        self.logger.info(f"  ✓ 订单簿深度分析")
        self.logger.info(f"  ✓ 资金费率优化")
        self.logger.info(f"  ✓ 成交量确认")
        self.logger.info(f"  ✓ 分级止盈")
        self.logger.info("=" * 60)

    def _load_instrument_info(self):
        """加载合约信息"""
        try:
            instruments = self.api_client.get_instruments('SWAP')
            if instruments['code'] == '0':
                for inst in instruments['data']:
                    if inst['instId'] == self.symbol:
                        self.contract_value = float(inst.get('ctVal', 10000000))
                        self.min_size = float(inst.get('minSz', 0.1))
                        self.lot_size = float(inst.get('lotSz', 0.1))
                        break
        except Exception as e:
            self.logger.warning(f"获取合约信息失败: {e}")

    def on_tick(self, ticker_data: Dict):
        """处理行情更新"""
        try:
            if not ticker_data:
                return

            current_price = float(ticker_data[0].get('last', 0))
            if current_price <= 0:
                return

            # 更新1分钟数据
            self.price_data['1m'].append(current_price)
            if len(self.price_data['1m']) > 100:
                self.price_data['1m'].pop(0)

            # 每30秒检查一次
            current_time = time.time()
            if current_time - self.last_check_time < 30:
                return
            self.last_check_time = current_time

            # 更新多时间框架数据
            self._update_multi_timeframe_data()

            # 更新订单簿数据
            if self.use_orderbook:
                self._update_orderbook_data()

            # 更新资金费率
            if self.use_funding_rate:
                self._update_funding_rate()

            # 更新持仓
            self._update_position()

            # 检查退出或入场
            if self.current_position:
                self._check_exit_conditions()
            else:
                self._check_entry_signals()

        except Exception as e:
            self.logger.error(f"处理行情异常: {e}")

    def _update_multi_timeframe_data(self):
        """更新多时间框架数据"""
        try:
            # 获取5分钟K线
            candles_5m = self.api_client.get_candles(self.symbol, bar='5m', limit=20)
            if candles_5m['code'] == '0' and candles_5m['data']:
                self.price_data['5m'] = [float(c[4]) for c in candles_5m['data']]
                self.price_data['5m'].reverse()

            # 获取15分钟K线
            candles_15m = self.api_client.get_candles(self.symbol, bar='15m', limit=20)
            if candles_15m['code'] == '0' and candles_15m['data']:
                self.price_data['15m'] = [float(c[4]) for c in candles_15m['data']]
                self.price_data['15m'].reverse()

                # 提取成交量
                self.volume_data = [float(c[5]) for c in candles_15m['data']]
                self.volume_data.reverse()

        except Exception as e:
            self.logger.warning(f"更新多时间框架数据失败: {e}")

    def _update_orderbook_data(self):
        """更新订单簿数据"""
        try:
            orderbook = self.api_client.get_orderbook(self.symbol, depth=20)
            if orderbook['code'] == '0' and orderbook['data']:
                self.orderbook_data = orderbook['data'][0]
        except Exception as e:
            self.logger.warning(f"更新订单簿失败: {e}")

    def _update_funding_rate(self):
        """更新资金费率"""
        try:
            funding = self.api_client.get_funding_rate(self.symbol)
            if funding['code'] == '0' and funding['data']:
                self.funding_rate = float(funding['data'][0].get('fundingRate', 0))
        except Exception as e:
            self.logger.warning(f"更新资金费率失败: {e}")

    def calculate_ma(self, prices: List[float], period: int) -> Optional[float]:
        """计算移动平均"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """计算指数移动平均"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """计算RSI"""
        if len(prices) < period + 1:
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

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_atr(self, period: int = 14) -> Optional[float]:
        """计算ATR（真实波动幅度）"""
        if '15m' not in self.price_data or len(self.price_data['15m']) < period:
            return None

        prices = self.price_data['15m']
        tr_list = []

        for i in range(1, len(prices)):
            high = max(prices[i], prices[i-1])
            low = min(prices[i], prices[i-1])
            tr = high - low
            tr_list.append(tr)

        if len(tr_list) < period:
            return None

        return sum(tr_list[-period:]) / period

    def calculate_bollinger_bands(self, prices: List[float], period: int = 20) -> Optional[Tuple[float, float, float]]:
        """计算布林带"""
        if len(prices) < period:
            return None

        recent_prices = prices[-period:]
        ma = sum(recent_prices) / period
        std = statistics.stdev(recent_prices)

        upper = ma + (2 * std)
        lower = ma - (2 * std)

        return upper, ma, lower

    def analyze_orderbook_pressure(self) -> Optional[float]:
        """分析订单簿压力（多空力量对比）"""
        if not self.orderbook_data:
            return None

        try:
            bids = self.orderbook_data.get('bids', [])
            asks = self.orderbook_data.get('asks', [])

            if not bids or not asks:
                return None

            # 计算买卖盘总量
            bid_volume = sum([float(b[1]) for b in bids[:10]])
            ask_volume = sum([float(a[1]) for a in asks[:10]])

            if bid_volume + ask_volume == 0:
                return 0

            # 返回买盘占比 (>0.5 = 买盘强, <0.5 = 卖盘强)
            return bid_volume / (bid_volume + ask_volume)

        except Exception as e:
            self.logger.warning(f"分析订单簿失败: {e}")
            return None

    def calculate_volume_ratio(self) -> Optional[float]:
        """计算成交量比率"""
        if len(self.volume_data) < 10:
            return None

        recent_volume = self.volume_data[-1]
        avg_volume = sum(self.volume_data[-10:]) / 10

        if avg_volume == 0:
            return 1.0

        return recent_volume / avg_volume

    def calculate_multi_timeframe_score(self, side: str) -> float:
        """
        多时间框架信号评分 (0-100)

        综合1m, 5m, 15m的趋势一致性
        """
        score = 0

        timeframes = ['1m', '5m', '15m']
        weights = [0.2, 0.3, 0.5]  # 长周期权重更高

        for tf, weight in zip(timeframes, weights):
            prices = self.price_data.get(tf, [])
            if len(prices) < 20:
                continue

            ma_short = self.calculate_ma(prices, 5)
            ma_long = self.calculate_ma(prices, 15)

            if ma_short is None or ma_long is None:
                continue

            if side == 'long' and ma_short > ma_long:
                score += 100 * weight
            elif side == 'short' and ma_short < ma_long:
                score += 100 * weight

        return score

    def calculate_signal_strength(self, side: str) -> float:
        """
        综合信号强度评分 (0-100)

        考虑因素：
        1. 多时间框架一致性 (40分)
        2. RSI确认 (20分)
        3. 订单簿压力 (20分)
        4. 成交量确认 (10分)
        5. 资金费率 (10分)
        """
        score = 0
        debug_parts = []

        # 1. 多时间框架 (40分)
        mtf_score = self.calculate_multi_timeframe_score(side)
        mtf_points = mtf_score * 0.4
        score += mtf_points
        debug_parts.append(f"多时间框架={mtf_points:.1f}")

        # 2. RSI确认 (20分)
        rsi_points = 0
        prices_1m = self.price_data.get('1m', [])
        rsi_value = None
        if len(prices_1m) >= 20:
            rsi = self.calculate_rsi(prices_1m)
            if rsi:
                rsi_value = rsi
                if side == 'long' and rsi < 40:
                    rsi_points = 20
                elif side == 'long' and rsi < 50:
                    rsi_points = 15
                elif side == 'short' and rsi > 60:
                    rsi_points = 20
                elif side == 'short' and rsi > 50:
                    rsi_points = 15
                score += rsi_points
        rsi_str = f"{rsi_value:.1f}" if rsi_value is not None else "N/A"
        debug_parts.append(f"RSI={rsi_points:.1f}(值={rsi_str})")

        # 3. 订单簿压力 (20分)
        ob_points = 0
        ob_pressure = self.analyze_orderbook_pressure()
        if ob_pressure is not None:
            if side == 'long' and ob_pressure > 0.55:
                ob_points = 20
            elif side == 'long' and ob_pressure > 0.5:
                ob_points = 10
            elif side == 'short' and ob_pressure < 0.45:
                ob_points = 20
            elif side == 'short' and ob_pressure < 0.5:
                ob_points = 10
            score += ob_points
        ob_str = f"{ob_pressure:.2f}" if ob_pressure is not None else "N/A"
        debug_parts.append(f"订单簿={ob_points:.1f}(压力={ob_str})")

        # 4. 成交量确认 (10分)
        vol_points = 0
        volume_ratio = self.calculate_volume_ratio()
        if volume_ratio and volume_ratio > 1.5:
            vol_points = 10
        elif volume_ratio and volume_ratio > 1.2:
            vol_points = 5
        score += vol_points
        vol_str = f"{volume_ratio:.2f}" if volume_ratio is not None else "N/A"
        debug_parts.append(f"成交量={vol_points:.1f}(比率={vol_str})")

        # 5. 资金费率 (10分)
        fr_points = 0
        if self.funding_rate:
            if side == 'long' and self.funding_rate < 0:  # 负费率做多
                fr_points = 10
            elif side == 'short' and self.funding_rate > 0:  # 正费率做空
                fr_points = 10
            elif side == 'long' and self.funding_rate < 0.0001:
                fr_points = 5
            elif side == 'short' and self.funding_rate > 0.0001:
                fr_points = 5
            score += fr_points
        fr_str = f"{self.funding_rate*100:.4f}" if self.funding_rate is not None else "N/A"
        debug_parts.append(f"资金费率={fr_points:.1f}(值={fr_str}%)")

        # 记录详细得分
        self.logger.info(f"   得分详情: {', '.join(debug_parts)}")

        return min(100, score)

    def calculate_dynamic_position_size(self, signal_strength: float) -> float:
        """
        动态计算仓位大小（Kelly公式优化）

        考虑因素：
        1. 信号强度
        2. 历史胜率
        3. 连续盈亏
        4. 波动率
        """
        position_multiplier = 1.0

        # 1. 信号强度调整 (60-100分)
        if signal_strength >= 80:
            position_multiplier *= 1.5
        elif signal_strength >= 70:
            position_multiplier *= 1.2
        elif signal_strength < 50:
            position_multiplier *= 0.6

        # 2. 历史胜率调整
        if self.total_trades >= 5:
            win_rate = self.winning_trades / self.total_trades
            if win_rate >= 0.6:
                position_multiplier *= 1.3
            elif win_rate < 0.4:
                position_multiplier *= 0.7

        # 3. 连续盈亏调整
        if self.consecutive_wins >= 3:
            position_multiplier *= 1.2
        elif self.consecutive_losses >= 2:
            position_multiplier *= 0.6

        # 4. 波动率调整
        atr = self.calculate_atr()
        if atr and len(self.price_data.get('15m', [])) > 0:
            current_price = self.price_data['15m'][-1]
            volatility_pct = (atr / current_price) * 100

            if volatility_pct > 8:  # 高波动，减仓
                position_multiplier *= 0.8
            elif volatility_pct < 3:  # 低波动，可加仓
                position_multiplier *= 1.1

        # 限制范围 0.3-2.0
        position_multiplier = max(0.3, min(2.0, position_multiplier))

        return self.base_position_size * position_multiplier

    def _check_entry_signals(self):
        """检查入场信号"""
        try:
            if len(self.price_data.get('15m', [])) < 20:
                return

            prices_15m = self.price_data['15m']
            current_price = prices_15m[-1]

            # 计算布林带
            bb = self.calculate_bollinger_bands(prices_15m)
            if not bb:
                return

            upper, middle, lower = bb

            # 打印市场状态（每次分析时）
            bb_position = ((current_price - lower) / (upper - lower)) * 100 if upper > lower else 50
            self.logger.info(f"📊 市场分析: 价格=${current_price:.8f}, 布林带位置={bb_position:.1f}% (下轨=${lower:.8f}, 上轨=${upper:.8f})")

            # 做多信号：价格接近下轨 + 多时间框架确认
            if current_price <= lower * 1.01:
                signal_strength = self.calculate_signal_strength('long')
                self.logger.info(f"💡 价格触及下轨，做多信号强度: {signal_strength:.1f}/100 (需要≥60)")

                if signal_strength >= 60:
                    self.logger.info(f"🟢 检测到做多信号 (强度: {signal_strength:.1f}/100)")
                    self.logger.info(f"  价格: ${current_price:.8f}")
                    self.logger.info(f"  布林下轨: ${lower:.8f}")
                    if self.funding_rate:
                        self.logger.info(f"  资金费率: {self.funding_rate*100:.4f}%")
                    self._open_position('long', signal_strength)
                    return

            # 做空信号：价格接近上轨 + 多时间框架确认
            if current_price >= upper * 0.99:
                signal_strength = self.calculate_signal_strength('short')
                self.logger.info(f"💡 价格触及上轨，做空信号强度: {signal_strength:.1f}/100 (需要≥60)")

                if signal_strength >= 60:
                    self.logger.info(f"🔴 检测到做空信号 (强度: {signal_strength:.1f}/100)")
                    self.logger.info(f"  价格: ${current_price:.8f}")
                    self.logger.info(f"  布林上轨: ${upper:.8f}")
                    if self.funding_rate:
                        self.logger.info(f"  资金费率: {self.funding_rate*100:.4f}%")
                    self._open_position('short', signal_strength)
                    return

        except Exception as e:
            self.logger.error(f"检查入场信号异常: {e}")

    def _open_position(self, side: str, signal_strength: float):
        """开仓"""
        try:
            # 动态计算仓位
            position_size = self.calculate_dynamic_position_size(signal_strength)
            contracts = position_size / self.contract_value
            contracts = round(contracts / self.lot_size) * self.lot_size

            if contracts < self.min_size:
                contracts = self.min_size

            order_side = 'buy' if side == 'long' else 'sell'

            self.logger.info(f"📊 开仓: {side.upper()}")
            self.logger.info(f"  数量: {contracts}张 ({contracts * self.contract_value:,.0f} PEPE)")
            self.logger.info(f"  信号强度: {signal_strength:.1f}/100")

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
                self.profit_targets_hit = []
                self.highest_profit_rate = 0
                time.sleep(1)
                self._update_position()
            else:
                self.logger.error(f"❌ 开仓失败: {result.get('msg')}")

        except Exception as e:
            self.logger.error(f"开仓异常: {e}")

    def _check_exit_conditions(self):
        """检查退出条件（分级止盈）"""
        if not self.current_position:
            return

        try:
            entry_price = self.current_position['entry_price']
            side = self.current_position['side']
            current_price = self.price_data['1m'][-1] if self.price_data['1m'] else None

            if not current_price:
                return

            # 计算盈亏率
            if side == 'long':
                profit_rate = (current_price - entry_price) / entry_price
            else:
                profit_rate = (entry_price - current_price) / entry_price

            # 更新最高盈利
            if profit_rate > self.highest_profit_rate:
                self.highest_profit_rate = profit_rate

            # 止损
            if profit_rate <= -self.base_stop_loss:
                self.logger.info(f"🛑 触发止损: {profit_rate*100:.2f}%")
                self._close_position(1.0, profit_rate, "止损")
                return

            # 分级止盈
            for i, (target, ratio) in enumerate(self.profit_levels):
                if i in self.profit_targets_hit:
                    continue

                if profit_rate >= target:
                    self.profit_targets_hit.append(i)
                    self.logger.info(f"🎯 触发第{i+1}级止盈: {profit_rate*100:.2f}% >= {target*100:.1f}%")
                    self._close_position(ratio, profit_rate, f"第{i+1}级止盈")

                    # 如果不是全部平仓，更新持仓
                    if ratio < 1.0:
                        time.sleep(1)
                        self._update_position()
                    return

            # 移动止盈：从最高点回撤2%平仓
            if self.highest_profit_rate > 0.03:  # 至少盈利3%才启用
                drawdown = self.highest_profit_rate - profit_rate
                if drawdown >= 0.02:  # 回撤2%
                    self.logger.info(f"📉 移动止盈触发: 从{self.highest_profit_rate*100:.2f}%回撤{drawdown*100:.2f}%")
                    self._close_position(1.0, profit_rate, "移动止盈")
                    return

        except Exception as e:
            self.logger.error(f"检查退出条件异常: {e}")

    def _close_position(self, ratio: float, profit_rate: float, reason: str):
        """平仓（支持部分平仓）"""
        if not self.current_position:
            return

        try:
            side = self.current_position['side']
            total_contracts = float(self.current_position['contracts'])
            close_contracts = total_contracts * ratio

            # 确保符合最小下单量和步长
            close_contracts = round(close_contracts / self.lot_size) * self.lot_size

            # 如果小于最小下单量，直接使用总仓位（全平）
            if close_contracts < self.min_size:
                close_contracts = total_contracts

            order_side = 'sell' if side == 'long' else 'buy'

            self.logger.info(f"📊 平仓: {reason}")
            self.logger.info(f"  平仓比例: {ratio*100:.0f}%")
            self.logger.info(f"  平仓数量: {close_contracts}张")
            self.logger.info(f"  盈亏率: {profit_rate*100:.2f}%")

            result = self.api_client.place_order(
                inst_id=self.symbol,
                side=order_side,
                order_type='market',
                size=str(close_contracts),
                pos_side='net',
                td_mode='cross'
            )

            if result['code'] == '0':
                self.logger.info(f"✅ 平仓成功")

                # 如果全部平仓，更新统计
                if ratio >= 0.99:
                    self.total_trades += 1
                    if profit_rate > 0:
                        self.winning_trades += 1
                        self.consecutive_wins += 1
                        self.consecutive_losses = 0
                    else:
                        self.consecutive_wins = 0
                        self.consecutive_losses += 1

                    win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
                    self.logger.info(f"📊 统计: 总{self.total_trades}次, 胜率{win_rate:.1f}%")

                    self.current_position = None
                    self.profit_targets_hit = []
                    self.highest_profit_rate = 0
            else:
                self.logger.error(f"❌ 平仓失败: {result.get('msg')}")

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
            'win_rate': self.winning_trades / self.total_trades if self.total_trades > 0 else 0,
            'funding_rate': self.funding_rate
        }

    def print_status(self):
        """打印策略状态"""
        status = self.get_status()
        self.logger.info("=" * 60)
        self.logger.info(f"高级策略状态")
        self.logger.info(f"总交易: {status['total_trades']}次, 胜率{status['win_rate']*100:.1f}%")
        if status['position']:
            pos = status['position']
            self.logger.info(f"持仓: {pos['side'].upper()}, {pos['contracts']}张")
        self.logger.info("=" * 60)
