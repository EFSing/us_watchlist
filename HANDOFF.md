# 跨设备恢复

本分支审阅 IWB 官方基池和中文收盘日报。先审阅 [#1 工程骨架](https://github.com/EFSing/us_watchlist/pull/1)、
[#2 共用行情和 B](https://github.com/EFSing/us_watchlist/pull/2) 与 [#3 C 和联合日报](https://github.com/EFSing/us_watchlist/pull/3)，
再审阅 [#4 IWB 日报](https://github.com/EFSing/us_watchlist/pull/4) 及后续 [#5 自动化](https://github.com/EFSing/us_watchlist/pull/5)。
审阅前用 GitHub 核对准确 HEAD、基线和 CI。调度与通知仍待独立授权。

全新 Windows 设备使用唯一目标路径，在其为空时执行。

```powershell
git clone --branch codex/us-iwb-foundation https://github.com/EFSing/us_watchlist.git D:\ChatGPT\archive\us_stock_watchlist
Set-Location -LiteralPath D:\ChatGPT\archive\us_stock_watchlist
git status --short --branch
```

已有 checkout 从根目录检查本地改动，然后 `git fetch origin --prune`，切换相同分支并在可快进时
执行 `git pull --ff-only`。按 [README](README.md) 安装包，运行测试、`smoke`、`b-offline` 和
`bc-offline`。11-18 的原报告与冻结输入位于 `.runtime/data/iwb-validation/2026-11-18/`，
中文复渲染位于 `.runtime/data/iwb-validation/2026-11-18-zh/report.html`。见 [实测记录](docs/IWB_DAILY.md)。
下一步是审阅 Draft。历史点时、拆股量能、研究效果及长期存储来源仍待验证或决策。
