# 跨设备恢复

当前交付为美股交易系统 V1 初始化。审阅分支为 `codex/v1-project-bootstrap`，PR 基线为
`main`。通过 GitHub 确认该分支的 Draft PR、最新 HEAD 和 CI。详见
[仓库](https://github.com/EFSing/us_watchlist)和[审阅分支的 PR](https://github.com/EFSing/us_watchlist/pulls?q=is%3Apr+head%3Acodex%2Fv1-project-bootstrap)。

全新 Windows 设备使用唯一目标路径，在其为空时执行。

```powershell
git clone --branch codex/v1-project-bootstrap https://github.com/EFSing/us_watchlist.git D:\ChatGPT\archive\us_stock_watchlist
Set-Location -LiteralPath D:\ChatGPT\archive\us_stock_watchlist
git status --short --branch
```

已有 checkout 从根目录检查本地改动，然后 `git fetch origin --prune`，切换相同分支并在可快进时
执行 `git pull --ff-only`。按 [README](README.md) 安装包、运行测试和离线烟测。
这些验证只需仓库代码和 Python 构建依赖。CI、远端分支与合并状态在 GitHub 实时查看。

当前交付止于审阅。关于真实数据接入和正式策略的决策列在 [CURRENT_STATUS.md](docs/CURRENT_STATUS.md)。
