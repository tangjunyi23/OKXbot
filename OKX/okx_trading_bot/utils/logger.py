import logging
import os
from datetime import datetime


def setup_logger(name: str, log_file: str = None, level: str = "INFO") -> logging.Logger:
    """设置日志记录器"""

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        # 创建logs目录
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class TradingLogger:
    """交易日志记录器，记录交易信号和执行情况"""

    def __init__(self, log_file: str = "logs/trading.log"):
        self.logger = setup_logger("TradingLogger", log_file)

    def log_signal(self, signal_type: str, price: float, reason: str):
        """记录交易信号"""
        self.logger.info(f"[SIGNAL] {signal_type} at {price:.2f} - {reason}")

    def log_order(self, order_id: str, side: str, price: float, size: float, status: str):
        """记录订单执行"""
        self.logger.info(f"[ORDER] {order_id} - {side} {size} @ {price:.2f} - Status: {status}")

    def log_position(self, symbol: str, size: float, entry_price: float, pnl: float):
        """记录持仓信息"""
        self.logger.info(f"[POSITION] {symbol} - Size: {size}, Entry: {entry_price:.2f}, PnL: {pnl:.2f}")

    def log_error(self, error_msg: str, exception: Exception = None):
        """记录错误信息"""
        if exception:
            self.logger.error(f"[ERROR] {error_msg} - {str(exception)}", exc_info=True)
        else:
            self.logger.error(f"[ERROR] {error_msg}")

    def log_performance(self, metrics: dict):
        """记录策略性能指标"""
        self.logger.info(f"[PERFORMANCE] {metrics}")
