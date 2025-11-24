import hmac
import base64
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from functools import wraps
import requests
from urllib.parse import urlencode


class RateLimiter:
    """API请求频率限制器"""

    def __init__(self, max_calls: int = 10, period: float = 1.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def wait(self):
        """等待直到可以进行下一次调用"""
        with self.lock:
            now = time.time()
            # 移除过期的调用记录
            self.calls = [t for t in self.calls if now - t < self.period]

            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)

            self.calls.append(time.time())


def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(current_delay)
                        current_delay *= backoff

            raise last_exception
        return wrapper
    return decorator


class OKXClient:
    """OKX REST API 客户端"""

    def __init__(self, api_key: str, secret_key: str, passphrase: str, is_simulated: bool = True, proxy: str = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_simulated = is_simulated

        # API基础URL
        self.base_url = "https://www.okx.com"

        # 设置请求头
        self.headers = {
            'Content-Type': 'application/json',
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
        }

        # 如果是模拟盘，添加模拟盘标识
        if self.is_simulated:
            self.headers['x-simulated-trading'] = '1'

        # 设置代理
        self.proxies = None
        if proxy:
            self.proxies = {
                'http': proxy,
                'https': proxy
            }

        # 频率限制器 - 按OKX规则: 私有接口 10次/秒
        self.rate_limiter = RateLimiter(max_calls=10, period=1.0)

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """生成签名"""
        message = timestamp + method + request_path + body
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        signature = base64.b64encode(mac.digest()).decode()
        return signature

    @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
    def _request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict:
        """发送HTTP请求（带频率限制和自动重试）"""
        # 应用频率限制
        self.rate_limiter.wait()

        url = self.base_url + endpoint

        # 生成时间戳
        timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'

        # 构建请求路径
        request_path = endpoint
        if params:
            query_string = urlencode(params)
            request_path = f"{endpoint}?{query_string}"

        # 构建请求体
        body = ''
        if data:
            body = json.dumps(data)

        # 生成签名
        signature = self._generate_signature(timestamp, method, request_path, body)

        # 设置请求头
        headers = self.headers.copy()
        headers['OK-ACCESS-SIGN'] = signature
        headers['OK-ACCESS-TIMESTAMP'] = timestamp

        # 发送请求
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, proxies=self.proxies, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, proxies=self.proxies, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            result = response.json()

            # 检查API返回的错误码 - 频率限制错误码50011需要重试
            if result.get('code') == '50011':
                raise Exception("Rate limit exceeded, will retry...")

            if result.get('code') != '0':
                raise Exception(f"API Error: {result.get('msg', 'Unknown error')}")

            return result

        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    # ==================== 市场数据接口 ====================

    def get_ticker(self, inst_id: str) -> Dict:
        """获取单个产品行情信息"""
        endpoint = '/api/v5/market/ticker'
        params = {'instId': inst_id}
        return self._request('GET', endpoint, params=params)

    def get_tickers(self, inst_type: str = 'SWAP') -> Dict:
        """获取所有产品行情信息"""
        endpoint = '/api/v5/market/tickers'
        params = {'instType': inst_type}
        return self._request('GET', endpoint, params=params)

    def get_candles(self, inst_id: str, bar: str = '1H', limit: int = 100) -> Dict:
        """
        获取K线数据

        Args:
            inst_id: 产品ID
            bar: 时间粒度 (1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M)
            limit: 返回数量，最多300
        """
        endpoint = '/api/v5/market/candles'
        params = {
            'instId': inst_id,
            'bar': bar,
            'limit': str(limit)
        }
        return self._request('GET', endpoint, params=params)

    def get_orderbook(self, inst_id: str, depth: int = 5) -> Dict:
        """获取深度数据"""
        endpoint = '/api/v5/market/books'
        params = {
            'instId': inst_id,
            'sz': str(depth)
        }
        return self._request('GET', endpoint, params=params)

    # ==================== 账户接口 ====================

    def get_balance(self, ccy: str = None) -> Dict:
        """获取账户余额"""
        endpoint = '/api/v5/account/balance'
        params = {}
        if ccy:
            params['ccy'] = ccy
        return self._request('GET', endpoint, params=params)

    def get_positions(self, inst_type: str = 'SWAP', inst_id: str = None) -> Dict:
        """获取持仓信息"""
        endpoint = '/api/v5/account/positions'
        params = {'instType': inst_type}
        if inst_id:
            params['instId'] = inst_id
        return self._request('GET', endpoint, params=params)

    def set_leverage(self, inst_id: str, lever: int, mgn_mode: str = 'cross', pos_side: str = 'net') -> Dict:
        """
        设置杠杆倍数

        Args:
            inst_id: 产品ID
            lever: 杠杆倍数
            mgn_mode: 保证金模式 (cross=全仓, isolated=逐仓)
            pos_side: 持仓方向 (net=单向, long=双向做多, short=双向做空)
        """
        endpoint = '/api/v5/account/set-leverage'
        data = {
            'instId': inst_id,
            'lever': str(lever),
            'mgnMode': mgn_mode,
            'posSide': pos_side
        }
        return self._request('POST', endpoint, data=data)

    # ==================== 交易接口 ====================

    def place_order(self, inst_id: str, side: str, order_type: str, size: str,
                   price: str = None, pos_side: str = 'net', td_mode: str = 'cross') -> Dict:
        """
        下单

        Args:
            inst_id: 产品ID
            side: 订单方向 (buy=买, sell=卖)
            order_type: 订单类型 (market=市价, limit=限价)
            size: 委托数量
            price: 委托价格 (限价单必填)
            pos_side: 持仓方向 (net=单向, long=双向做多, short=双向做空)
            td_mode: 交易模式 (cross=全仓, isolated=逐仓, cash=非保证金)
        """
        endpoint = '/api/v5/trade/order'
        data = {
            'instId': inst_id,
            'tdMode': td_mode,
            'side': side,
            'ordType': order_type,
            'sz': size
        }

        # 只在双向持仓模式下传递 posSide
        if pos_side and pos_side != 'net':
            data['posSide'] = pos_side

        if order_type == 'limit' and price:
            data['px'] = price

        return self._request('POST', endpoint, data=data)

    def cancel_order(self, inst_id: str, ord_id: str = None, cl_ord_id: str = None) -> Dict:
        """撤销订单"""
        endpoint = '/api/v5/trade/cancel-order'
        data = {'instId': inst_id}

        if ord_id:
            data['ordId'] = ord_id
        elif cl_ord_id:
            data['clOrdId'] = cl_ord_id
        else:
            raise ValueError("Must provide either ord_id or cl_ord_id")

        return self._request('POST', endpoint, data=data)

    def get_order(self, inst_id: str, ord_id: str = None, cl_ord_id: str = None) -> Dict:
        """获取订单信息"""
        endpoint = '/api/v5/trade/order'
        params = {'instId': inst_id}

        if ord_id:
            params['ordId'] = ord_id
        elif cl_ord_id:
            params['clOrdId'] = cl_ord_id
        else:
            raise ValueError("Must provide either ord_id or cl_ord_id")

        return self._request('GET', endpoint, params=params)

    def get_pending_orders(self, inst_type: str = 'SWAP', inst_id: str = None) -> Dict:
        """获取未成交订单列表"""
        endpoint = '/api/v5/trade/orders-pending'
        params = {'instType': inst_type}
        if inst_id:
            params['instId'] = inst_id
        return self._request('GET', endpoint, params=params)

    def get_order_history(self, inst_type: str = 'SWAP', inst_id: str = None, limit: int = 100) -> Dict:
        """获取历史订单记录"""
        endpoint = '/api/v5/trade/orders-history'
        params = {
            'instType': inst_type,
            'limit': str(limit)
        }
        if inst_id:
            params['instId'] = inst_id
        return self._request('GET', endpoint, params=params)

    # ==================== 公共数据接口 ====================

    def get_instruments(self, inst_type: str = 'SWAP') -> Dict:
        """获取交易产品基础信息"""
        endpoint = '/api/v5/public/instruments'
        params = {'instType': inst_type}
        return self._request('GET', endpoint, params=params)

    def get_funding_rate(self, inst_id: str) -> Dict:
        """获取永续合约资金费率"""
        endpoint = '/api/v5/public/funding-rate'
        params = {'instId': inst_id}
        return self._request('GET', endpoint, params=params)

    # ==================== 策略交易接口 ====================

    def place_algo_order(self, inst_id: str, side: str, order_type: str, size: str,
                         tp_trigger_px: str = None, tp_order_px: str = None,
                         sl_trigger_px: str = None, sl_order_px: str = None,
                         td_mode: str = 'cross') -> Dict:
        """
        下止盈止损单

        Args:
            inst_id: 产品ID
            side: 订单方向 (buy=买, sell=卖)
            order_type: 订单类型 (conditional=条件单, oco=OCO单, trigger=计划委托)
            size: 委托数量
            tp_trigger_px: 止盈触发价
            tp_order_px: 止盈委托价 (-1为市价)
            sl_trigger_px: 止损触发价
            sl_order_px: 止损委托价 (-1为市价)
            td_mode: 交易模式 (cross=全仓, isolated=逐仓)
        """
        endpoint = '/api/v5/trade/order-algo'
        data = {
            'instId': inst_id,
            'tdMode': td_mode,
            'side': side,
            'ordType': order_type,
            'sz': size
        }

        if tp_trigger_px:
            data['tpTriggerPx'] = tp_trigger_px
            data['tpOrdPx'] = tp_order_px or '-1'

        if sl_trigger_px:
            data['slTriggerPx'] = sl_trigger_px
            data['slOrdPx'] = sl_order_px or '-1'

        return self._request('POST', endpoint, data=data)

    def cancel_algo_order(self, algo_id: str, inst_id: str) -> Dict:
        """撤销策略订单"""
        endpoint = '/api/v5/trade/cancel-algos'
        data = [{'algoId': algo_id, 'instId': inst_id}]
        return self._request('POST', endpoint, data=data)

    def get_algo_orders(self, ord_type: str = 'conditional', inst_id: str = None) -> Dict:
        """获取策略订单列表"""
        endpoint = '/api/v5/trade/orders-algo-pending'
        params = {'ordType': ord_type}
        if inst_id:
            params['instId'] = inst_id
        return self._request('GET', endpoint, params=params)

    # ==================== 批量交易接口 ====================

    def batch_orders(self, orders: List[Dict]) -> Dict:
        """
        批量下单 (最多20个)

        Args:
            orders: 订单列表，每个订单包含 instId, tdMode, side, ordType, sz 等字段
        """
        endpoint = '/api/v5/trade/batch-orders'
        return self._request('POST', endpoint, data=orders)

    def batch_cancel_orders(self, orders: List[Dict]) -> Dict:
        """
        批量撤单 (最多20个)

        Args:
            orders: 订单列表，每个订单包含 instId, ordId 字段
        """
        endpoint = '/api/v5/trade/cancel-batch-orders'
        return self._request('POST', endpoint, data=orders)

    # ==================== 平仓接口 ====================

    def close_position(self, inst_id: str, mgn_mode: str = 'cross', pos_side: str = 'net') -> Dict:
        """
        市价全平

        Args:
            inst_id: 产品ID
            mgn_mode: 保证金模式 (cross=全仓, isolated=逐仓)
            pos_side: 持仓方向 (net=单向, long=多头, short=空头)
        """
        endpoint = '/api/v5/trade/close-position'
        data = {
            'instId': inst_id,
            'mgnMode': mgn_mode,
        }
        if pos_side and pos_side != 'net':
            data['posSide'] = pos_side
        return self._request('POST', endpoint, data=data)

    # ==================== 账户配置接口 ====================

    def get_account_config(self) -> Dict:
        """获取账户配置"""
        endpoint = '/api/v5/account/config'
        return self._request('GET', endpoint)

    def set_position_mode(self, pos_mode: str = 'net_mode') -> Dict:
        """
        设置持仓模式

        Args:
            pos_mode: 持仓模式 (long_short_mode=双向持仓, net_mode=单向持仓)
        """
        endpoint = '/api/v5/account/set-position-mode'
        data = {'posMode': pos_mode}
        return self._request('POST', endpoint, data=data)
