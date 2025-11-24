import math
from typing import List, Tuple
from decimal import Decimal, ROUND_DOWN


def format_number(number: float, precision: int = 8) -> str:
    """格式化数字，去除科学计数法"""
    return f"{number:.{precision}f}".rstrip('0').rstrip('.')


def calculate_grid_levels(price_upper: float, price_lower: float, grid_num: int) -> List[float]:
    """
    计算等差网格价格档位

    Args:
        price_upper: 价格上限
        price_lower: 价格下限
        grid_num: 网格数量

    Returns:
        价格档位列表
    """
    if grid_num < 2:
        raise ValueError("网格数量必须大于等于2")

    if price_upper <= price_lower:
        raise ValueError("价格上限必须大于价格下限")

    step = (price_upper - price_lower) / (grid_num - 1)
    levels = [price_lower + i * step for i in range(grid_num)]

    return levels


def calculate_geometric_grid_levels(price_upper: float, price_lower: float, grid_num: int) -> List[float]:
    """
    计算等比网格价格档位（适合波动较大的市场）

    Args:
        price_upper: 价格上限
        price_lower: 价格下限
        grid_num: 网格数量

    Returns:
        价格档位列表
    """
    if grid_num < 2:
        raise ValueError("网格数量必须大于等于2")

    if price_upper <= price_lower:
        raise ValueError("价格上限必须大于价格下限")

    ratio = (price_upper / price_lower) ** (1 / (grid_num - 1))
    levels = [price_lower * (ratio ** i) for i in range(grid_num)]

    return levels


def calculate_position_size(investment: float, price: float, grid_num: int) -> float:
    """
    计算每个网格的下单数量

    Args:
        investment: 总投资金额
        price: 当前价格
        grid_num: 网格数量

    Returns:
        每个网格的下单数量
    """
    total_quantity = investment / price
    per_grid_quantity = total_quantity / grid_num

    return per_grid_quantity


def round_down(value: float, decimals: int) -> float:
    """向下取整到指定小数位"""
    multiplier = 10 ** decimals
    return math.floor(value * multiplier) / multiplier


def calculate_pnl(entry_price: float, current_price: float, size: float, side: str) -> float:
    """
    计算盈亏

    Args:
        entry_price: 开仓价格
        current_price: 当前价格
        size: 持仓数量
        side: 方向 (long/short)

    Returns:
        盈亏金额
    """
    if side.lower() == 'long':
        pnl = (current_price - entry_price) * size
    elif side.lower() == 'short':
        pnl = (entry_price - current_price) * size
    else:
        raise ValueError(f"Invalid side: {side}")

    return pnl


def calculate_pnl_rate(entry_price: float, current_price: float, side: str) -> float:
    """
    计算收益率

    Args:
        entry_price: 开仓价格
        current_price: 当前价格
        side: 方向 (long/short)

    Returns:
        收益率
    """
    if side.lower() == 'long':
        rate = (current_price - entry_price) / entry_price
    elif side.lower() == 'short':
        rate = (entry_price - current_price) / entry_price
    else:
        raise ValueError(f"Invalid side: {side}")

    return rate
