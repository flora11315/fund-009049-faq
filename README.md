# 009049 基金 FAQ AI 助手原型

这是一个面向 `009049 易方达高端制造混合发起式 A` 的轻量 FAQ 助手原型，用于验证：

- 常见基金问题能否准确回答
- 回答是否带来源和数据日期
- 是否能拒绝收益预测、买卖建议等不合规问题
- 批量测试集的准确率表现

当前版本不依赖外部包，直接使用 Python 标准库运行。

## 目录

```text
.
├── data/
│   ├── eval_questions.jsonl       # 测试问题集
│   └── fund_009049_knowledge.json # 009049 知识库
├── reports/                       # 评测报告输出目录
└── src/
    └── faq_assistant.py           # 问答与评测入口
```

## 快速开始

交互式提问：

```bash
python3 src/faq_assistant.py ask "009049是什么基金？"
```

采集公开数据并更新知识库：

```bash
python3 src/collect_fund_data.py
```

批量评测：

```bash
python3 src/faq_assistant.py eval
```

启动前端页面：

```bash
python3 src/web_server.py
```

然后打开：

```text
http://127.0.0.1:8000
```

运行后会输出准确率摘要，并在 `reports/eval_report.json` 生成逐题评测结果。

## 当前知识库边界

当前版本已经接入公开数据自动采集，会从天天基金实时估值接口和东方财富基金数据脚本拉取 009049 的基金名称、净值日期、单位净值、实时估值等信息，并写入：

- `data/fund_009049_collected.json`
- `data/fund_009049_knowledge.json`

涉及规模、持仓、基金经理、费率明细等更完整的信息，仍建议继续接入基金公司公告、产品资料概要和定期报告。

建议下一步把 `data/fund_009049_knowledge.json` 替换或补充为自动采集后的最新数据，包括：

- 易方达基金官网产品页
- 基金合同、招募说明书、基金产品资料概要
- 最近 4 期季报、半年报、年报
- 东方财富 / 天天基金的净值、规模、持仓和交易状态数据

## 评测口径

评测脚本会检查：

- 标准关键词是否出现在回答中
- 需要拒答的问题是否被拒答
- 是否包含来源
- 是否包含数据日期或时点说明

这不是最终生产级评测，但足够用于原型阶段快速发现知识库缺口和回答风险。

## 前端功能

本地前端提供一个轻量工作台：

- 问答测试：输入问题并查看答案、来源、资料时点和风险提示
- 采集更新：点击后触发 `/api/collect`，刷新公开数据并更新知识库
- 运行评测：点击后触发 `/api/eval`，显示准确率和拒答准确率
- 知识条目：查看当前知识库分类和资料时点

## 云平台部署

项目已支持云平台部署：

- `src/web_server.py` 支持 `HOST` 和 `PORT` 环境变量
- `Dockerfile` 可用于容器化部署
- `Procfile` / `runtime.txt` 可用于 Python Web Service 平台
- `/healthz` 可作为健康检查地址
- 可设置 `APP_USERNAME` / `APP_PASSWORD` 开启基础认证

本地模拟云平台启动：

```bash
HOST=0.0.0.0 PORT=8000 APP_USERNAME=demo APP_PASSWORD=change-me python3 src/web_server.py
```

详细部署说明见：

```text
docs/cloud_deployment.md
```
