"""
OKX量化交易 - 完全增强版桌面UI
新功能：涨跌排行榜、个人信息、全币种支持、模糊搜索
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import subprocess
import os
from datetime import datetime
from okx_trading_bot.config import Config
from okx_trading_bot.api import OKXClient


class SearchableCombobox(ttk.Frame):
    """带模糊搜索的下拉框"""
    def __init__(self, parent, values, **kwargs):
        super().__init__(parent)
        self.values = values
        self.filtered_values = values.copy()

        # 搜索框
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_values)

        self.entry = ttk.Entry(self, textvariable=self.search_var, **kwargs)
        self.entry.pack(fill='x')

        # 下拉列表
        self.listbox = tk.Listbox(self, height=8, **kwargs)
        self.listbox.pack(fill='both', expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.on_select)

        # 初始化列表
        self.update_listbox()

    def filter_values(self, *args):
        """模糊搜索过滤"""
        search_term = self.search_var.get().upper()
        if not search_term:
            self.filtered_values = self.values.copy()
        else:
            self.filtered_values = [v for v in self.values if search_term in v.upper()]
        self.update_listbox()

    def update_listbox(self):
        """更新列表显示"""
        self.listbox.delete(0, tk.END)
        for value in self.filtered_values[:50]:  # 最多显示50个
            self.listbox.insert(tk.END, value)

    def on_select(self, event):
        """选择项目"""
        selection = self.listbox.curselection()
        if selection:
            value = self.listbox.get(selection[0])
            self.search_var.set(value)

    def get(self):
        """获取当前值"""
        return self.search_var.get()

    def set(self, value):
        """设置值"""
        self.search_var.set(value)


class ModernButton(tk.Canvas):
    """现代化按钮控件"""
    def __init__(self, parent, text, command, bg_color, hover_color, width=180, height=50):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bg=parent['bg'])
        self.text = text
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.enabled = True

        self.rect = self.create_rounded_rect(5, 5, width-5, height-5, radius=15, fill=bg_color)
        self.text_id = self.create_text(width/2, height/2, text=text, fill='white',
                                        font=('Microsoft YaHei UI', 13, 'bold'))  # 增大按钮字体

        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        self.bind('<Button-1>', self.on_click)

    def create_rounded_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1,
                  x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius,
                  x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2,
                  x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius,
                  x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
        return self.create_polygon(points, **kwargs, smooth=True)

    def on_enter(self, event):
        if self.enabled:
            self.itemconfig(self.rect, fill=self.hover_color)
            self.config(cursor='hand2')

    def on_leave(self, event):
        if self.enabled:
            self.itemconfig(self.rect, fill=self.bg_color)

    def on_click(self, event):
        if self.enabled and self.command:
            self.itemconfig(self.rect, fill='#ffffff')
            self.after(100, lambda: self.itemconfig(self.rect, fill=self.hover_color))
            self.after(200, self.command)

    def set_enabled(self, enabled):
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
        self.root.title("OKX 量化交易系统 v3.0 - 完全增强版")
        self.root.geometry("1920x1080")  # 增大窗口以容纳更大字体

        # 设置高DPI支持
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        # 配色方案
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

        # 获取所有可交易币种
        self.all_symbols = []
        self.load_all_symbols()

        # 主流币种TOP10
        self.top_symbols = [
            'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP',
            'BNB-USDT-SWAP', 'XRP-USDT-SWAP', 'ADA-USDT-SWAP',
            'DOGE-USDT-SWAP', 'MATIC-USDT-SWAP', 'DOT-USDT-SWAP',
            'SHIB-USDT-SWAP'
        ]

        # 策略列表
        self.available_strategies = {
            'smart': '智能策略 (推荐)',
            'advanced': '高级策略 (多维度)',
            'enhanced': '增强策略 (MACD+KDJ)',
            'position': '仓位策略 (简单)',
            'grid': '网格策略 (震荡)'
        }

        self.symbol = self.config.get('trading.symbol', 'BTC-USDT-SWAP')
        self.strategy_type = self.config.get('trading.strategy_type', 'smart')
        self.bot_process = None
        self.is_running = False
        self.market_data_cache = {}  # 缓存市场数据

        self.setup_ui()
        self.start_auto_update()

    def load_all_symbols(self):
        """加载所有可交易币种"""
        try:
            result = self.api_client.get_instruments('SWAP')
            if result['code'] == '0':
                self.all_symbols = [inst['instId'] for inst in result['data']
                                   if inst['instId'].endswith('-USDT-SWAP')]
                self.all_symbols.sort()
        except:
            # 如果加载失败，使用默认列表
            self.all_symbols = self.top_symbols.copy()

    def setup_ui(self):
        """设置UI界面"""
        # 顶部标题栏 - 增加高度
        header = tk.Frame(self.root, bg=self.colors['bg_medium'], height=100)
        header.pack(fill='x')
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=self.colors['bg_medium'])
        title_frame.pack(side='left', padx=40, pady=25)

        tk.Label(title_frame, text="OKX 量化交易系统 v3.0", font=('Microsoft YaHei UI', 34, 'bold'),
                bg=self.colors['bg_medium'], fg=self.colors['text_white']).pack(side='left')

        # 状态指示器 - 增大尺寸
        status_frame = tk.Frame(header, bg=self.colors['bg_medium'])
        status_frame.pack(side='right', padx=40)

        self.status_indicator = tk.Canvas(status_frame, width=28, height=28,
                                          bg=self.colors['bg_medium'], highlightthickness=0)
        self.status_indicator.pack(side='left', padx=15)
        self.status_circle = self.status_indicator.create_oval(6, 6, 22, 22,
                                                               fill=self.colors['danger'], outline='')

        self.status_label = tk.Label(status_frame, text="系统离线",
                                     font=('Microsoft YaHei UI', 20, 'bold'),
                                     bg=self.colors['bg_medium'], fg=self.colors['danger'])
        self.status_label.pack(side='left')

        # 主容器 - 使用Notebook标签页
        # 配置标签页字体大小
        style = ttk.Style()
        style.configure('TNotebook.Tab', font=('Microsoft YaHei UI', 14, 'bold'), padding=[20, 10])

        main_notebook = ttk.Notebook(self.root)
        main_notebook.pack(fill='both', expand=True, padx=15, pady=15)

        # 标签页1：交易主界面
        trading_tab = tk.Frame(main_notebook, bg=self.colors['bg_dark'])
        main_notebook.add(trading_tab, text='交易主界面')
        self.create_trading_tab(trading_tab)

        # 标签页2：市场行情
        market_tab = tk.Frame(main_notebook, bg=self.colors['bg_dark'])
        main_notebook.add(market_tab, text='市场行情')
        self.create_market_tab(market_tab)

        # 标签页3：个人信息
        profile_tab = tk.Frame(main_notebook, bg=self.colors['bg_dark'])
        main_notebook.add(profile_tab, text='个人信息')
        self.create_profile_tab(profile_tab)

    def create_trading_tab(self, parent):
        """创建交易主界面标签页"""
        container = tk.Frame(parent, bg=self.colors['bg_dark'])
        container.pack(fill='both', expand=True, padx=15, pady=15)

        # 左侧面板 - 增加宽度以容纳更大字体
        left_panel = tk.Frame(container, bg=self.colors['bg_dark'], width=550)
        left_panel.pack(side='left', fill='both', padx=(0, 15))
        left_panel.pack_propagate(False)

        self.create_trading_config_card(left_panel)
        self.create_account_card(left_panel)
        self.create_position_card(left_panel)

        # 右侧面板
        right_panel = tk.Frame(container, bg=self.colors['bg_dark'])
        right_panel.pack(side='right', fill='both', expand=True, padx=(15, 0))

        self.create_control_panel(right_panel)
        self.create_log_panel(right_panel)

    def create_market_tab(self, parent):
        """创建市场行情标签页"""
        container = tk.Frame(parent, bg=self.colors['bg_dark'])
        container.pack(fill='both', expand=True, padx=25, pady=15)

        # 搜索框 - 增加高度和字体
        search_frame = tk.Frame(container, bg=self.colors['bg_medium'], height=100)
        search_frame.pack(fill='x', pady=(0, 15))
        search_frame.pack_propagate(False)

        tk.Label(search_frame, text="搜索币种:", font=('Microsoft YaHei UI', 18, 'bold'),
                bg=self.colors['bg_medium'], fg=self.colors['text_white']).pack(side='left', padx=30, pady=30)

        self.market_search_var = tk.StringVar()
        self.market_search_var.trace('w', self.filter_market_list)

        search_entry = tk.Entry(search_frame, textvariable=self.market_search_var,
                               font=('Microsoft YaHei UI', 16), width=25)
        search_entry.pack(side='left', padx=15, pady=30)

        ModernButton(search_frame, "刷新", self.refresh_market_data,
                    self.colors['accent_blue'], '#0a3d62', width=140, height=50).pack(side='left', padx=15)

        # 涨跌排行榜
        rank_frame = tk.Frame(container, bg=self.colors['bg_medium'])
        rank_frame.pack(fill='both', expand=True)

        tk.Label(rank_frame, text="涨跌排行榜 (24小时)", font=('Microsoft YaHei UI', 20, 'bold'),
                bg=self.colors['bg_medium'], fg=self.colors['text_white']).pack(pady=20)

        # 创建表格 - 增大列宽和高度
        columns = ('排名', '币种', '当前价格', '24h涨跌', '24h成交量', '操作')

        # 配置表格字体
        style = ttk.Style()
        style.configure('Treeview', font=('Microsoft YaHei UI', 12), rowheight=30)
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 13, 'bold'))

        self.market_tree = ttk.Treeview(rank_frame, columns=columns, show='headings', height=18)

        for col in columns:
            self.market_tree.heading(col, text=col)
            if col == '币种':
                self.market_tree.column(col, width=180, anchor='center')
            elif col == '当前价格':
                self.market_tree.column(col, width=180, anchor='e')
            elif col == '24h涨跌':
                self.market_tree.column(col, width=140, anchor='center')
            elif col == '24h成交量':
                self.market_tree.column(col, width=180, anchor='e')
            elif col == '排名':
                self.market_tree.column(col, width=100, anchor='center')
            else:
                self.market_tree.column(col, width=120, anchor='center')

        scrollbar = ttk.Scrollbar(rank_frame, orient='vertical', command=self.market_tree.yview)
        self.market_tree.configure(yscrollcommand=scrollbar.set)

        self.market_tree.pack(side='left', fill='both', expand=True, padx=25, pady=(0, 25))
        scrollbar.pack(side='right', fill='y', pady=(0, 25))

        # 双击选择币种
        self.market_tree.bind('<Double-1>', self.on_market_select)

        # 自动加载市场数据
        self.root.after(500, self.refresh_market_data)

    def create_profile_tab(self, parent):
        """创建个人信息标签页"""
        container = tk.Frame(parent, bg=self.colors['bg_dark'])
        container.pack(fill='both', expand=True, padx=30, pady=25)

        # 标题 - 增大字体
        tk.Label(container, text="个人账户信息", font=('Microsoft YaHei UI', 26, 'bold'),
                bg=self.colors['bg_dark'], fg=self.colors['text_white']).pack(pady=25)

        # 内容区域
        content_frame = tk.Frame(container, bg=self.colors['bg_medium'])
        content_frame.pack(fill='both', expand=True)

        # 左侧：账户概览
        left_info = tk.Frame(content_frame, bg=self.colors['bg_medium'])
        left_info.pack(side='left', fill='both', expand=True, padx=25, pady=25)

        tk.Label(left_info, text="账户概览", font=('Microsoft YaHei UI', 22, 'bold'),
                bg=self.colors['bg_medium'], fg=self.colors['accent_green']).pack(anchor='w', pady=15)

        self.profile_info = {}
        info_items = [
            ('总权益', 'total_eq'),
            ('可用余额', 'avail_bal'),
            ('已用保证金', 'margin_used'),
            ('未实现盈亏', 'upl'),
            ('账户等级', 'acct_lv'),
            ('持仓数量', 'pos_count'),
        ]

        for label, key in info_items:
            frame = tk.Frame(left_info, bg=self.colors['bg_light'], height=65)
            frame.pack(fill='x', pady=8)
            frame.pack_propagate(False)

            tk.Label(frame, text=label + ':', font=('Microsoft YaHei UI', 16),
                    bg=self.colors['bg_light'], fg=self.colors['text_gray']).pack(side='left', padx=20, pady=15)

            value_label = tk.Label(frame, text='加载中...', font=('Consolas', 17, 'bold'),
                                  bg=self.colors['bg_light'], fg=self.colors['text_white'])
            value_label.pack(side='right', padx=20, pady=15)
            self.profile_info[key] = value_label

        # 右侧：持仓详情
        right_info = tk.Frame(content_frame, bg=self.colors['bg_medium'])
        right_info.pack(side='right', fill='both', expand=True, padx=25, pady=25)

        tk.Label(right_info, text="持仓详情", font=('Microsoft YaHei UI', 22, 'bold'),
                bg=self.colors['bg_medium'], fg=self.colors['accent_blue']).pack(anchor='w', pady=15)

        self.profile_positions = scrolledtext.ScrolledText(right_info, bg=self.colors['bg_light'],
                                                           fg=self.colors['text_white'],
                                                           font=('Consolas', 14), relief='flat',
                                                           padx=20, pady=15)
        self.profile_positions.pack(fill='both', expand=True)

        # 刷新按钮 - 增大尺寸
        ModernButton(container, "刷新个人信息", self.refresh_profile_data,
                    self.colors['accent_purple'], '#341f97', width=240, height=60).pack(pady=25)

    def create_trading_config_card(self, parent):
        """创建交易配置卡片"""
        card = self.create_card(parent, "交易配置", height=420)

        content = tk.Frame(card, bg=self.colors['bg_medium'])
        content.pack(fill='both', expand=True, padx=25, pady=(0, 20))

        # 币种搜索选择 - 增大字体
        tk.Label(content, text="交易币种:", font=('Microsoft YaHei UI', 16),
                bg=self.colors['bg_medium'], fg=self.colors['text_gray']).pack(anchor='w', pady=(8, 5))

        symbol_search_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        symbol_search_frame.pack(fill='x', pady=8)

        self.symbol_search_var = tk.StringVar(value=self.symbol)
        self.symbol_search_var.trace('w', self.filter_symbol_list)

        symbol_entry = tk.Entry(symbol_search_frame, textvariable=self.symbol_search_var,
                               font=('Microsoft YaHei UI', 14), width=22)
        symbol_entry.pack(side='left')

        # 币种下拉列表 - 减少高度避免遮挡
        self.symbol_listbox = tk.Listbox(content, height=3, font=('Consolas', 13))
        self.symbol_listbox.pack(fill='x', pady=8)
        self.symbol_listbox.bind('<<ListboxSelect>>', self.on_symbol_list_select)
        self.update_symbol_listbox()

        # 策略选择 - 增大字体和间距
        strategy_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        strategy_frame.pack(fill='x', pady=15)

        tk.Label(strategy_frame, text="交易策略:", font=('Microsoft YaHei UI', 16),
                bg=self.colors['bg_medium'], fg=self.colors['text_gray'],
                width=8, anchor='w').pack(side='left')

        self.strategy_var = tk.StringVar(value=self.available_strategies.get(self.strategy_type))

        # 配置Combobox字体
        style = ttk.Style()
        style.configure('TCombobox', font=('Microsoft YaHei UI', 13))

        strategy_combo = ttk.Combobox(strategy_frame, textvariable=self.strategy_var,
                                     values=list(self.available_strategies.values()),
                                     state='readonly', font=('Microsoft YaHei UI', 13), width=16)
        strategy_combo.pack(side='left', padx=8)
        strategy_combo.bind('<<ComboboxSelected>>', self.on_strategy_changed)

        # 保存配置按钮 - 增大尺寸
        ModernButton(content, "保存配置", self.save_config,
                    self.colors['accent_blue'], '#0a3d62', width=180, height=45).pack(pady=15)

    def create_account_card(self, parent):
        """创建账户信息卡片"""
        card = self.create_card(parent, "账户资金", height=220)

        content = tk.Frame(card, bg=self.colors['bg_medium'])
        content.pack(fill='both', expand=True, padx=25, pady=(0, 20))

        # 总资产 - 增大字体和间距
        equity_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        equity_frame.pack(fill='x', pady=8)

        tk.Label(equity_frame, text="总权益", font=('Microsoft YaHei UI', 15),
                bg=self.colors['bg_medium'], fg=self.colors['text_gray']).pack(side='left')

        self.balance_label = tk.Label(equity_frame, text="$0.00",
                                      font=('Consolas', 20, 'bold'),
                                      bg=self.colors['bg_medium'],
                                      fg=self.colors['accent_blue'])
        self.balance_label.pack(side='right')

        # 可用余额 - 增大字体
        avail_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        avail_frame.pack(fill='x', pady=8)

        tk.Label(avail_frame, text="可用", font=('Microsoft YaHei UI', 15),
                bg=self.colors['bg_medium'], fg=self.colors['text_gray']).pack(side='left')

        self.available_label = tk.Label(avail_frame, text="$0.00",
                                        font=('Consolas', 16),
                                        bg=self.colors['bg_medium'],
                                        fg=self.colors['text_white'])
        self.available_label.pack(side='right')

        # 保证金 - 增大字体
        margin_frame = tk.Frame(content, bg=self.colors['bg_medium'])
        margin_frame.pack(fill='x', pady=8)

        tk.Label(margin_frame, text="保证金", font=('Microsoft YaHei UI', 15),
                bg=self.colors['bg_medium'], fg=self.colors['text_gray']).pack(side='left')

        self.margin_label = tk.Label(margin_frame, text="$0.00 (0%)",
                                     font=('Consolas', 16),
                                     bg=self.colors['bg_medium'],
                                     fg=self.colors['text_white'])
        self.margin_label.pack(side='right')

        # 详情按钮 - 增大尺寸
        ModernButton(content, "详细信息", lambda: self.root.after(0, lambda: self.root.nametowidget('.').focus()),
                    self.colors['accent_purple'], '#341f97', width=180, height=42).pack(pady=8)

    def create_position_card(self, parent):
        """创建持仓信息卡片"""
        card = self.create_card(parent, "当前持仓")

        self.position_text = scrolledtext.ScrolledText(card, bg=self.colors['bg_light'],
                                                       fg=self.colors['text_white'],
                                                       font=('Consolas', 14), relief='flat',
                                                       padx=20, pady=15)
        self.position_text.pack(fill='both', expand=True, padx=25, pady=(0, 20))

    def create_control_panel(self, parent):
        """创建控制面板"""
        card = self.create_card(parent, "交易控制", height=190)

        button_frame = tk.Frame(card, bg=self.colors['bg_medium'])
        button_frame.pack(fill='x', padx=25, pady=(0, 20))

        btn_container = tk.Frame(button_frame, bg=self.colors['bg_medium'])
        btn_container.pack(pady=12)

        # 第一行 - 增大按钮尺寸
        row1 = tk.Frame(btn_container, bg=self.colors['bg_medium'])
        row1.pack(fill='x', pady=8)

        self.start_button = ModernButton(row1, "启动交易", self.start_bot,
                                         self.colors['success'], '#27ae60', width=220, height=55)
        self.start_button.pack(side='left', padx=8)

        self.stop_button = ModernButton(row1, "停止交易", self.stop_bot,
                                        self.colors['danger'], '#c0392b', width=220, height=55)
        self.stop_button.pack(side='left', padx=8)
        self.stop_button.set_enabled(False)

        ModernButton(row1, "刷新", self.refresh_data,
                    self.colors['accent_blue'], '#0a3d62', width=160, height=55).pack(side='left', padx=8)

        # 第二行 - 增大按钮尺寸
        row2 = tk.Frame(btn_container, bg=self.colors['bg_medium'])
        row2.pack(fill='x', pady=8)

        ModernButton(row2, "一键平仓", self.emergency_close,
                    self.colors['warning'], '#d35400', width=200, height=50).pack(side='left', padx=8)

        ModernButton(row2, "市场", lambda: self.select_tab(1),
                    '#16a085', '#138d75', width=160, height=50).pack(side='left', padx=8)

        ModernButton(row2, "个人", lambda: self.select_tab(2),
                    '#8e44ad', '#6c3483', width=160, height=50).pack(side='left', padx=8)

    def create_log_panel(self, parent):
        """创建日志面板"""
        card = self.create_card(parent, "实时日志")

        self.log_text = scrolledtext.ScrolledText(card, bg=self.colors['bg_dark'],
                                                  fg=self.colors['accent_green'],
                                                  font=('Consolas', 13), relief='flat',
                                                  padx=20, pady=15)
        self.log_text.pack(fill='both', expand=True, padx=25, pady=(0, 20))

        self.log("[INFO] 系统初始化完成")
        self.log(f"[INFO] 已加载 {len(self.all_symbols)} 个交易对")
        self.log(f"[INFO] 当前币种: {self.symbol}")
        self.log("=" * 60)
        self.log("[INFO] 准备就绪，配置参数后点击'启动交易'")

    def create_card(self, parent, title, height=None):
        """创建卡片容器"""
        card = tk.Frame(parent, bg=self.colors['bg_medium'], relief='flat', bd=0)
        if height:
            card.pack(fill='x', pady=12)
            card.pack_propagate(False)
            card.configure(height=height)
        else:
            card.pack(fill='both', expand=True, pady=12)

        # 增大卡片标题字体
        tk.Label(card, text=title, font=('Microsoft YaHei UI', 18, 'bold'),
                bg=self.colors['bg_medium'], fg=self.colors['text_white'],
                anchor='w').pack(fill='x', padx=25, pady=(18, 12))

        return card

    def select_tab(self, index):
        """切换标签页"""
        notebook = self.root.children['!notebook']
        notebook.select(index)

    def filter_symbol_list(self, *args):
        """过滤币种列表（模糊搜索）"""
        search_term = self.symbol_search_var.get().upper()
        self.update_symbol_listbox(search_term)

    def update_symbol_listbox(self, filter_text=''):
        """更新币种列表"""
        self.symbol_listbox.delete(0, tk.END)

        if filter_text:
            filtered = [s for s in self.all_symbols if filter_text in s.upper()]
        else:
            filtered = self.all_symbols[:50]  # 默认显示前50个

        for symbol in filtered[:30]:  # 最多显示30个
            self.symbol_listbox.insert(tk.END, symbol)

    def on_symbol_list_select(self, event):
        """选择币种"""
        selection = self.symbol_listbox.curselection()
        if selection:
            symbol = self.symbol_listbox.get(selection[0])
            self.symbol_search_var.set(symbol)
            self.symbol = symbol
            self.log(f"[INFO] 选择币种: {symbol}")

    def filter_market_list(self, *args):
        """过滤市场列表"""
        search_term = self.market_search_var.get().upper()
        self.refresh_market_data(search_term)

    def refresh_market_data(self, filter_text=''):
        """刷新市场数据"""
        def _refresh():
            try:
                self.market_tree.delete(*self.market_tree.get_children())

                # 获取所有币种行情
                symbols_to_show = self.all_symbols if not filter_text else \
                                 [s for s in self.all_symbols if filter_text in s.upper()]

                market_data = []
                for symbol in symbols_to_show[:100]:  # 最多100个
                    try:
                        ticker = self.api_client.get_ticker(symbol)
                        if ticker['code'] == '0' and ticker['data']:
                            data = ticker['data'][0]
                            price = float(data['last'])
                            high = float(data['high24h'])
                            low = float(data['low24h'])

                            change_pct = ((price - low) / low * 100) if low > 0 else 0
                            vol = float(data.get('volCcy24h', 0))

                            market_data.append({
                                'symbol': symbol,
                                'price': price,
                                'change': change_pct,
                                'volume': vol
                            })
                    except:
                        continue

                # 按涨跌幅排序
                market_data.sort(key=lambda x: x['change'], reverse=True)

                # 显示数据
                for idx, item in enumerate(market_data[:50], 1):
                    symbol = item['symbol']
                    price = item['price']
                    change = item['change']
                    volume = item['volume']

                    # 根据币种调整精度
                    if 'PEPE' in symbol or 'SHIB' in symbol:
                        price_str = f"${price:.8f}"
                    else:
                        price_str = f"${price:.4f}"

                    change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
                    vol_str = f"${volume/1000000:.2f}M"

                    # 插入行
                    tag = 'up' if change > 0 else 'down'
                    self.market_tree.insert('', 'end', values=(idx, symbol, price_str, change_str, vol_str, '选择'),
                                           tags=(tag,))

                # 设置颜色
                self.market_tree.tag_configure('up', foreground='#2ecc71')
                self.market_tree.tag_configure('down', foreground='#e74c3c')

                self.log(f"[INFO] 已更新 {len(market_data)} 个币种行情")

            except Exception as e:
                self.log(f"[ERROR] 刷新市场数据失败: {e}")

        threading.Thread(target=_refresh, daemon=True).start()

    def on_market_select(self, event):
        """双击选择币种进行交易"""
        selection = self.market_tree.selection()
        if selection:
            item = self.market_tree.item(selection[0])
            symbol = item['values'][1]
            self.symbol = symbol
            self.symbol_search_var.set(symbol)
            self.log(f"[INFO] 选择交易币种: {symbol}")
            self.select_tab(0)  # 切换到交易主界面
            messagebox.showinfo("提示", f"已选择 {symbol}，请保存配置后开始交易")

    def refresh_profile_data(self):
        """刷新个人信息"""
        def _refresh():
            try:
                # 获取账户信息
                balance = self.api_client.get_balance()
                positions = self.api_client.get_positions()

                if balance['code'] == '0' and balance['data']:
                    data = balance['data'][0]
                    total_eq = float(data.get('totalEq', 0))
                    avail_bal = float(data.get('availBal', 0))
                    margin_used = total_eq - avail_bal

                    self.profile_info['total_eq'].config(text=f"${total_eq:.2f} USDT")
                    self.profile_info['avail_bal'].config(text=f"${avail_bal:.2f} USDT")
                    self.profile_info['margin_used'].config(text=f"${margin_used:.2f} USDT")
                    self.profile_info['acct_lv'].config(text=data.get('acctLv', 'N/A'))

                # 获取持仓
                self.profile_positions.delete('1.0', 'end')
                pos_count = 0
                total_upl = 0

                if positions['code'] == '0' and positions['data']:
                    for pos in positions['data']:
                        if float(pos.get('pos', 0)) != 0:
                            pos_count += 1
                            upl = float(pos.get('upl', 0))
                            total_upl += upl

                            self.profile_positions.insert('end', f"{'='*60}\n")
                            self.profile_positions.insert('end', f"币种: {pos.get('instId')}\n")
                            self.profile_positions.insert('end', f"方向: {'做多' if float(pos.get('pos', 0)) > 0 else '做空'}\n")
                            self.profile_positions.insert('end', f"数量: {abs(float(pos.get('pos', 0)))} 张\n")
                            self.profile_positions.insert('end', f"开仓价: ${pos.get('avgPx')}\n")
                            self.profile_positions.insert('end', f"盈亏: ${upl:.2f} ({float(pos.get('uplRatio', 0))*100:.2f}%)\n\n")

                if pos_count == 0:
                    self.profile_positions.insert('end', "暂无持仓")

                self.profile_info['pos_count'].config(text=f"{pos_count} 个")
                self.profile_info['upl'].config(text=f"${total_upl:.2f} USDT",
                                               fg=self.colors['success'] if total_upl >= 0 else self.colors['danger'])

                self.log("[INFO] 个人信息已更新")

            except Exception as e:
                self.log(f"[ERROR] 更新个人信息失败: {e}")

        threading.Thread(target=_refresh, daemon=True).start()

    def on_strategy_changed(self, event):
        """策略改变"""
        strategy_name = self.strategy_var.get()
        for code, name in self.available_strategies.items():
            if name == strategy_name:
                self.strategy_type = code
                break
        self.log(f"[INFO] 切换策略: {strategy_name}")

    def save_config(self):
        """保存配置"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'okx_trading_bot', 'config', 'config.yaml')
            import yaml

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            config_data['trading']['symbol'] = self.symbol
            config_data['trading']['strategy_type'] = self.strategy_type

            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, allow_unicode=True)

            self.log("[INFO] 配置已保存")
            messagebox.showinfo("成功", f"配置已保存！\n币种: {self.symbol}\n策略: {self.available_strategies[self.strategy_type]}")
        except Exception as e:
            self.log(f"[ERROR] 保存配置失败: {e}")
            messagebox.showerror("错误", f"保存失败: {e}")

    def emergency_close(self):
        """紧急平仓"""
        if messagebox.askyesno("确认", "确定要平掉所有持仓吗？"):
            try:
                result = self.api_client.close_position(self.symbol)
                if result['code'] == '0':
                    self.log("[INFO] 紧急平仓成功")
                    messagebox.showinfo("成功", "已平掉所有持仓")
                else:
                    self.log(f"[ERROR] 平仓失败: {result.get('msg')}")
                    messagebox.showerror("失败", result.get('msg'))
            except Exception as e:
                self.log(f"[ERROR] 平仓异常: {e}")
                messagebox.showerror("错误", str(e))

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
                self.margin_label.config(text=f"${margin_used:.2f} ({margin_pct:.1f}%)",
                                        fg=self.colors['danger'] if margin_pct > 50 else self.colors['success'])
        except:
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
                        side = "做多" if pos_size > 0 else "做空"
                        entry = float(pos.get('avgPx', 0))
                        mark = float(pos.get('markPx', 0))
                        upl = float(pos.get('upl', 0))
                        upl_ratio = float(pos.get('uplRatio', 0)) * 100

                        self.position_text.insert('end', f"方向: {side}\n")
                        self.position_text.insert('end', f"数量: {abs(pos_size)} 张\n")

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
        except:
            pass

    def refresh_data(self):
        """刷新数据"""
        self.log("[INFO] 刷新数据...")
        threading.Thread(target=self._refresh_data_thread, daemon=True).start()

    def _refresh_data_thread(self):
        """刷新数据线程"""
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

        threading.Thread(target=auto_update, daemon=True).start()

    def start_bot(self):
        """启动交易机器人"""
        if self.is_running:
            messagebox.showwarning("警告", "机器人已在运行中")
            return

        try:
            self.log("[INFO] 正在启动交易机器人...")
            self.log(f"[INFO] 交易对: {self.symbol}")
            self.log(f"[INFO] 策略: {self.available_strategies.get(self.strategy_type)}")

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

            self.log("[INFO] 交易机器人已启动")

            threading.Thread(target=self._monitor_bot_output, daemon=True).start()

        except Exception as e:
            self.log(f"[ERROR] 启动失败: {e}")
            messagebox.showerror("错误", f"启动失败: {e}")

    def stop_bot(self):
        """停止交易机器人"""
        if not self.is_running:
            return

        try:
            self.log("[INFO] 正在停止交易机器人...")

            if self.bot_process:
                self.bot_process.terminate()
                self.bot_process.wait(timeout=5)

            self.is_running = False
            self.status_indicator.itemconfig(self.status_circle, fill=self.colors['danger'])
            self.status_label.config(text="系统离线", fg=self.colors['danger'])
            self.start_button.set_enabled(True)
            self.stop_button.set_enabled(False)

            self.log("[INFO] 交易机器人已停止")

        except Exception as e:
            self.log(f"[ERROR] 停止失败: {e}")

    def _monitor_bot_output(self):
        """监控机器人输出"""
        if not self.bot_process:
            return

        for line in iter(self.bot_process.stderr.readline, ''):
            if not self.is_running:
                break
            if line.strip():
                if "检测到" in line or "开仓" in line or "平仓" in line or "触发" in line:
                    self.log(f"[TRADE] {line.strip()}")

    def log(self, message):
        """添加日志"""
        def _log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert('end', f"[{timestamp}] {message}\n")
            self.log_text.see('end')
        self.root.after(0, _log)


def main():
    root = tk.Tk()

    try:
        root.iconbitmap('icon.ico')
    except:
        pass

    app = TradingUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
