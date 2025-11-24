from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, config: Dict):
        self.config = config
        self.positions = {}
        self.pending_orders = {}

    @abstractmethod
    def on_tick(self, ticker_data: Dict):
        """
        处理行情数据

        Args:
            ticker_data: 行情数据
        """
        pass

    @abstractmethod
    def on_order_update(self, order_data: Dict):
        """
        处理订单更新

        Args:
            order_data: 订单数据
        """
        pass

    @abstractmethod
    def generate_signals(self) -> List[Dict]:
        """
        生成交易信号

        Returns:
            交易信号列表
        """
        pass

    def update_position(self, position_data: Dict):
        """更新持仓信息"""
        inst_id = position_data.get('instId')
        if inst_id:
            self.positions[inst_id] = position_data

    def update_order(self, order_data: Dict):
        """更新订单信息"""
        order_id = order_data.get('ordId')
        if order_id:
            self.pending_orders[order_id] = order_data

    def get_position(self, inst_id: str) -> Optional[Dict]:
        """获取指定产品的持仓"""
        return self.positions.get(inst_id)

    def get_order(self, order_id: str) -> Optional[Dict]:
        """获取指定订单"""
        return self.pending_orders.get(order_id)
