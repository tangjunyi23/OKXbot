import json
import time
import hmac
import base64
import threading
from typing import Callable, Dict, List
from datetime import datetime
import websocket


class OKXWebSocket:
    """OKX WebSocket 客户端"""

    def __init__(self, api_key: str = None, secret_key: str = None, passphrase: str = None,
                 is_simulated: bool = True, channel_type: str = 'public'):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_simulated = is_simulated
        self.channel_type = channel_type  # 'public' 或 'private'

        # WebSocket URL - 根据OKX官方文档修正
        if is_simulated:
            # 模拟盘
            if channel_type == 'private':
                self.ws_url = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
            else:
                self.ws_url = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
        else:
            # 实盘
            if channel_type == 'private':
                self.ws_url = "wss://ws.okx.com:8443/ws/v5/private"
            else:
                self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"

        self.ws = None
        self.callbacks: Dict[str, List[Callable]] = {}
        self.is_connected = False
        self.ping_thread = None
        self.reconnect_count = 0
        self.max_reconnect = 5

    def _generate_signature(self, timestamp: str) -> str:
        """生成WebSocket签名"""
        message = timestamp + 'GET' + '/users/self/verify'
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        signature = base64.b64encode(mac.digest()).decode()
        return signature

    def _on_message(self, ws, message):
        """处理接收到的消息"""
        try:
            data = json.loads(message)

            # 处理订阅确认
            if 'event' in data:
                if data['event'] == 'subscribe':
                    print(f"订阅成功: {data.get('arg', {})}")
                elif data['event'] == 'error':
                    print(f"订阅错误: {data.get('msg', 'Unknown error')}")
                return

            # 处理数据推送
            if 'arg' in data and 'data' in data:
                channel = data['arg'].get('channel')
                inst_id = data['arg'].get('instId', '')

                # 调用注册的回调函数
                callback_key = f"{channel}:{inst_id}"
                if callback_key in self.callbacks:
                    for callback in self.callbacks[callback_key]:
                        callback(data['data'])

                # 通用回调
                if channel in self.callbacks:
                    for callback in self.callbacks[channel]:
                        callback(data['data'])

        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
        except Exception as e:
            print(f"处理消息错误: {e}")

    def _on_error(self, ws, error):
        """处理错误"""
        print(f"WebSocket错误: {error}")
        self.is_connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        """处理连接关闭"""
        print("WebSocket连接已关闭")
        self.is_connected = False

    def _on_open(self, ws):
        """处理连接打开"""
        print("WebSocket连接已建立")
        self.is_connected = True

        # 如果提供了API密钥，进行登录认证（用于私有频道）
        if self.api_key and self.secret_key and self.passphrase:
            self._login()

    def _login(self):
        """登录认证（用于订阅私有频道）"""
        timestamp = str(int(time.time()))
        signature = self._generate_signature(timestamp)

        login_msg = {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": timestamp,
                "sign": signature
            }]
        }

        self.ws.send(json.dumps(login_msg))

    def _ping_loop(self):
        """定期发送ping消息保持连接（OKX要求30秒内必须有活动）"""
        while self.is_connected:
            try:
                if self.ws:
                    self.ws.send("ping")
                time.sleep(25)  # 每25秒发送一次ping，确保在30秒超时前
            except Exception as e:
                print(f"发送ping失败: {e}")
                self._try_reconnect()
                break

    def _try_reconnect(self):
        """尝试重新连接"""
        if self.reconnect_count >= self.max_reconnect:
            print(f"已达到最大重连次数 ({self.max_reconnect})，停止重连")
            return False

        self.reconnect_count += 1
        print(f"尝试重新连接... ({self.reconnect_count}/{self.max_reconnect})")

        try:
            time.sleep(2 ** self.reconnect_count)  # 指数退避
            self.connect()
            self.reconnect_count = 0  # 重连成功，重置计数
            return True
        except Exception as e:
            print(f"重连失败: {e}")
            return False

    def connect(self):
        """建立WebSocket连接"""
        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open
        )

        # 在新线程中运行WebSocket
        ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        ws_thread.start()

        # 等待连接建立
        timeout = 10
        start_time = time.time()
        while not self.is_connected and time.time() - start_time < timeout:
            time.sleep(0.1)

        if not self.is_connected:
            raise Exception("WebSocket连接超时")

        # 启动ping线程
        self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self.ping_thread.start()

        return True

    def disconnect(self):
        """断开WebSocket连接"""
        self.is_connected = False
        if self.ws:
            self.ws.close()

    def subscribe(self, channel: str, inst_id: str = None, callback: Callable = None):
        """
        订阅频道

        Args:
            channel: 频道名称 (tickers, candle1m, books, trades等)
            inst_id: 产品ID
            callback: 数据回调函数
        """
        if not self.is_connected:
            raise Exception("WebSocket未连接")

        # 构建订阅消息
        args = {"channel": channel}
        if inst_id:
            args["instId"] = inst_id

        subscribe_msg = {
            "op": "subscribe",
            "args": [args]
        }

        # 发送订阅消息
        self.ws.send(json.dumps(subscribe_msg))

        # 注册回调函数
        if callback:
            callback_key = f"{channel}:{inst_id}" if inst_id else channel
            if callback_key not in self.callbacks:
                self.callbacks[callback_key] = []
            self.callbacks[callback_key].append(callback)

    def unsubscribe(self, channel: str, inst_id: str = None):
        """取消订阅频道"""
        if not self.is_connected:
            return

        args = {"channel": channel}
        if inst_id:
            args["instId"] = inst_id

        unsubscribe_msg = {
            "op": "unsubscribe",
            "args": [args]
        }

        self.ws.send(json.dumps(unsubscribe_msg))

        # 移除回调函数
        callback_key = f"{channel}:{inst_id}" if inst_id else channel
        if callback_key in self.callbacks:
            del self.callbacks[callback_key]

    # ==================== 便捷订阅方法 ====================

    def subscribe_ticker(self, inst_id: str, callback: Callable):
        """订阅行情数据"""
        self.subscribe("tickers", inst_id, callback)

    def subscribe_candles(self, inst_id: str, bar: str = "1m", callback: Callable = None):
        """
        订阅K线数据

        Args:
            inst_id: 产品ID
            bar: K线周期 (1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H等)
            callback: 回调函数
        """
        channel = f"candle{bar}"
        self.subscribe(channel, inst_id, callback)

    def subscribe_orderbook(self, inst_id: str, depth: str = "5", callback: Callable = None):
        """
        订阅深度数据

        Args:
            inst_id: 产品ID
            depth: 深度档位 (5, 50, 400)
            callback: 回调函数
        """
        channel = f"books{depth}"
        self.subscribe(channel, inst_id, callback)

    def subscribe_trades(self, inst_id: str, callback: Callable):
        """订阅交易数据"""
        self.subscribe("trades", inst_id, callback)

    def subscribe_account(self, callback: Callable):
        """订阅账户信息（需要登录）"""
        self.subscribe("account", callback=callback)

    def subscribe_positions(self, inst_type: str = "SWAP", callback: Callable = None):
        """订阅持仓信息（需要登录）"""
        self.subscribe("positions", inst_type, callback)

    def subscribe_orders(self, inst_type: str = "SWAP", callback: Callable = None):
        """订阅订单信息（需要登录）"""
        self.subscribe("orders", inst_type, callback)
