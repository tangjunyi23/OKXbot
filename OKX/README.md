# OKX量化交易系统

基于OKX交易所API的Python量化交易系统，支持多种交易策略和完整的风险管理机制。

## 主要功能

- 多策略支持：智能策略、增强策略(MACD+KDJ+RSI)、网格策略、仓位策略
- 完整的风险管理系统：动态仓位、止损止盈、连续亏损保护、冷却机制
- WebSocket实时行情订阅
- 图形化交易界面
- 实时日志监控和市场数据分析
- 支持200+交易对，模糊搜索

## 系统架构

```
okx_trading_bot/
├── api/
│   ├── okx_client.py          # REST API封装(含限频和重试)
│   └── okx_websocket.py       # WebSocket客户端(含断线重连)
├── strategies/
│   ├── smart_profit_strategy.py    # 智能策略(RSI+MA)
│   ├── enhanced_strategy.py        # 增强策略(MACD+KDJ+RSI+BB)
│   ├── advanced_strategy.py        # 高级策略(多时间框架)
│   ├── grid_strategy.py            # 网格策略
│   └── position_strategy.py        # 仓位策略
├── risk_manager/
│   └── risk_manager.py        # 风险控制(冷却期、动态仓位、紧急停止)
├── config/
│   └── config.yaml            # 配置文件
└── utils/
    └── logger.py              # 日志工具
```

## 安装部署

### 环境要求

- Python 3.8+
- 稳定的网络连接
- OKX交易所账户

### 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包：
- requests >= 2.28.0
- websocket-client >= 1.4.0
- pyyaml >= 6.0
- pandas >= 1.5.0

### 配置API密钥

编辑 `okx_trading_bot/config/config.yaml`：

```yaml
okx:
  api_key: "YOUR_API_KEY"
  secret_key: "YOUR_SECRET_KEY"
  passphrase: "YOUR_PASSPHRASE"
  is_simulated: false          # true=模拟盘, false=实盘
  proxy: http://127.0.0.1:7897 # 可选，访问受限地区需要

trading:
  symbol: ETH-USDT-SWAP         # 交易对
  leverage: 10                  # 杠杆倍数(建议不超过10倍)
  margin_mode: cross            # cross=全仓, isolated=逐仓
  strategy_type: smart          # smart/enhanced/grid/position

smart_strategy:
  min_signal_strength: 50       # 信号强度阈值(0-100)
  position_size: 5000000        # 仓位大小(张)
  base_stop_loss: 0.025         # 基础止损比例(2.5%)
  base_take_profit: 0.05        # 基础止盈比例(5%)
  trailing_stop_trigger: 0.025  # 追踪止损触发(2.5%)
  trailing_stop_distance: 0.012 # 追踪止损距离(1.2%)

risk_management:
  max_daily_loss: 500           # 每日最大亏损(USDT)
  max_drawdown: 0.2             # 最大回撤(20%)
  max_position_size: 0.1        # 最大仓位
  max_consecutive_losses: 5     # 最大连续亏损次数
  consecutive_loss_cooldown: 3600 # 冷却时间(秒)
  max_hourly_trades: 10         # 每小时最大交易次数
```

## 使用方法

### 命令行模式

```bash
# 测试API连接
python main.py --mode test

# 启动实盘交易
python main.py --mode live

# 运行回测
python main.py --mode backtest
```

### 图形界面模式(推荐)

```bash
python trading_ui_enhanced.py
```

界面包含三个主要标签页：

**交易主界面**
- 交易配置：选择币种和策略
- 账户资金：显示余额和保证金
- 当前持仓：实时持仓信息
- 交易控制：启动/停止/刷新按钮
- 实时日志：交易事件记录

**市场行情**
- 涨跌排行榜(24小时)
- 实时价格和成交量
- 模糊搜索币种
- 双击快速选择交易对

**个人信息**
- 账户概览：总权益、可用余额、保证金
- 持仓详情：所有持仓的详细信息

## 交易策略详解

### 智能策略 (smart)

基于RSI和移动平均线的趋势跟踪策略。

**特点**：
- RSI超买超卖判断
- 双均线交叉信号
- 动态止损和追踪止盈
- 市场波动率调整

**适用场景**：单边趋势行情

### 增强策略 (enhanced)

多指标组合策略，使用MACD、KDJ、RSI和布林带。

**特点**：
- 加权信号评分(0-100分)
- MACD金叉死叉(25分)
- KDJ超买超卖(25分)
- RSI确认(20分)
- 布林带突破(20分)
- 趋势确认(10分)
- Kelly公式动态仓位

