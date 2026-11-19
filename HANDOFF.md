# 跨设备恢复

当前交付为实际 US Candidate、Yahoo Chart 共用离线输入和 B 形态验证。审阅分支为 `codex/iwb-b-offline`，以
初始化 Draft PR [#1](https://github.com/EFSing/us_watchlist/pull/1) 的分支为基线。
通过 GitHub 查看[本分支的 PR](https://github.com/EFSing/us_watchlist/pulls?q=is%3Apr+head%3Acodex%2Fiwb-b-offline)
及 CI。若基线先进入 `main`，核对提交关系后再调整本 PR 的目标分支。

全新 Windows 设备使用唯一目标路径，在其为空时执行。

```powershell
git clone --branch codex/iwb-b-offline https://github.com/EFSing/us_watchlist.git D:\ChatGPT\archive\us_stock_watchlist
Set-Location -LiteralPath D:\ChatGPT\archive\us_stock_watchlist
git status --short --branch
```

已有 checkout 从根目录检查本地改动，然后 `git fetch origin --prune`，切换相同分支并在可快进时
执行 `git pull --ff-only`。按 [README](README.md) 安装包，运行测试、`smoke` 和 `b-offline`。
真实 Candidate 归档、120 个会话的 Yahoo 观察与 B 形态结果见 [B 离线验证](docs/B_OFFLINE.md)。
归档和 Yahoo 快照均在目标收盘后取得，历史点时标为未验证。下一步是审阅，并确定可追溯的
美股点时行情与拆股量能来源。
