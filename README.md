# 全球主要指数 · 每日分析报告生成器

一键采集全球 6 个主要指数的日线与当日分时数据，自动生成**图文并茂的 PDF 报告**，
以及**单文件、可交互的 HTML 报告**（图表已内嵌，离线可看）。

> 仅供学习与技术研究使用，不构成任何投资建议。

## 覆盖的指数

| 指数 | 代码 | 市场 |
| --- | --- | --- |
| 上证指数 | `sh000001` | A 股 |
| 创业板指 | `sz399006` | A 股 |
| 恒生指数 | `hkHSI` | 港股 |
| 恒生科技指数 | `hkHSTECH` | 港股 |
| 纳斯达克 100 | `usNDX` | 美股 |
| 华安黄金 ETF | `sh518880` | A 股（作为 COMEX 黄金的代理） |

## 报告内容

- **汇总页**：6 项指数一览表（今日点位 / 涨跌 / 振幅 / 成交量 / 量比 / 多周期收益）
- **每个指数一页**：
  - 关键数据 + 240 日区间高/低 + 多周期涨跌
  - 图 1：近 240 个交易日日线走势
  - 图 2：今日日内分时（含成交量柱）
  - 简要文字分析（量价、VWAP 强弱、趋势位置）
- **末页**：数据口径与说明
- PDF 与 HTML 内容一致；HTML 可搜索（Ctrl+F）、可打印（Ctrl+P 另存为 PDF）、手机端自适应

## 环境要求

- Python 3.10 及以上（已在 3.14 上实测）

## 安装

```bash
git clone <本仓库地址>
cd index-daily-report

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # macOS / Linux

pip install -r requirements.txt
```

如果装了 [uv](https://github.com/astral-sh/uv)，也可以：

```bash
uv venv
uv pip install -r requirements.txt
```

## 运行

```bash
python run_report.py
```

Windows 下也可以直接双击：

- `启动分析.bat` —— 带命令行窗口，能看到采集进度
- `启动分析.vbs` —— 静默运行，跑完弹出结果

## 输出

```
output/
└── <日期> 指数分析/
    ├── <日期> 全球主要指数分析.pdf   # 8 页 PDF
    ├── index.html                    # 单文件 HTML 报告（图表已内嵌）
    ├── 在浏览器中打开.bat            # 一键用默认浏览器打开 index.html
    └── charts/                       # 6 个指数 × 2 张图（240 日 + 分时）
```

每次运行都会新建一个以日期命名的子目录，**不会覆盖历史报告**。
`output/` 已在 `.gitignore` 中忽略。

## 目录结构

```
index-daily-report/
├── run_report.py        # 主脚本：抓数据、画图、生成 PDF
├── html_report.py       # HTML 报告生成模块
├── data_source.py       # 数据抓取（腾讯财经公开接口）
├── requirements.txt
├── 启动分析.bat
├── 启动分析.vbs
└── output/              # 运行时自动生成
```

## 数据源

全部为公开接口，无需密钥：

- `web.ifzq.gtimg.cn`（腾讯财经）
  - `fqkline` 端点：A 股 / 港股 / 黄金 ETF 的日线与前复权数据
  - `usfqkline` 端点：美股指数的日线
  - `minute/query` 端点：1 分钟分时

两点说明：

1. 原先使用的东方财富接口（`push2his.eastmoney.com`）近期稳定性不佳，已切换到腾讯财经。
2. COMEX 黄金（GC）在腾讯接口中没有对应品种，因此临时用 A 股黄金 ETF（`sh518880`）
   作为代理来观察价格走势。注意 ETF 的单位是「元/份」，与 COMEX 的「美元/盎司」不同。

请在遵守数据提供方使用条款的前提下使用。

## 免责声明

本项目仅用于技术学习与研究。任何基于本项目产生的投资决策及其后果，由使用者自行承担。
