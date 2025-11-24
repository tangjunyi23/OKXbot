"""
做多做空仓位策略

基于市场趋势进行做多或做空操作
"""
import time
from typing import Dict, List, Optional
from .base_strategy import BaseStrategy
from ..utils.logger import setup_logger


class PositionStrategy(BaseStrategy):
    """做多做空仓位策略"""

    def __init__(self, config: Dict, api_client):
        super().__init__(config)
        self.api_client = api_client
        self.logger = setup_logger("PositionStrategy")

        # 策略参数
        self.symbol = config.get('symbol', 'ETH-USDT-SWAP')
        self.position_size = config.get('position_size', 0.1)  # 每次开仓数量（ETH）
        self.stop_loss_rate = config.get('stop_loss_rate', 0.03)  # 止损率 3%
        self.take_profit_rate = config.get('take_profit_rate', 0.05)  # 止盈率 5%
        self.leverage = config.get('leverage', 5)

        # 获取合约信息
        self.contract_value = 0.01  # ETH-USDT-SWAP 合约面值
        self.min_size = 1  # 最小下单量（张）
        self.lot_size = 1  # 下单精度（张）

        try:
            instruments = self.api_client.get_instruments('SWAP')
            if instruments['code'] == '0':
                for inst in instruments['data']:
                    if inst['instId'] == self.symbol:
                        self.contract_value = float(inst.get('ctVal', 0.01))
                        self.min_size = float(inst.get('minSz', 1))
                        self.lot_size = float(inst.get('lotSz', 1))
                        self.logger.info(f"合约面值: {self.contract_value}, 最小下单量: {self.min_size}")
                        break
        except Exception as e:
            self.logger.warning(f"获取合约信息失败，使用默认值: {e}")

        # 当前状态
        self.current_price = None
        self.current_position = None  # {'side': 'long'/'short', 'size': float, 'entry_price': float}
        self.last_check_time = 0

        # 简单移动平均线参数
        self.ma_short_period = config.get('ma_short_period', 5)
        self.ma_long_period = config.get('ma_long_period', 20)
        self.price_history = []  # 存储历史价格用于计算MA

        self.logger.info(f"初始化做多做空策略:")
        self.logger.info(f"交易对: {self.symbol}")
        self.logger.info(f"每次开仓数量: {self.position_size} ETH")
        self.logger.info(f"止损率: {self.stop_loss_rate * 100}%")
        self.logger.info(f"止盈率: {self.take_profit_rate * 100}%")
        self.logger.info(f"杠杆: {self.leverage}x")

    def on_tick(self, ticker_data: Dict):
        """处理行情更新"""
        try:
            if not ticker_data:
                return

            # 更新当前价格
            last_price = float(ticker_data[0].get('last', 0))
            if last_price <= 0:
                return

            self.current_price = last_price

            # 添加到价格历史
            self.price_history.append(last_price)
            if len(self.price_history) > self.ma_long_period:
                self.price_history.pop(0)

            # 每30秒检查一次
            current_time = time.time()
            if current_time - self.last_check_time < 30:
                return
            self.last_check_time = current_time

            # 检查当前持仓
            self._update_position()

            # 如果有持仓，检查止盈止损
            if self.current_position:
                self._check_exit_conditions()
            else:
                # 没有持仓，检查入场信号
                self._check_entry_signals()

        except Exception as e:
            self.logger.error(f"处理行情数据失败: {e}")

    def _update_position(self):
        """更新当前持仓信息"""
        try:
            positions = self.api_client.get_positions(inst_id=self.symbol)
            if positions['code'] == '0' and positions['data']:
                for pos in positions['data']:
                    pos_size = float(pos.get('pos', 0))
                    if pos_size != 0:
                        avg_price = float(pos.get('avgPx', 0))
                        # pos为正数表示做多，负数表示做空
                        side = 'long' if pos_size > 0 else 'short'
                        self.current_position = {
                            'side': side,
                            'size': abs(pos_size),
                            'entry_price': avg_price,
                            'contracts': abs(pos_size)
                        }
                        return
                # 没有持仓
                self.current_position = None
            else:
                self.current_position = None
        except Exception as e:
            self.logger.error(f"更新持仓失败: {e}")

    def _calculate_ma(self, period: int) -> Optional[float]:
        """计算移动平均线"""
        if len(self.price_history) < period:
            return None
        return sum(self.price_history[-period:]) / period

    def _check_entry_signals(self):
        """检查入场信号"""
        try:
            # 需要足够的历史数据
            if len(self.price_history) < self.ma_long_period:
                return

            ma_short = self._calculate_ma(self.ma_short_period)
            ma_long = self._calculate_ma(self.ma_long_period)

            if ma_short is None or ma_long is None:
                return

            # 短期MA向上突破长期MA，做多信号
            if ma_short > ma_long and self.current_price > ma_short:
                self.logger.info(f"检测到做多信号: 价格={self.current_price:.2f}, MA{self.ma_short_period}={ma_short:.2f}, MA{self.ma_long_period}={ma_long:.2f}")
                self._open_position('long')

            # 短期MA向下突破长期MA，做空信号
            elif ma_short < ma_long and self.current_price < ma_short:
                self.logger.info(f"检测到做空信号: 价格={self.current_price:.2f}, MA{self.ma_short_period}={ma_short:.2f}, MA{self.ma_long_period}={ma_long:.2f}")
                self._open_position('short')

        except Exception as e:
            self.logger.error(f"检查入场信号失败: {e}")

    def _check_exit_conditions(self):
        """检查止盈止损条件"""
        if not self.current_position:
            return

        try:
            entry_price = self.current_position['entry_price']
            side = self.current_position['side']

            if side == 'long':
                # 做多：价格上涨达到止盈，或下跌达到止损
                profit_rate = (self.current_price - entry_price) / entry_price

                if profit_rate >= self.take_profit_rate:
                    self.logger.info(f"触发止盈: 入场价={entry_price:.2f}, 当前价={self.current_price:.2f}, 收益率={profit_rate*100:.2f}%")
                    self._close_position()
                elif profit_rate <= -self.stop_loss_rate:
                    self.logger.info(f"触发止损: 入场价={entry_price:.2f}, 当前价={self.current_price:.2f}, 收益率={profit_rate*100:.2f}%")
                    self._close_position()

            elif side == 'short':
                # 做空：价格下跌达到止盈，或上涨达到止损
                profit_rate = (entry_price - self.current_price) / entry_price

                if profit_rate >= self.take_profit_rate:
                    self.logger.info(f"触发止盈: 入场价={entry_price:.2f}, 当前价={self.current_price:.2f}, 收益率={profit_rate*100:.2f}%")
                    self._close_position()
                elif profit_rate <= -self.stop_loss_rate:
                    self.logger.info(f"触发止损: 入场价={entry_price:.2f}, 当前价={self.current_price:.2f}, 收益率={profit_rate*100:.2f}%")
                    self._close_position()

        except Exception as e:
            self.logger.error(f"检查止盈止损失败: {e}")

    def _open_position(self, side: str):
        """开仓"""
        try:
            # 计算合约张数
            contracts = self.position_size / self.contract_value

            # 调整为合约精度的整数倍
            contracts = round(contracts / self.lot_size) * self.lot_size

            # 确保满足最小下单量
            if contracts < self.min_size:
                contracts = self.min_size

            # 做多：买入开多；做空：卖出开空
            order_side = 'buy' if side == 'long' else 'sell'

            self.logger.info(f"开仓: {side}, 数量={contracts}张 ({contracts * self.contract_value:.4f} ETH)")

            result = self.api_client.place_order(
                inst_id=self.symbol,
                side=order_side,
                order_type='market',  # 市价单
                size=str(contracts),
                pos_side='net',
                td_mode='cross'
            )

            if result['code'] == '0' and result['data']:
                order_id = result['data'][0]['ordId']
                self.logger.info(f"开仓成功: {side}, 订单ID: {order_id}")
                # 更新持仓
                time.sleep(1)  # 等待订单成交
                self._update_position()
            else:
                self.logger.error(f"开仓失败: {result.get('msg', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"开仓异常: {e}")

    def _close_position(self):
        """平仓"""
        if not self.current_position:
            return

        try:
            side = self.current_position['side']
            contracts = int(self.current_position['contracts'])

            # 做多平仓：卖出；做空平仓：买入
            order_side = 'sell' if side == 'long' else 'buy'

            self.logger.info(f"平仓: {side}, 数量={contracts}张")

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
                self.logger.info(f"平仓成功: 订单ID: {order_id}")
                # 清除持仓
                self.current_position = None
            else:
                self.logger.error(f"平仓失败: {result.get('msg', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"平仓异常: {e}")

    def on_order_update(self, order_data: Dict):
        """处理订单更新"""
        try:
            if not order_data:
                return

            for order in order_data:
                order_id = order.get('ordId')
                state = order.get('state')
                self.logger.info(f"订单更新: ID={order_id}, 状态={state}")

        except Exception as e:
            self.logger.error(f"处理订单更新失败: {e}")

    def generate_signals(self) -> List[Dict]:
        """生成交易信号"""
        # 此策略由行情驱动，不需要主动生成信号
        return []

    def cancel_all_orders(self):
        """取消所有订单（策略使用市价单，一般不需要）"""
        self.logger.info("策略使用市价单，无需取消订单")

    def close_all_positions(self):
        """平掉所有持仓"""
        self.logger.info("正在平掉所有持仓...")
        self._update_position()
        if self.current_position:
            self._close_position()

    def get_status(self) -> Dict:
        """获取策略状态"""
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'position': self.current_position,
            'ma_short': self._calculate_ma(self.ma_short_period),
            'ma_long': self._calculate_ma(self.ma_long_period)
        }

    def print_status(self):
        """打印策略状态"""
        status = self.get_status()
        self.logger.info("=" * 60)
        self.logger.info(f"交易对: {status['symbol']}")
        self.logger.info(f"当前价格: {status['current_price']:.2f}" if status['current_price'] else "当前价格: N/A")

        if status['ma_short']:
            self.logger.info(f"MA{self.ma_short_period}: {status['ma_short']:.2f}")
        if status['ma_long']:
            self.logger.info(f"MA{self.ma_long_period}: {status['ma_long']:.2f}")

        if status['position']:
            pos = status['position']
            self.logger.info(f"当前持仓: {pos['side'].upper()}")
            self.logger.info(f"持仓数量: {pos['contracts']} 张 ({pos['size'] * self.contract_value:.4f} ETH)")
            self.logger.info(f"入场价格: {pos['entry_price']:.2f}")
            if self.current_price:
                if pos['side'] == 'long':
                    pnl_rate = (self.current_price - pos['entry_price']) / pos['entry_price']
                else:
                    pnl_rate = (pos['entry_price'] - self.current_price) / pos['entry_price']
                self.logger.info(f"浮动盈亏: {pnl_rate*100:.2f}%")
        else:
            self.logger.info("当前持仓: 无")

        self.logger.info("=" * 60)
