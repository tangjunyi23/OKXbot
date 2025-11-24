"""
OKX量化交易 - 增强版桌面UI
特性：币种选择、策略选择、账户详情、高清字体
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import subprocess
import os
import json
from datetime import datetime
from okx_trading_bot.config import Config
from okx_trading_bot.api import OKXClient


class ModernButton(tk.Canvas):
    """现代化按钮控件（带动画效果）"""
    def __init__(self, parent, text, command, bg_color, hover_color, width=180, height=50):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bg=parent['bg'])
        self.text = text
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.current_color = bg_color
        self.enabled = True

        # 创建圆角矩形
        self.rect = self.create_rounded_rect(5, 5, width-5, height-5, radius=15, fill=bg_color)
        self.text_id = self.create_text(width/2, height/2, text=text, fill='white',
                                        font=('Microsoft YaHei UI', 11, 'bold'))

        # 绑定事件
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        self.bind('<Button-1>', self.on_click)

    def create_rounded_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        """创建圆角矩形"""
        points = [x1+radius, y1,
                  x1+radius, y1,
                  x2-radius, y1,
                  x2-radius, y1,
                  x2, y1,
                  x2, y1+radius,
                  x2, y1+radius,
                  x2, y2-radius,
                  x2, y2-radius,
                  x2, y2,
                  x2-radius, y2,
                  x2-radius, y2,
                  x1+radius, y2,
                  x1+radius, y2,
                  x1, y2,
                  x1, y2-radius,
                  x1, y2-radius,
                  x1, y1+radius,
                  x1, y1+radius,
                  x1, y1]
        return self.create_polygon(points, **kwargs, smooth=True)

    def on_enter(self, event):
        """鼠标悬停效果"""
        if self.enabled:
            self.animate_color(self.hover_color)
            self.config(cursor='hand2')

    def on_leave(self, event):
        """鼠标离开效果"""
        if self.enabled:
            self.animate_color(self.bg_color)

    def on_click(self, event):
        """点击效果"""
        if self.enabled and self.command:
            self.itemconfig(self.rect, fill='#ffffff')
            self.after(100, lambda: self.itemconfig(self.rect, fill=self.hover_color))
            self.after(200, self.command)

    def animate_color(self, target_color):
        """颜色渐变动画"""
        self.itemconfig(self.rect, fill=target_color)

    def set_enabled(self, enabled):
        """设置按钮启用状态"""
        self.enabled = enabled
        if enabled:
            self.itemconfig(self.rect, fill=self.bg_color)
            self.itemconfig(self.text_id, fill='white')
        else:
            self.itemconfig(self.rect, fill='#555555')
            self.itemconfig(self.text_id, fill='#888888')


class TradingUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OKX 量化交易系统 v2.0")
        self.root.geometry("1500x950")

        # 设置高DPI支持
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        # 现代化配色方案
        self.colors = {
            'bg_dark': '#0f0f1e',
            'bg_medium': '#1a1a2e',
            'bg_light': '#16213e',
            'accent_blue': '#0f4c75',
            'accent_green': '#00d9a3',
            'accent_red': '#ff4757',
            'accent_purple': '#5f27cd',
            'text_white': '#ffffff',
            'text_gray': '#95a5a6',
            'success': '#2ecc71',
            'warning': '#f39c12',
            'danger': '#e74c3c'
        }

        self.root.configure(bg=self.colors['bg_dark'])

        # 加载配置
        self.config = Config()
        okx_config = self.config.get_okx_config()

        self.api_client = OKXClient(
            api_key=okx_config['api_key'],
            secret_key=okx_config['secret_key'],
            passphrase=okx_config['passphrase'],
            is_simulated=okx_config.get('is_simulated', False),
            proxy=okx_config.get('proxy')
        )

        # 交易对列表
        self.available_symbols = [
            'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP',
            'PEPE-USDT-SWAP', 'DOGE-USDT-SWAP', 'SHIB-USDT-SWAP',
            'XRP-USDT-SWAP', 'ADA-USDT-SWAP', 'MATIC-USDT-SWAP'
        ]

        # 策略列表
        self.available_strategies = {
            'smart': '智能策略 (推荐)',
            'advanced': '高级策略 (多维度)',
            'position': '仓位策略 (简单)',
            'grid': '网格策略 (震荡)'
        }

        self.symbol = self.config.get('trading.symbol', 'PEPE-USDT-SWAP')
        self.strategy_type = self.config.get('trading.strategy_type', 'smart')
        self.bot_process = None
        self.is_running = False
        self.update_thread = None

        self.setup_ui()
        self.start_auto_update()

    def setup_ui(self):
        """设置UI界面"""

        # ==================== 顶部标题栏 ====================
        header = tk.Frame(self.root, bg=self.colors['bg_medium'], height=80)
        header.pack(fill='x', padx=0, pady=0)
        header.pack_propagate(False)

        # 标题
        title_frame = tk.Frame(header, bg=self.colors['bg_medium'])
        title_frame.pack(side='left', padx=30, pady=20)

        tk.Label(
            title_frame,
            text="🚀 OKX",
            font=('Microsoft YaHei UI', 24, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['accent_green']
        ).pack(side='left')

        tk.Label(
            title_frame,
            text=" 量化交易系统",
            font=('Microsoft YaHei UI', 24, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_white']
        ).pack(side='left')

        # 状态指示器
        status_frame = tk.Frame(header, bg=self.colors['bg_medium'])
        status_frame.pack(side='right', padx=30)

        self.status_indicator = tk.Canvas(status_frame, width=20, height=20,
                                          bg=self.colors['bg_medium'], highlightthickness=0)
        self.status_indicator.pack(side='left', padx=10)
        self.status_circle = self.status_indicator.create_oval(4, 4, 16, 16,
                                                               fill=self.colors['danger'], outline='')

        self.status_label = tk.Label(
            status_frame,
            text="系统离线",
            font=('Microsoft YaHei UI', 14, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['danger']
        )
        self.status_label.pack(side='left')

        # ==================== 主容器 ====================
        main_container = tk.Frame(self.root, bg=self.colors['bg_dark'])
        main_container.pack(fill='both', expand=True, padx=20, pady=10)

        # ==================== 左侧面板 ====================
        left_panel = tk.Frame(main_container, bg=self.colors['bg_dark'], width=480)
        left_panel.pack(side='left', fill='both', padx=(0, 10))
        left_panel.pack_propagate(False)

        # 交易设置卡片
        self.create_trading_config_card(left_panel)

        # 市场行情卡片
        self.create_market_card(left_panel)

        # 账户信息卡片
        self.create_account_card(left_panel)

        # 持仓信息卡片
        self.create_position_card(left_panel)

        # ==================== 右侧面板 ====================
        right_panel = tk.Frame(main_container, bg=self.colors['bg_dark'])
        right_panel.pack(side='right', fill='both', expand=True, padx=(10, 0))

        # 控制面板
        self.create_control_panel(right_panel)

        # 日志面板
        self.create_log_panel(right_panel)

    def create_card(self, parent, title, height=None):
        """创建卡片容器"""
        card = tk.Frame(parent, bg=self.colors['bg_medium'], relief='flat', bd=0)
        if height:
            card.pack(fill='x', pady=10)
            card.pack_propagate(False)
            card.configure(height=height)
        else:
            card.pack(fill='both', expand=True, pady=10)

        # 卡片标题
        title_label = tk.Label(
            card,
            text=title,
            font=('Microsoft YaHei UI', 13, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_white'],
            anchor='w'
        )
        title_label.pack(fill='x', padx=20, pady=(15, 10))

        return card

    def create_trading_config_card(self, parent):
        """创建交易配置卡片"""
        card = self.create_card(parent, "⚙ 交易配置", height=200)

        content = tk.Frame(card, bg=self.colors['bg_medium'])
        content.pack(fill='both', expand=True, padx=20, pady=(0, 15))

        # 币种选择
        symbol_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        symbol_frame.pack(fill='x', pady=8)

        tk.Label(
            symbol_frame,
            text="交易币种:",
            font=('Microsoft YaHei UI', 11),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray'],
            width=10,
            anchor='w'
        ).pack(side='left')

        self.symbol_var = tk.StringVar(value=self.symbol)
        symbol_combo = ttk.Combobox(
            symbol_frame,
            textvariable=self.symbol_var,
            values=self.available_symbols,
            state='readonly',
            font=('Microsoft YaHei UI', 10),
            width=20
        )
        symbol_combo.pack(side='left', padx=5)
        symbol_combo.bind('<<ComboboxSelected>>', self.on_symbol_changed)

        # 策略选择
        strategy_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        strategy_frame.pack(fill='x', pady=8)

        tk.Label(
            strategy_frame,
            text="交易策略:",
            font=('Microsoft YaHei UI', 11),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray'],
            width=10,
            anchor='w'
        ).pack(side='left')

        self.strategy_var = tk.StringVar(value=self.available_strategies.get(self.strategy_type, 'smart'))
        strategy_combo = ttk.Combobox(
            strategy_frame,
            textvariable=self.strategy_var,
            values=list(self.available_strategies.values()),
            state='readonly',
            font=('Microsoft YaHei UI', 10),
            width=20
        )
        strategy_combo.pack(side='left', padx=5)
        strategy_combo.bind('<<ComboboxSelected>>', self.on_strategy_changed)

        # 杠杆设置
        leverage_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        leverage_frame.pack(fill='x', pady=8)

        tk.Label(
            leverage_frame,
            text="杠杆倍数:",
            font=('Microsoft YaHei UI', 11),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray'],
            width=10,
            anchor='w'
        ).pack(side='left')

        self.leverage_label = tk.Label(
            leverage_frame,
            text=f"{self.config.get('trading.leverage')}x",
            font=('Microsoft YaHei UI', 11, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['accent_green']
        )
        self.leverage_label.pack(side='left', padx=5)

        # 保存配置按钮
        ModernButton(
            content, "💾 保存配置", self.save_config,
            self.colors['accent_blue'], '#0a3d62', width=150, height=35
        ).pack(pady=10)

    def create_market_card(self, parent):
        """创建市场行情卡片"""
        card = self.create_card(parent, "📊 市场行情", height=170)

        content = tk.Frame(card, bg=self.colors['bg_medium'])
        content.pack(fill='both', expand=True, padx=20, pady=(0, 15))

        # 价格显示
        price_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        price_frame.pack(fill='x', pady=5)

        tk.Label(
            price_frame,
            text="当前价格",
            font=('Microsoft YaHei UI', 10),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray']
        ).pack(side='left')

        self.price_label = tk.Label(
            price_frame,
            text="加载中...",
            font=('Consolas', 15, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['accent_green']
        )
        self.price_label.pack(side='right')

        # 24h涨跌
        change_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        change_frame.pack(fill='x', pady=5)

        tk.Label(
            change_frame,
            text="24h 波动",
            font=('Microsoft YaHei UI', 10),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray']
        ).pack(side='left')

        self.change_label = tk.Label(
            change_frame,
            text="--",
            font=('Consolas', 13, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_white']
        )
        self.change_label.pack(side='right')

        # 成交量
        volume_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        volume_frame.pack(fill='x', pady=5)

        tk.Label(
            volume_frame,
            text="24h 成交",
            font=('Microsoft YaHei UI', 10),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray']
        ).pack(side='left')

        self.volume_label = tk.Label(
            volume_frame,
            text="--",
            font=('Consolas', 11),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_white']
        )
        self.volume_label.pack(side='right')

    def create_account_card(self, parent):
        """创建账户信息卡片"""
        card = self.create_card(parent, "💰 账户资金", height=200)

        content = tk.Frame(card, bg=self.colors['bg_medium'])
        content.pack(fill='both', expand=True, padx=20, pady=(0, 15))

        # 总资产
        equity_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        equity_frame.pack(fill='x', pady=5)

        tk.Label(
            equity_frame,
            text="总权益",
            font=('Microsoft YaHei UI', 10),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray']
        ).pack(side='left')

        self.balance_label = tk.Label(
            equity_frame,
            text="$0.00",
            font=('Consolas', 15, 'bold'),
            bg=self.colors['bg_medium'],
            fg=self.colors['accent_blue']
        )
        self.balance_label.pack(side='right')

        # 可用余额
        avail_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        avail_frame.pack(fill='x', pady=5)

        tk.Label(
            avail_frame,
            text="可用",
            font=('Microsoft YaHei UI', 10),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray']
        ).pack(side='left')

        self.available_label = tk.Label(
            avail_frame,
            text="$0.00",
            font=('Consolas', 11),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_white']
        )
        self.available_label.pack(side='right')

        # 保证金占用
        margin_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        margin_frame.pack(fill='x', pady=5)

        tk.Label(
            margin_frame,
            text="保证金",
            font=('Microsoft YaHei UI', 10),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_gray']
        ).pack(side='left')

        self.margin_label = tk.Label(
            margin_frame,
            text="$0.00 (0%)",
            font=('Consolas', 11),
            bg=self.colors['bg_medium'],
            fg=self.colors['text_white']
        )
        self.margin_label.pack(side='right')

        # 查看详情按钮
        ModernButton(
            content, "📋 账户详情", self.show_account_details,
            self.colors['accent_purple'], '#341f97', width=150, height=35
        ).pack(pady=10)

    def create_position_card(self, parent):
        """创建持仓信息卡片"""
        card = self.create_card(parent, "📈 持仓状态")

        self.position_text = scrolledtext.ScrolledText(
            card,
            bg=self.colors['bg_light'],
            fg=self.colors['text_white'],
            font=('Consolas', 11),
            relief='flat',
            padx=15,
            pady=10
        )
        self.position_text.pack(fill='both', expand=True, padx=20, pady=(0, 15))

    def create_control_panel(self, parent):
        """创建控制面板"""
        card = self.create_card(parent, "🎮 交易控制", height=160)

        button_frame = tk.Frame(card, bg=self.colors['bg_medium'])
        button_frame.pack(fill='x', padx=20, pady=(0, 15))

        # 按钮容器
        btn_container = tk.Frame(button_frame, bg=self.colors['bg_medium'])
        btn_container.pack(pady=10)

        # 第一行按钮
        row1 = tk.Frame(btn_container, bg=self.colors['bg_medium'])
        row1.pack(fill='x', pady=5)

        self.start_button = ModernButton(
            row1, "▶ 启动交易", self.start_bot,
            self.colors['success'], '#27ae60', width=200, height=50
        )
        self.start_button.pack(side='left', padx=5)

        self.stop_button = ModernButton(
            row1, "⏸ 停止交易", self.stop_bot,
            self.colors['danger'], '#c0392b', width=200, height=50
        )
        self.stop_button.pack(side='left', padx=5)
        self.stop_button.set_enabled(False)

        ModernButton(
            row1, "🔄 刷新", self.refresh_data,
            self.colors['accent_blue'], '#0a3d62', width=140, height=50
        ).pack(side='left', padx=5)

        # 第二行按钮
        row2 = tk.Frame(btn_container, bg=self.colors['bg_medium'])
        row2.pack(fill='x', pady=5)

        ModernButton(
            row2, "⚡ 一键平仓", self.emergency_close,
            self.colors['warning'], '#d35400', width=160, height=45
        ).pack(side='left', padx=5)

        ModernButton(
            row2, "📊 统计", self.show_stats,
            '#16a085', '#138d75', width=160, height=45
        ).pack(side='left', padx=5)

        ModernButton(
            row2, "📖 文档", self.open_docs,
            '#8e44ad', '#6c3483', width=160, height=45
        ).pack(side='left', padx=5)

    def create_log_panel(self, parent):
        """创建日志面板"""
        card = self.create_card(parent, "📝 实时日志")

        self.log_text = scrolledtext.ScrolledText(
            card,
            bg=self.colors['bg_dark'],
            fg=self.colors['accent_green'],
            font=('Consolas', 10),
            relief='flat',
            padx=15,
            pady=10
        )
        self.log_text.pack(fill='both', expand=True, padx=20, pady=(0, 15))

        # 初始日志
        self.log("✓ 系统初始化完成")
        self.log(f"✓ 交易对: {self.symbol}")
        self.log(f"✓ 策略: {self.available_strategies.get(self.strategy_type)}")
        self.log("✓ 配置加载成功")
        self.log("━" * 60)
        self.log("⚡ 准备就绪，配置交易参数后点击'启动交易'")

    def log(self, message, color=None):
        """添加日志"""
        def _log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] {message}\n"
            self.log_text.insert('end', log_message)
            self.log_text.see('end')
        self.root.after(0, _log)

    def on_symbol_changed(self, event):
        """币种选择变化"""
        self.symbol = self.symbol_var.get()
        self.log(f"📌 切换交易对: {self.symbol}")
        self.refresh_data()

    def on_strategy_changed(self, event):
        """策略选择变化"""
        strategy_name = self.strategy_var.get()
        # 反向查找策略代码
        for code, name in self.available_strategies.items():
            if name == strategy_name:
                self.strategy_type = code
                break
        self.log(f"📌 切换策略: {strategy_name}")

    def save_config(self):
        """保存配置"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'okx_trading_bot', 'config', 'config.yaml')

            # 读取现有配置
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            # 更新配置
            config_data['trading']['symbol'] = self.symbol
            config_data['trading']['strategy_type'] = self.strategy_type

            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, allow_unicode=True)

            self.log("✓ 配置已保存")
            messagebox.showinfo("成功", "配置已保存！")
        except Exception as e:
            self.log(f"✗ 保存配置失败: {e}")
            messagebox.showerror("错误", f"保存失败: {e}")

    def show_account_details(self):
        """显示账户详细信息"""
        detail_window = tk.Toplevel(self.root)
        detail_window.title("账户详细信息")
        detail_window.geometry("700x600")
        detail_window.configure(bg=self.colors['bg_dark'])

        # 标题
        tk.Label(
            detail_window,
            text="💰 账户详细信息",
            font=('Microsoft YaHei UI', 18, 'bold'),
            bg=self.colors['bg_dark'],
            fg=self.colors['text_white']
        ).pack(pady=20)

        # 内容框
        content_frame = tk.Frame(detail_window, bg=self.colors['bg_medium'])
        content_frame.pack(fill='both', expand=True, padx=30, pady=(0, 20))

        # 滚动文本
        detail_text = scrolledtext.ScrolledText(
            content_frame,
            bg=self.colors['bg_light'],
            fg=self.colors['text_white'],
            font=('Consolas', 11),
            relief='flat',
            padx=20,
            pady=20
        )
        detail_text.pack(fill='both', expand=True, padx=15, pady=15)

        # 获取账户信息
        try:
            balance = self.api_client.get_balance()
            positions = self.api_client.get_positions()

            detail_text.insert('end', "=" * 60 + "\n")
            detail_text.insert('end', "账户概览\n")
            detail_text.insert('end', "=" * 60 + "\n\n")

            if balance['code'] == '0' and balance['data']:
                data = balance['data'][0]
                detail_text.insert('end', f"总权益: ${float(data.get('totalEq', 0)):.2f} USDT\n")
                detail_text.insert('end', f"可用余额: ${float(data.get('availBal', 0)):.2f} USDT\n")
                detail_text.insert('end', f"冻结余额: ${float(data.get('frozenBal', 0)):.2f} USDT\n")
                detail_text.insert('end', f"账户等级: {data.get('acctLv', 'N/A')}\n\n")

                detail_text.insert('end', "=" * 60 + "\n")
                detail_text.insert('end', "币种余额\n")
                detail_text.insert('end', "=" * 60 + "\n\n")

                for detail in data.get('details', []):
                    ccy = detail.get('ccy')
                    avail = float(detail.get('availBal', 0))
                    if avail > 0:
                        detail_text.insert('end', f"{ccy}: {avail}\n")

            detail_text.insert('end', "\n" + "=" * 60 + "\n")
            detail_text.insert('end', "持仓信息\n")
            detail_text.insert('end', "=" * 60 + "\n\n")

            if positions['code'] == '0' and positions['data']:
                has_pos = False
                for pos in positions['data']:
                    if float(pos.get('pos', 0)) != 0:
                        has_pos = True
                        detail_text.insert('end', f"产品: {pos.get('instId')}\n")
                        detail_text.insert('end', f"数量: {pos.get('pos')} 张\n")
                        detail_text.insert('end', f"开仓价: ${pos.get('avgPx')}\n")
                        detail_text.insert('end', f"盈亏: ${pos.get('upl')} ({float(pos.get('uplRatio', 0))*100:.2f}%)\n")
                        detail_text.insert('end', "-" * 60 + "\n")

                if not has_pos:
                    detail_text.insert('end', "暂无持仓\n")

        except Exception as e:
            detail_text.insert('end', f"获取账户信息失败: {e}\n")

        # 关闭按钮
        ModernButton(
            detail_window, "关闭", detail_window.destroy,
            self.colors['accent_purple'], '#341f97', width=200, height=45
        ).pack(pady=20)

    def emergency_close(self):
        """紧急平仓"""
        if messagebox.askyesno("确认", "确定要平掉所有持仓吗？"):
            try:
                result = self.api_client.close_position(self.symbol)
                if result['code'] == '0':
                    self.log("✓ 紧急平仓成功")
                    messagebox.showinfo("成功", "已平掉所有持仓")
                else:
                    self.log(f"✗ 平仓失败: {result.get('msg')}")
                    messagebox.showerror("失败", result.get('msg'))
            except Exception as e:
                self.log(f"✗ 平仓异常: {e}")
                messagebox.showerror("错误", str(e))

    def update_market_data(self):
        """更新市场数据"""
        try:
            ticker = self.api_client.get_ticker(self.symbol)
            if ticker['code'] == '0' and ticker['data']:
                data = ticker['data'][0]
                price = float(data['last'])
                high = float(data['high24h'])
                low = float(data['low24h'])
                vol = float(data.get('volCcy24h', 0))

                change = ((high - low) / price * 100)

                # 根据币种调整显示精度
                if 'PEPE' in self.symbol or 'SHIB' in self.symbol:
                    self.price_label.config(text=f"${price:.8f}")
                else:
                    self.price_label.config(text=f"${price:.4f}")

                self.change_label.config(
                    text=f"{change:.2f}%",
                    fg=self.colors['success'] if change > 0 else self.colors['danger']
                )
                self.volume_label.config(text=f"${vol/1000000:.1f}M")
        except Exception as e:
            pass

    def update_account_data(self):
        """更新账户数据"""
        try:
            balance = self.api_client.get_balance()
            if balance['code'] == '0' and balance['data']:
                data = balance['data'][0]
                equity = float(data.get('totalEq', 0))

                avail = 0
                for detail in data.get('details', []):
                    if detail.get('ccy') == 'USDT':
                        avail = float(detail.get('availBal', 0))

                margin_used = equity - avail
                margin_pct = (margin_used / equity * 100) if equity > 0 else 0

                self.balance_label.config(text=f"${equity:.2f}")
                self.available_label.config(text=f"${avail:.2f}")
                self.margin_label.config(
                    text=f"${margin_used:.2f} ({margin_pct:.1f}%)",
                    fg=self.colors['danger'] if margin_pct > 50 else self.colors['success']
                )
        except Exception as e:
            pass

    def update_position_data(self):
        """更新持仓数据"""
        try:
            positions = self.api_client.get_positions(inst_id=self.symbol)
            self.position_text.delete('1.0', 'end')

            if positions['code'] == '0' and positions['data']:
                has_position = False
                for pos in positions['data']:
                    pos_size = float(pos.get('pos', 0))
                    if pos_size != 0:
                        has_position = True
                        side = "🟢 做多" if pos_size > 0 else "🔴 做空"
                        entry = float(pos.get('avgPx', 0))
                        mark = float(pos.get('markPx', 0))
                        upl = float(pos.get('upl', 0))
                        upl_ratio = float(pos.get('uplRatio', 0)) * 100

                        self.position_text.insert('end', f"方向: {side}\n")
                        self.position_text.insert('end', f"数量: {abs(pos_size)} 张\n")

                        # 根据币种调整精度
                        if 'PEPE' in self.symbol or 'SHIB' in self.symbol:
                            self.position_text.insert('end', f"开仓: ${entry:.8f}\n")
                            self.position_text.insert('end', f"当前: ${mark:.8f}\n")
                        else:
                            self.position_text.insert('end', f"开仓: ${entry:.4f}\n")
                            self.position_text.insert('end', f"当前: ${mark:.4f}\n")

                        self.position_text.insert('end', f"盈亏: ${upl:.2f} ({upl_ratio:+.2f}%)\n")

                if not has_position:
                    self.position_text.insert('end', "暂无持仓\n\n等待交易信号...")
            else:
                self.position_text.insert('end', "暂无持仓\n\n等待交易信号...")
        except Exception as e:
            self.position_text.insert('end', f"查询失败: {e}")

    def refresh_data(self):
        """刷新所有数据"""
        self.log("🔄 刷新数据...")
        threading.Thread(target=self._refresh_data_thread, daemon=True).start()

    def _refresh_data_thread(self):
        """刷新数据线程"""
        self.update_market_data()
        self.update_account_data()
        self.update_position_data()

    def start_auto_update(self):
        """启动自动更新"""
        def auto_update():
            while True:
                try:
                    self._refresh_data_thread()
                except:
                    pass
                time.sleep(5)

        self.update_thread = threading.Thread(target=auto_update, daemon=True)
        self.update_thread.start()

    def start_bot(self):
        """启动交易机器人"""
        if self.is_running:
            messagebox.showwarning("警告", "机器人已在运行中")
            return

        try:
            self.log("🚀 正在启动交易机器人...")
            self.log(f"📊 交易对: {self.symbol}")
            self.log(f"🎯 策略: {self.available_strategies.get(self.strategy_type)}")

            self.bot_process = subprocess.Popen(
                ['python', 'main.py', '--mode', 'live'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            self.is_running = True
            self.status_indicator.itemconfig(self.status_circle, fill=self.colors['success'])
            self.status_label.config(text="系统运行中", fg=self.colors['success'])
            self.start_button.set_enabled(False)
            self.stop_button.set_enabled(True)

            self.log("✓ 交易机器人已启动")
            self.log("✓ WebSocket连接中...")

            threading.Thread(target=self._monitor_bot_output, daemon=True).start()

        except Exception as e:
            self.log(f"✗ 启动失败: {e}")
            messagebox.showerror("错误", f"启动失败: {e}")

    def stop_bot(self):
        """停止交易机器人"""
        if not self.is_running:
            return

        try:
            self.log("⏸ 正在停止交易机器人...")

            if self.bot_process:
                self.bot_process.terminate()
                self.bot_process.wait(timeout=5)

            self.is_running = False
            self.status_indicator.itemconfig(self.status_circle, fill=self.colors['danger'])
            self.status_label.config(text="系统离线", fg=self.colors['danger'])
            self.start_button.set_enabled(True)
            self.stop_button.set_enabled(False)

            self.log("✓ 交易机器人已停止")

        except Exception as e:
            self.log(f"✗ 停止失败: {e}")

    def _monitor_bot_output(self):
        """监控机器人输出"""
        if not self.bot_process:
            return

        for line in iter(self.bot_process.stderr.readline, ''):
            if not self.is_running:
                break
            if line.strip():
                if "检测到" in line or "开仓" in line or "平仓" in line or "触发" in line:
                    self.log(f"📊 {line.strip()}")

    def show_stats(self):
        """显示统计"""
        messagebox.showinfo("统计", "交易统计功能开发中...")

    def open_docs(self):
        """打开文档"""
        try:
            os.startfile("README.md")
        except:
            messagebox.showinfo("提示", "请查看项目目录中的 README.md 文件")


def main():
    root = tk.Tk()

    # 设置窗口图标（如果有的话）
    try:
        root.iconbitmap('icon.ico')
    except:
        pass

    app = TradingUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
