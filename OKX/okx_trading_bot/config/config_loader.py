import yaml
import os
from typing import Any, Dict


class Config:
    """配置加载器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config: Dict[str, Any] = yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号分隔的嵌套路径"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def get_okx_config(self) -> Dict[str, str]:
        """获取OKX API配置"""
        return self.config.get('okx', {})

    def get_trading_config(self) -> Dict[str, Any]:
        """获取交易配置"""
        return self.config.get('trading', {})

    def get_grid_config(self) -> Dict[str, Any]:
        """获取网格策略配置"""
        return self.config.get('grid_strategy', {})

    def get_risk_config(self) -> Dict[str, Any]:
        """获取风险管理配置"""
        return self.config.get('risk_management', {})

    def get_backtest_config(self) -> Dict[str, Any]:
        """获取回测配置"""
        return self.config.get('backtest', {})

    def get_notification_config(self) -> Dict[str, Any]:
        """获取通知配置"""
        return self.config.get('notification', {})
