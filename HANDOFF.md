# 跨设备恢复

当前交付为 US Candidate、Yahoo Chart 共用输入、B 形态及两套 C 规则和联合日报。
审阅顺序为工程初始化 Draft [#1](https://github.com/EFSing/us_watchlist/pull/1)、
共用输入和 B 修正 Draft [#2](https://github.com/EFSing/us_watchlist/pull/2)、
以及以 #2 分支为基线的 [C 和联合日报 Draft](https://github.com/EFSing/us_watchlist/pulls?q=is%3Apr+head%3Acodex%2Fus-c-joint-offline)。
合并前使用 GitHub 核对准确 HEAD、基线和 CI。

全新 Windows 设备使用唯一目标路径，在其为空时执行。

```powershell
git clone --branch codex/us-c-joint-offline https://github.com/EFSing/us_watchlist.git D:\ChatGPT\archive\us_stock_watchlist
Set-Location -LiteralPath D:\ChatGPT\archive\us_stock_watchlist
git status --short --branch
```

已有 checkout 从根目录检查本地改动，然后 `git fetch origin --prune`，切换相同分支并在可快进时
执行 `git pull --ff-only`。按 [README](README.md) 安装包，运行测试、`smoke`、`b-offline` 和
`bc-offline`。真实结果、归档出处及 SHA 见 [B+C 离线日报](docs/BC_OFFLINE.md)。
11-16 和 11-17 的真实 ZIP、清单和报告在本机 `.runtime/data/` 和 `.runtime/artifacts/bc-offline/`。
历史点时待验证。下一步是审阅，并决定点时行情、拆股量能与长期证据存储来源。
