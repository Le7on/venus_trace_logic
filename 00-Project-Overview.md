# TraceLogic Python — 项目概览

> Hamilton Venus `.trc` 日志解析工具，原 C# WPF 项目的 Python 重写版本。

## 基本信息

| 项目 | 详情 |
|------|------|
| 原仓库 | [VerisFlow/TraceLogicLocal](https://github.com/VerisFlow/TraceLogicLocal) |
| 语言 | Python 3.10+，纯标准库 |
| 重写日期 | 2026-03-26 |
| 测试 | 24/24 通过 |
| 代码行数 | ~700 行 |

## 功能

解析 Hamilton Venus 自动化工作站生成的 `.trc` 日志文件，提取：

- **TraceEntry** — 每一行日志（时间戳/来源/命令/状态/详情）
- **PipettingStep** — 聚合的移液操作（Aspirate/Dispense/PickupTip/EjectTip）
- **LiquidTransferEvent** — 高层液体转移事件（aspirate→dispense 配对，按 channel 追踪）

导出：LiquidTransferEvent 列表 → CSV

## 目录结构

```
09-TraceLogic-Python/
├── tracelogic/
│   ├── enums.py       # EntryStatus, PipettingActionType
│   ├── models.py      # 数据类（dataclass）
│   ├── parser.py      # TraceFileParser（核心解析逻辑）
│   └── exporter.py    # DataExporter（CSV 导出）
├── main.py            # CLI 入口
├── tests/
│   ├── test_parser.py # 24 个单元测试
│   └── sample.trc     # 示例 .trc 文件
└── README.md          # 完整文档
```

## 快速使用

```bash
# 解析并打印摘要
python3 main.py sample.trc

# 导出 CSV
python3 main.py sample.trc --export output.csv

# 显示所有 PipettingStep
python3 main.py sample.trc --show-steps
```

## C# → Python 对应关系

| C# 原版 | Python 版 |
|---------|----------|
| `TraceFileParser.cs` | `parser.py` |
| `Models/*.cs` | `models.py` (dataclass) |
| `Enums/*.cs` | `enums.py` |
| `DataExporter.cs` | `exporter.py` |
| WPF MainWindow | `main.py` (CLI) |

## 相关链接

- [[60-MOC/01-MOC-Lab-Automation|MOC - Lab Automation]]
- [[10-Projects/06-Liquid-Dispensing-Research/README|Liquid Dispensing Research]]
