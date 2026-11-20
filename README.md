# 美股交易系统

V1 初始化提供离线可运行的 Python 骨架。烟测以合成股票池和已完成交易时段的 OHLCV 生成一份 HTML，
展示输入来源、覆盖缺口和描述性量能数据。

## 从仓库根目录运行

需要 Git 和 Python 3.12 或更新版本。CI 覆盖 Linux 的 3.12／3.13 和 Windows 的 3.12。
当前审阅分支及基线见 [HANDOFF.md](HANDOFF.md)。

Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir ".[yahoo]"
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\us-watchlist.exe smoke
```

macOS／Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir ".[yahoo]"
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/us-watchlist smoke
```

输出位于 `.runtime/artifacts/smoke/US_2026-01-05_regular.html`。相同输入和渲染版本重复执行
会返回同一文件。更改合成输入后若仍使用同一时段身份，先在无运行进程时清理该烟测输出，或给新
fixture 指定另一个交易日／时段。

跨设备恢复见 [HANDOFF.md](HANDOFF.md)，依赖与输入口径见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## B 常规时段离线验证

安装后从项目根目录运行 `us-watchlist b-offline`。默认使用已提交的合成样本，
预期为 1 个突破回踩形态匹配、1 个无突破、1 个历史缺口和 1 个首次突破回踩失败。
HTML 输出在 `.runtime/artifacts/b-offline/synthetic/`。实际股票池使用上游 US Candidate，
可选 `capture-yahoo` 冻结 Yahoo Chart 常规时段数据。归档契约、采集和历史时点标识见
[B 离线验证](docs/B_OFFLINE.md)。

同一输入已有旧版 B HTML 时，先将该 HTML 移到归档目录，再执行新版渲染。发布器会保留已有文件及其内容身份。

## B+C 联合日报

运行 `us-watchlist bc-offline` 生成合成单文件日报。B 与两套 C 规则分别验证
共同数据中的历史覆盖和结构。打开 `.runtime/artifacts/bc-offline/synthetic/` 下的 HTML
查看候选与逐股诊断。实际输入、C 规则与观察结果见 [B+C 离线日报](docs/BC_OFFLINE.md)。

匹配卡片展示价格结构、三项回踩量能及研究参考计划。指标、资格边界和冻结验证见
[B+C 参考研究](docs/BC_REFERENCE_RESEARCH.md)。

## IWB 基础池与 B+C 日报

`us-watchlist iwb-refresh` 下载并冻结官方 IWB 版本。`us-watchlist iwb-report --trade-date YYYY-MM-DD --output <目录>` 从可用本地版本出发，采集 Yahoo 常规会话行情并生成单文件报告。输入格式、数据门槛与真实验证见 [IWB 日报](docs/IWB_DAILY.md)。

Actions 手动补跑、定时验收、短期归档和跨设备校验见 [IWB 日报自动化](docs/IWB_AUTOMATION.md)。
定时执行由 `US_IWB_SCHEDULE_ENABLED` 控制，默认关闭。

## IWB 研究模拟持仓

`us-watchlist iwb-paper` 可从已验证的日报归档建立离线历史复算，逐个 XNYS 交易日还原模拟计划与持仓，
并生成独立的中文 HTML 和邮件摘要文本。政策未配置时只保留计划、价格检查和待决原因。
操作命令、冻结样本和启用条件见 [研究模拟持仓](docs/IWB_PAPER.md)。
