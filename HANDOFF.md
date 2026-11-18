# 跨设备恢复

当前交付为 IWB 股票池与 B 常规时段离线验证。审阅分支为 `codex/iwb-b-offline`，以
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
合成验证只需仓库代码和 Python 构建依赖。真实 IWB 归档抽查与本地输入契约见
[B 离线验证](docs/B_OFFLINE.md)。下一步是审阅，并确定可追溯的美股点时行情和拆股数据来源。
