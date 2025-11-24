import time
from typing import Dict, List, Optional
from .base_strategy import BaseStrategy
from ..utils.helpers import calculate_grid_levels, calculate_position_size
from ..utils.logger import setup_logger


class GridStrategy(BaseStrategy):
    """网格交易策略"""

    def __init__(self, config: Dict, api_client):
        super().__init__(config)
        self.api_client = api_client
        self.logger = setup_logger("GridStrategy")

        # 策略参数
        self.symbol = config.get('symbol', 'BTC-USDT-SWAP')
        self.grid_num = config.get('grid_num', 10)
        self.price_upper = config.get('price_upper', 50000)
        self.price_lower = config.get('price_lower', 40000)
        self.investment = config.get('investment', 1000)
        self.min_profit_rate = config.get('min_profit_rate', 0.005)

        # 获取合约信息
        self.contract_value = 1  # 默认合约面值
        self.min_size = 0.01  # 默认最小下单量
        self.lot_size = 0.01  # 默认下单精度
        try:
            instruments = self.api_client.get_instruments('SWAP')
            if instruments['code'] == '0':
                for inst in instruments['data']:
                    if inst['instId'] == self.symbol:
                        self.contract_value = float(inst.get('ctVal', 1))
                        self.min_size = float(inst.get('minSz', 0.01))
                        self.lot_size = float(inst.get('lotSz', 0.01))
                        break
        except Exception as e:
            self.logger.warning(f"获取合约信息失败，使用默认值: {e}")

        # 计算网格档位
        self.grid_levels = calculate_grid_levels(
            self.price_upper,
            self.price_lower,
            self.grid_num
        )

        # 计算每个网格的数量（币数量）
        mid_price = (self.price_upper + self.price_lower) / 2
        coin_amount = calculate_position_size(
            self.investment,
            mid_price,
            self.grid_num
        )

        # 转换为合约张数
        self.per_grid_size = coin_amount / self.contract_value

        # 四舍五入到合约精度
        self.per_grid_size = round(self.per_grid_size / self.lot_size) * self.lot_size

        # 确保满足最小下单量
        if self.per_grid_size < self.min_size:
            self.per_grid_size = self.min_size
            self.logger.warning(f"每格张数小于最小值，已调整为: {self.min_size}")

        # 网格状态
        self.grid_orders = {}  # 存储每个网格的订单
        self.filled_grids = set()  # 已成交的网格
        self.current_price = None

        self.logger.info(f"初始化网格策略:")
        self.logger.info(f"交易对: {self.symbol}")
        self.logger.info(f"合约面值: {self.contract_value}")
        self.logger.info(f"最小下单量: {self.min_size} 张")
        self.logger.info(f"价格范围: {self.price_lower} - {self.price_upper}")
        self.logger.info(f"网格数量: {self.grid_num}")
        self.logger.info(f"每格张数: {self.per_grid_size:.4f}")
        self.logger.info(f"网格档位: {[f'{level:.2f}' for level in self.grid_levels]}")

    def initialize_grid(self):
        """初始化网格订单"""
        try:
            # 获取当前价格
            ticker = self.api_client.get_ticker(self.symbol)
            if ticker['code'] == '0' and ticker['data']:
                self.current_price = float(ticker['data'][0]['last'])
                self.logger.info(f"当前价格: {self.current_price:.2f}")

                # 在当前价格以下挂买单，以上挂卖单
                for i, price in enumerate(self.grid_levels):
                    if price < self.current_price:
                        # 挂买单
                        self._place_grid_order(i, price, 'buy')
                    elif price > self.current_price:
                        # 挂卖单
                        self._place_grid_order(i, price, 'sell')

                self.logger.info(f"网格初始化完成，共挂 {len(self.grid_orders)} 个订单")

        except Exception as e:
            self.logger.error(f"初始化网格失败: {e}")

    def _place_grid_order(self, grid_index: int, price: float, side: str):
        """下网格订单"""
        try:
            result = self.api_client.place_order(
                inst_id=self.symbol,
                side=side,
                order_type='limit',
                size=str(self.per_grid_size),
                price=str(price),
                pos_side='net',
                td_mode='cross'
            )

            if result['code'] == '0' and result['data']:
                order_id = result['data'][0]['ordId']
                self.grid_orders[grid_index] = {
                    'order_id': order_id,
                    'price': price,
                    'side': side,
                    'size': self.per_grid_size,
                    'status': 'pending'
                }
                self.logger.info(f"下网格订单: 档位{grid_index}, {side} @ {price:.2f}, 订单ID: {order_id}")
            else:
                self.logger.error(f"下单失败: {result.get('msg', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"下网格订单异常: {e}")

    def on_tick(self, ticker_data: Dict):
        """处理行情更新"""
        try:
            if not ticker_data:
                return

            # 更新当前价格
            last_price = float(ticker_data[0].get('last', 0))
            if last_price > 0:
                self.current_price = last_price

        except Exception as e:
            self.logger.error(f"处理行情数据失败: {e}")

    def on_order_update(self, order_data: Dict):
        """处理订单更新"""
        try:
            if not order_data:
                return

            for order in order_data:
                order_id = order.get('ordId')
                state = order.get('state')

                # 查找该订单对应的网格
                grid_index = None
                for idx, grid_order in self.grid_orders.items():
                    if grid_order['order_id'] == order_id:
                        grid_index = idx
                        break

                if grid_index is None:
                    continue

                # 订单完全成交
                if state == 'filled':
                    self._handle_filled_order(grid_index, order)

                # 订单取消
                elif state == 'canceled':
                    self.logger.warning(f"网格订单被取消: 档位{grid_index}")
                    if grid_index in self.grid_orders:
                        del self.grid_orders[grid_index]

        except Exception as e:
            self.logger.error(f"处理订单更新失败: {e}")

    def _handle_filled_order(self, grid_index: int, order: Dict):
        """处理已成交订单"""
        try:
            grid_order = self.grid_orders.get(grid_index)
            if not grid_order:
                return

            filled_side = grid_order['side']
            filled_price = grid_order['price']

            self.logger.info(f"网格订单成交: 档位{grid_index}, {filled_side} @ {filled_price:.2f}")

            # 标记该网格已成交
            self.filled_grids.add(grid_index)

            # 删除已成交的订单
            del self.grid_orders[grid_index]

            # 在相邻档位下反向订单
            if filled_side == 'buy':
                # 买单成交后，在上一档挂卖单
                if grid_index + 1 < len(self.grid_levels):
                    next_price = self.grid_levels[grid_index + 1]
                    # 确保利润率满足最小要求
                    profit_rate = (next_price - filled_price) / filled_price
                    if profit_rate >= self.min_profit_rate:
                        self._place_grid_order(grid_index + 1, next_price, 'sell')

            elif filled_side == 'sell':
                # 卖单成交后，在下一档挂买单
                if grid_index - 1 >= 0:
                    next_price = self.grid_levels[grid_index - 1]
                    # 确保利润率满足最小要求
                    profit_rate = (filled_price - next_price) / next_price
                    if profit_rate >= self.min_profit_rate:
                        self._place_grid_order(grid_index - 1, next_price, 'buy')

        except Exception as e:
            self.logger.error(f"处理成交订单失败: {e}")

    def generate_signals(self) -> List[Dict]:
        """生成交易信号"""
        # 网格策略不需要主动生成信号，由订单成交驱动
        return []

    def cancel_all_orders(self):
        """取消所有网格订单"""
        self.logger.info("取消所有网格订单...")
        for grid_index, grid_order in list(self.grid_orders.items()):
            try:
                result = self.api_client.cancel_order(
                    inst_id=self.symbol,
                    ord_id=grid_order['order_id']
                )
                if result['code'] == '0':
                    self.logger.info(f"取消订单成功: 档位{grid_index}, 订单ID: {grid_order['order_id']}")
                else:
                    self.logger.error(f"取消订单失败: {result.get('msg', 'Unknown error')}")
            except Exception as e:
                self.logger.error(f"取消订单异常: {e}")

        self.grid_orders.clear()

    def get_grid_status(self) -> Dict:
        """获取网格状态"""
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'grid_num': self.grid_num,
            'price_range': [self.price_lower, self.price_upper],
            'pending_orders': len(self.grid_orders),
            'filled_grids': len(self.filled_grids),
            'grid_orders': self.grid_orders
        }

    def print_grid_status(self):
        """打印网格状态"""
        status = self.get_grid_status()
        self.logger.info("=" * 50)
        self.logger.info(f"交易对: {status['symbol']}")
        self.logger.info(f"当前价格: {status['current_price']:.2f}")
        self.logger.info(f"价格范围: {status['price_range'][0]} - {status['price_range'][1]}")
        self.logger.info(f"网格数量: {status['grid_num']}")
        self.logger.info(f"挂单数量: {status['pending_orders']}")
        self.logger.info(f"已成交网格: {status['filled_grids']}")
        self.logger.info("=" * 50)