**适用场景**：震荡+趋势结合行情

### 网格策略 (grid)

适用于区间震荡的套利策略。

**特点**：
- 自动网格划分
- 双向套利
- 固定利润目标

**适用场景**：明确区间的震荡行情

### 仓位策略 (position)

简单的做多做空策略。

**特点**：
- 基于均线的方向判断
- 固定止损止盈
- 适合新手

**适用场景**：趋势明确的行情

## 风险管理机制

系统实现了多层风险控制：

### 仓位控制
- 最大仓位限制
- 动态仓位调整(基于胜率)
- 杠杆检查
- 持仓数量限制(最多3个)

### 损失保护
- 每日最大亏损限制
- 最大回撤保护
- 紧急停止机制
- 连续亏损后自动冷却

### 交易频率
- 每小时交易次数限制
- 冷却期机制(连续5次亏损后暂停1小时)
- 防止过度交易

### 动态调整
- 胜率低于50%时减小仓位
- 连续盈利3次后适当增加仓位
- 根据市场波动调整止损

## 注意事项

1. **首次使用务必使用模拟盘测试**
   - 在config.yaml中设置 `is_simulated: true`
   - 熟悉系统后再切换实盘

2. **合理设置杠杆**
   - 主流币种(BTC/ETH)：建议不超过20倍
   - 小市值币种：建议不超过10倍
   - 新手建议5倍以内

3. **网络连接**
   - 确保网络稳定
   - 部分地区需要配置代理
   - 定期检查WebSocket连接状态

4. **监控日志**
   - 定期查看 `trading_bot.log`
   - 关注风险管理报告
   - 及时处理异常情况

5. **资金管理**
   - 不要投入全部资金
   - 设置合理的止损线
   - 分散投资不同币种

## API权限设置

在OKX创建API密钥时，请配置以下权限：

- 读取权限 (Read) - 必需
- 交易权限 (Trade) - 必需
- 提现权限 (Withdraw) - 不要开启

建议使用子账户并设置IP白名单。

## 性能优化

- 使用WebSocket减少API调用
- 实现了请求限频(10次/秒)
- 自动重试机制(失败后指数退避)
- 连接池复用

## 常见问题

**Q: 为什么启动后不交易？**
A: 检查以下几点：
- 杠杆是否超过币种支持的最大值
- 信号强度阈值是否设置过高
- 市场波动是否足够
- 查看日志中的具体报错

**Q: 如何降低风险？**
A: 建议：
- 降低杠杆倍数
- 提高信号强度阈值
- 减小仓位大小
- 启用时间过滤

**Q: 网络连接不稳定怎么办？**
A:
- 配置稳定的代理
- 系统会自动重连WebSocket
- 失败请求会自动重试

## 开发路线

- [x] 多策略支持
- [x] 风险管理系统
- [x] 图形化界面
- [x] WebSocket实时行情
- [x] 增强策略(MACD+KDJ)
- [ ] 策略回测优化
- [ ] 更多技术指标
- [ ] Telegram通知
- [ ] 策略参数自动优化

## 更新日志

### v3.0 (2024-11)
- 新增增强策略(MACD+KDJ+RSI+BB组合)
- 重构风险管理系统(冷却期、动态仓位)
- 优化UI界面(1920x1080分辨率、大字体)
- 移除装饰性图标，专业化设计
- 修复小币种平仓bug(int转float)
- 增加市场排行榜和个人信息页面

### v2.0 (2024-10)
- 添加WebSocket实时行情
- 实现多策略切换
- 完善日志系统
- 增加限频和重试机制

### v1.0 (2024-09)
- 基础交易功能
- REST API集成
- 网格策略实现

## API文档

参考OKX官方文档：https://www.okx.com/docs-v5/zh/

## 技术支持

遇到问题请提交Issue，包含以下信息：
- Python版本
- 错误日志
- 配置参数(隐藏敏感信息)
- 复现步骤

## 免责声明

本项目仅供学习和研究使用。加密货币交易存在高风险，使用本系统进行交易产生的任何盈亏均由使用者自行承担。作者不对使用本系统造成的任何损失负责。

使用本系统即表示您已充分理解并接受上述风险。请在充分了解量化交易和风险管理的前提下谨慎使用。

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request。贡献代码前请确保：
- 代码符合PEP 8规范
- 添加必要的注释和文档
- 测试通过

## 联系方式

- GitHub Issues: 提交问题和建议
- 邮件: (如需添加请补充)
