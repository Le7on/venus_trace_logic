# TraceLogic Python

A Python 3.10+ rewrite of the TraceLogicLocal C# WPF application.  
Parses Hamilton Venus `.trc` log files, aggregates pipetting steps, and generates liquid transfer event reports.

---

## Installation

```bash
git clone <repo>
cd 09-TraceLogic-Python
python3 --version   # requires 3.10+

pip install -r requirements.txt   # installs flask>=2.3.0
```

---

## Web UI Usage

### 模式一：浏览器模式（仅需 Flask）

```bash
pip install flask
python app.py
# 浏览器访问 http://localhost:5000
```

### 模式二：原生桌面窗口（推荐，接近 WPF 体验）

```bash
pip install flask pywebview
python webview_app.py
# 自动弹出原生窗口，无需打开浏览器
# 若未安装 pywebview，自动 fallback 到浏览器模式
```

### 模式三：CLI（无 GUI）

```bash
python main.py run.trc
python main.py run.trc --export output.csv
```

**Web UI features:**
- Drag-and-drop or click-to-browse `.trc` file upload
- Three data tabs: Liquid Transfers / Pipetting Steps / All Entries
- Per-column visibility checkboxes
- Paginated tables (100 rows/page)
- CSV export (Liquid Transfers)
- Status bar with parse summary
- About dialog
- Dark theme, fully offline (no CDN dependencies)

---

## CLI Usage

```bash
# Print summary
python main.py run.trc

# Export transfers to CSV
python main.py run.trc --export transfers.csv

# Show all TraceEntry rows
python main.py run.trc --show-entries

# Show PipettingStep list
python main.py run.trc --show-steps
```

---

## File Structure

```
09-TraceLogic-Python/
├── tracelogic/           # Core parser library (do not modify)
│   ├── enums.py
│   ├── models.py
│   ├── parser.py
│   └── exporter.py
├── app.py                # Flask web application
├── templates/
│   └── index.html        # Single-page frontend (embedded CSS + JS)
├── main.py               # CLI entry point
├── requirements.txt      # flask>=2.3.0
└── tests/
    └── test_parser.py
```

---

## API Routes

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Serve the web UI |
| POST | `/parse` | Upload `.trc` file, returns JSON `{entries, steps, transfers, summary}` |
| GET | `/export` | Download last parsed result as CSV |

---

## Data Models

| Python class | Description |
|---|---|
| `TraceEntry` | Single parsed log line |
| `ChannelAction` | Per-channel action within a step |
| `PipettingStep` | Aggregated Start→Complete pair |
| `LiquidTransferEvent` | Aspirate→Dispense paired transfer |
| `TraceAnalysisResult` | Full parse result container |

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```
