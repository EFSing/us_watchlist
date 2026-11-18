# 美股交易系统

V1 初始化提供离线可运行的 Python 骨架。烟测以合成股票池和已完成交易时段的 OHLCV 生成一份 HTML，
展示输入来源、覆盖缺口和描述性量能数据。

## 从仓库根目录运行

需要 Git 和 Python 3.12 或更新版本。CI 覆盖 Linux 的 3.12／3.13 和 Windows 的 3.12。
审阅阶段使用 [`codex/v1-project-bootstrap`](https://github.com/EFSing/us_watchlist/tree/codex/v1-project-bootstrap)。

Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir .
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\us-watchlist.exe smoke
```

macOS／Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir .
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/us-watchlist smoke
```

输出位于 `.runtime/artifacts/smoke/US_2026-01-05_regular.html`。相同输入和渲染版本重复执行
会返回同一文件。更改合成输入后若仍使用同一时段身份，先在无运行进程时清理该烟测输出，或给新
fixture 指定另一个交易日／时段。

跨设备恢复见 [HANDOFF.md](HANDOFF.md)，依赖与输入口径见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)。
