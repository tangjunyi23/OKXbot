from typing import Dict, List, Optional
from datetime import datetime, timedelta
from ..utils.logger import setup_logger


class RiskManager:
    """风险管理模块 - 增强版"""

    def __init__(self, config: Dict):
        self.config = config
        self.logger = setup_logger("RiskManager")

        # 基础风险参数
        self.max_position_size = config.get('max_position_size', 0.1)
        self.stop_loss_rate = config.get('stop_loss_rate', 0.05)
        self.take_profit_rate = config.get('take_profit_rate', 0.10)
        self.max_daily_loss = config.get('max_daily_loss', 500)
        self.max_drawdown = config.get('max_drawdown', 0.20)

        # 增强风险控制参数
        self.max_leverage = config.get('max_leverage', 10)  # 最大杠杆
        self.max_consecutive_losses = config.get('max_consecutive_losses', 5)  # 最大连续亏损次数
        self.consecutive_loss_cooldown = config.get('consecutive_loss_cooldown', 3600)  # 冷却时间(秒)
        self.max_positions = config.get('max_positions', 3)  # 最大持仓数量
        self.max_correlation_exposure = config.get('max_correlation_exposure', 0.5)  # 相关性暴露限制

        # 动态仓位调整参数
        self.win_rate_threshold = config.get('win_rate_threshold', 0.5)  # 胜率阈值
        self.reduce_size_on_loss = config.get('reduce_size_on_loss', True)  # 亏损后减仓
        self.position_scaling_factor = config.get('position_scaling_factor', 0.5)  # 仓位缩放因子

        # 交易记录
        self.daily_pnl = 0.0
        self.daily_trades = []
        self.current_date = datetime.now().date()
        self.peak_balance = 0.0
        self.current_balance = 0.0

        # 增强统计数据
        self.consecutive_losses = 0  # 连续亏损次数
        self.consecutive_wins = 0  # 连续盈利次数
        self.cooldown_until = None  # 冷却截止时间
        self.active_positions = {}  # 当前持仓 {symbol: size}
        self.hourly_trades = []  # 每小时交易记录
        self.max_hourly_trades = config.get('max_hourly_trades', 10)  # 每小时最大交易次数

    def reset_daily_stats(self):
        """重置每日统计"""
        today = datetime.now().date()
        if today != self.current_date:
            self.logger.info(f"重置每日统计 - 昨日盈亏: {self.daily_pnl:.2f} USDT, 交易次数: {len(self.daily_trades)}")
            self.daily_pnl = 0.0
            self.daily_trades = []
            self.current_date = today

    def update_balance(self, balance: float):
        """更新账户余额"""
        self.current_balance = balance
        if balance > self.peak_balance:
            self.peak_balance = balance

    def check_position_size(self, size: float) -> bool:
        """检查仓位大小是否超限"""
        if abs(size) > self.max_position_size:
            self.logger.warning(f"仓位大小 {size} 超过最大限制 {self.max_position_size}")
            return False
        return True

    def check_stop_loss(self, entry_price: float, current_price: float, side: str) -> bool:
        """
        检查是否触发止损

        Args:
            entry_price: 开仓价格
            current_price: 当前价格
            side: 方向 (long/short)

        Returns:
            是否触发止损
        """
        if side.lower() == 'long':
            loss_rate = (entry_price - current_price) / entry_price
        elif side.lower() == 'short':
            loss_rate = (current_price - entry_price) / entry_price
        else:
            return False

        if loss_rate >= self.stop_loss_rate:
            self.logger.warning(f"触发止损: 亏损率 {loss_rate:.2%}, 止损线 {self.stop_loss_rate:.2%}")
            return True

        return False

    def check_take_profit(self, entry_price: float, current_price: float, side: str) -> bool:
        """
        检查是否触发止盈

        Args:
            entry_price: 开仓价格
            current_price: 当前价格
            side: 方向 (long/short)

        Returns:
            是否触发止盈
        """
        if side.lower() == 'long':
            profit_rate = (current_price - entry_price) / entry_price
        elif side.lower() == 'short':
            profit_rate = (entry_price - current_price) / entry_price
        else:
            return False

        if profit_rate >= self.take_profit_rate:
            self.logger.info(f"触发止盈: 盈利率 {profit_rate:.2%}, 止盈线 {self.take_profit_rate:.2%}")
            return True

        return False

    def check_daily_loss_limit(self) -> bool:
        """检查是否达到每日最大亏损"""
        self.reset_daily_stats()

        if self.daily_pnl <= -self.max_daily_loss:
            self.logger.error(f"达到每日最大亏损限制: {self.daily_pnl:.2f} USDT")
            return False

        return True

    def check_max_drawdown(self) -> bool:
        """检查是否达到最大回撤"""
        if self.peak_balance == 0:
            return True

        drawdown = (self.peak_balance - self.current_balance) / self.peak_balance

        if drawdown >= self.max_drawdown:
            self.logger.error(f"达到最大回撤限制: {drawdown:.2%}")
            return False

        return True

    def can_open_position(self, size: float, symbol: str = None, leverage: int = 1) -> bool:
        """
        检查是否可以开仓 - 增强版

        Args:
            size: 仓位大小
            symbol: 交易币种
            leverage: 杠杆倍数

        Returns:
            是否可以开仓
        """
        # 检查冷却期
        if not self.check_cooldown():
            self.logger.warning("处于冷却期，暂停开仓")
            return False

        # 检查连续亏损
        if not self.check_consecutive_losses():
            self.logger.warning(f"连续亏损 {self.consecutive_losses} 次，触发保护机制")
            return False

        # 检查每小时交易频率
        if not self.check_hourly_trade_limit():
            self.logger.warning("超过每小时交易次数限制")
            return False

        # 检查持仓数量
        if not self.check_position_count():
            self.logger.warning(f"持仓数量已达上限 {self.max_positions}")
            return False

        # 检查杠杆限制
        if not self.check_leverage(leverage):
            self.logger.warning(f"杠杆 {leverage}x 超过限制 {self.max_leverage}x")
            return False

        # 检查每日亏损限制
        if not self.check_daily_loss_limit():
            return False

        # 检查最大回撤
        if not self.check_max_drawdown():
            return False

        # 检查仓位大小
        adjusted_size = self.get_adjusted_position_size(size)
        if not self.check_position_size(adjusted_size):
            return False

        return True

    def record_trade(self, pnl: float, side: str, price: float, size: float, symbol: str = None):
        """
        记录交易 - 增强版

        Args:
            pnl: 盈亏
            side: 方向
            price: 价格
            size: 数量
            symbol: 交易币种
        """
        self.reset_daily_stats()

        trade_record = {
            'timestamp': datetime.now(),
            'side': side,
            'price': price,
            'size': size,
            'pnl': pnl,
            'symbol': symbol
        }

        self.daily_trades.append(trade_record)
        self.hourly_trades.append(trade_record)
        self.daily_pnl += pnl

        # 更新连续盈亏统计
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

            # 触发连续亏损保护
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.trigger_cooldown()

        # 清理1小时前的交易记录
        one_hour_ago = datetime.now() - timedelta(hours=1)
        self.hourly_trades = [t for t in self.hourly_trades if t['timestamp'] > one_hour_ago]

        self.logger.info(f"记录交易: {side} {size} @ {price:.2f}, 盈亏: {pnl:.2f}, "
                        f"今日累计: {self.daily_pnl:.2f}, 连续: {'盈' if pnl > 0 else '亏'} {max(self.consecutive_wins, self.consecutive_losses)}")

    def get_position_size_by_risk(self, balance: float, entry_price: float, stop_loss_price: float, risk_per_trade: float = 0.02) -> float:
        """
        根据风险计算仓位大小

        Args:
            balance: 账户余额
            entry_price: 入场价格
            stop_loss_price: 止损价格
            risk_per_trade: 单笔交易风险比例（默认2%）

        Returns:
            建议仓位大小
        """
        risk_amount = balance * risk_per_trade
        price_risk = abs(entry_price - stop_loss_price)

        if price_risk == 0:
            return 0

        size = risk_amount / price_risk

        # 确保不超过最大仓位限制
        if size > self.max_position_size:
            size = self.max_position_size

        return size

    def check_cooldown(self) -> bool:
        """检查是否处于冷却期"""
        if self.cooldown_until is None:
            return True

        if datetime.now() < self.cooldown_until:
            remaining = (self.cooldown_until - datetime.now()).total_seconds()
            self.logger.warning(f"冷却期剩余: {remaining:.0f}秒")
            return False

        # 冷却期结束，重置
        self.cooldown_until = None
        self.consecutive_losses = 0
        self.logger.info("冷却期结束，恢复交易")
        return True

    def check_consecutive_losses(self) -> bool:
        """检查连续亏损次数"""
        return self.consecutive_losses < self.max_consecutive_losses

    def check_hourly_trade_limit(self) -> bool:
        """检查每小时交易频率"""
        # 清理1小时前的记录
        one_hour_ago = datetime.now() - timedelta(hours=1)
        self.hourly_trades = [t for t in self.hourly_trades if t['timestamp'] > one_hour_ago]

        if len(self.hourly_trades) >= self.max_hourly_trades:
            self.logger.warning(f"1小时内交易次数: {len(self.hourly_trades)}/{self.max_hourly_trades}")
            return False
        return True

    def check_position_count(self) -> bool:
        """检查持仓数量"""
        active_count = sum(1 for size in self.active_positions.values() if size != 0)
        return active_count < self.max_positions

    def check_leverage(self, leverage: int) -> bool:
        """检查杠杆倍数"""
        return leverage <= self.max_leverage

    def trigger_cooldown(self):
        """触发冷却期"""
        self.cooldown_until = datetime.now() + timedelta(seconds=self.consecutive_loss_cooldown)
        self.logger.error(f"🚨 触发连续亏损保护！冷却时间: {self.consecutive_loss_cooldown}秒")
        self.logger.error(f"冷却截止时间: {self.cooldown_until.strftime('%Y-%m-%d %H:%M:%S')}")

    def get_adjusted_position_size(self, base_size: float) -> float:
        """
        根据历史表现动态调整仓位大小

        Args:
            base_size: 基础仓位大小

        Returns:
            调整后的仓位大小
        """
        if not self.reduce_size_on_loss or len(self.daily_trades) < 5:
            return base_size

        # 计算最近的胜率
        recent_trades = self.daily_trades[-10:] if len(self.daily_trades) >= 10 else self.daily_trades
        win_count = sum(1 for t in recent_trades if t['pnl'] > 0)
        win_rate = win_count / len(recent_trades) if recent_trades else 0.5

        # 如果胜率低于阈值，减小仓位
        if win_rate < self.win_rate_threshold:
            adjustment = self.position_scaling_factor
            adjusted_size = base_size * adjustment
            self.logger.info(f"胜率 {win_rate:.2%} 低于阈值 {self.win_rate_threshold:.2%}，"
                           f"仓位调整: {base_size:.4f} -> {adjusted_size:.4f}")
            return adjusted_size

        # 如果连续盈利，可以适当增加仓位（但不超过最大限制）
        if self.consecutive_wins >= 3:
            adjustment = min(1.2, 2.0 - self.position_scaling_factor)
            adjusted_size = min(base_size * adjustment, self.max_position_size)
            self.logger.info(f"连续盈利 {self.consecutive_wins} 次，"
                           f"仓位调整: {base_size:.4f} -> {adjusted_size:.4f}")
            return adjusted_size

        return base_size

    def update_position(self, symbol: str, size: float):
        """
        更新持仓信息

        Args:
            symbol: 币种
            size: 持仓大小 (0表示平仓)
        """
        if size == 0 and symbol in self.active_positions:
            del self.active_positions[symbol]
            self.logger.info(f"移除持仓: {symbol}")
        else:
            self.active_positions[symbol] = size
            self.logger.info(f"更新持仓: {symbol} = {size}")

    def get_total_exposure(self) -> float:
        """获取总暴露度（所有持仓价值之和）"""
        return sum(abs(size) for size in self.active_positions.values())

    def is_emergency_stop(self) -> bool:
        """
        检查是否需要紧急停止交易

        触发条件：
        1. 达到最大回撤
        2. 达到每日最大亏损
        3. 处于冷却期且连续亏损严重

        Returns:
            是否需要紧急停止
        """
        # 检查最大回撤
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
            if drawdown >= self.max_drawdown:
                self.logger.error(f"🚨 紧急停止：达到最大回撤 {drawdown:.2%}")
                return True

        # 检查每日最大亏损
        if self.daily_pnl <= -self.max_daily_loss:
            self.logger.error(f"🚨 紧急停止：达到每日最大亏损 {self.daily_pnl:.2f} USDT")
            return True

        # 检查连续亏损+冷却期
        if self.cooldown_until and self.consecutive_losses >= self.max_consecutive_losses:
            self.logger.error(f"🚨 紧急停止：连续亏损 {self.consecutive_losses} 次，处于冷却期")
            return True

        return False

    def get_daily_stats(self) -> Dict:
        """获取每日统计数据"""
        self.reset_daily_stats()

        return {
            'date': self.current_date,
            'daily_pnl': self.daily_pnl,
            'trade_count': len(self.daily_trades),
            'win_count': sum(1 for t in self.daily_trades if t['pnl'] > 0),
            'loss_count': sum(1 for t in self.daily_trades if t['pnl'] < 0),
            'current_balance': self.current_balance,
            'peak_balance': self.peak_balance,
            'drawdown': (self.peak_balance - self.current_balance) / self.peak_balance if self.peak_balance > 0 else 0,
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses,
            'active_positions': len(self.active_positions),
            'hourly_trades': len(self.hourly_trades)
        }

    def get_risk_report(self) -> str:
        """生成风险报告 - 增强版"""
        stats = self.get_daily_stats()

        win_rate = stats['win_count'] / stats['trade_count'] if stats['trade_count'] > 0 else 0

        # 冷却状态
        cooldown_status = "否"
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            remaining = (self.cooldown_until - datetime.now()).total_seconds()
            cooldown_status = f"是 (剩余 {remaining:.0f}秒)"

        report = f"""
========== 风险管理报告（增强版） ==========
📅 日期: {stats['date']}
💰 今日盈亏: {stats['daily_pnl']:.2f} USDT
📊 交易次数: {stats['trade_count']} (1小时内: {stats['hourly_trades']})
🎯 胜率: {win_rate:.2%}
💵 当前余额: {stats['current_balance']:.2f} USDT
📈 峰值余额: {stats['peak_balance']:.2f} USDT
📉 回撤: {stats['drawdown']:.2%}
🔥 连续盈利: {stats['consecutive_wins']} 次
❄️  连续亏损: {stats['consecutive_losses']} 次
📦 持仓数量: {stats['active_positions']} / {self.max_positions}
🛡️  冷却状态: {cooldown_status}
⚠️  紧急停止: {'是' if self.is_emergency_stop() else '否'}
==========================================
"""
        return report
