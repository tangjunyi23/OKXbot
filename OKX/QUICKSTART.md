# 快速开始指南

## 第一步：安装依赖

```bash
pip install -r requirements.txt
```

## 第二步：配置 API 密钥

### 1. 获取 OKX API 密钥

1. 登录 OKX 官网
2. 进入 个人中心 > API 管理
3. 创建 API Key，获取：
   - API Key
   - Secret Key
   - Passphrase

**重要**：首次使用建议选择"模拟盘交易"权限

### 2. 修改配置文件

编辑 `okx_trading_bot/config/config.yaml`：

```yaml
okx:
  api_key: "你的API_KEY"
  secret_key: "你的SECRET_KEY"
  passphrase: "你的PASSPHRASE"
  is_simulated: true  # 首次使用保持为 true（模拟盘）
```

### 3. 调整策略参数

根据你的需求调整网格参数：

```yaml
grid_strategy:
  grid_num: 10           # 网格数量（建议 5-20）
  price_upper: 50000     # 价格上限（根据当前价格设置）
  price_lower: 40000     # 价格下限（根据当前价格设置）
  investment: 1000       # 投资金额（USDT）
  min_profit_rate: 0.005 # 最小利润率（0.5%）
```

## 第三步：测试连接

测试 API 是否配置正确：

```bash
python main.py --mode test
```

如果看到类似以下输出，说明配置成功：

```
行情获取成功:
产品: BTC-USDT-SWAP
最新价: 43250.5
24h涨跌幅: 2.35%
```

## 第四步：运行回测

在历史数据上测试策略效果：

```bash
python main.py --mode backtest
```

查看回测结果，评估策略表现。

## 第五步：模拟盘运行

确认配置文件中 `is_simulated: true`，然后启动：

```bash
python main.py --mode live
```

机器人将：
1. 连接 OKX 模拟盘
2. 初始化网格订单
3. 开始实时交易监控

### 停止机器人

按 `Ctrl+C` 停止运行，机器人会自动：
- 取消所有挂单
- 断开连接
- 保存日志

## 第六步：查看日志

交易日志保存在 `logs/trading_bot.log`，可以查看：

```bash
# Windows
type logs\trading_bot.log

# Linux/Mac
cat logs/trading_bot.log
```

## 实盘交易（谨慎）

**仅在充分测试后考虑实盘交易！**

1. 修改配置：`is_simulated: false`
2. 确保账户有足够余额
3. 从小额资金开始
4. 密切监控交易日志

## 常用命令

```bash
# 测试连接
python main.py --mode test

# 回测
python main.py --mode backtest

# 模拟盘
python main.py --mode live

# 使用自定义配置文件
python main.py --mode live --config my_config.yaml

# 查看示例
python example_usage.py
```

## 监控建议

运行机器人时，建议：

1. 定期查看日志文件
2. 在 OKX 网页端监控持仓
3. 设置价格提醒
4. 准备好随时干预（取消订单等）

## 安全提示

- ✅ 首次使用必须用模拟盘
- ✅ 不要将 API 密钥提交到 Git
- ✅ 设置合理的风险参数
- ✅ 使用子账户限制风险
- ✅ 定期检查日志

## 获取帮助

遇到问题？

1. 查看 `README.md` 详细说明
2. 运行 `python example_usage.py` 查看示例
3. 检查日志文件排查错误
4. 查看 OKX API 文档：https://www.okx.com/docs-v5/zh/

## 下一步

- 调整网格参数优化策略
- 尝试不同的价格区间
- 监控实际表现
- 根据市场情况调整配置

祝交易顺利！
