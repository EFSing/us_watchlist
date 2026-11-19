# 跨设备恢复

从 `codex/us-iwb-daily-automation` 恢复日常审阅。审查和未来合并顺序为 [#1 工程骨架](https://github.com/EFSing/us_watchlist/pull/1) → [#2 共用行情和 B](https://github.com/EFSing/us_watchlist/pull/2) → [#3 C 和联合日报](https://github.com/EFSing/us_watchlist/pull/3) → [#4 IWB 官方基池及中文日报](https://github.com/EFSing/us_watchlist/pull/4) → [#5 独立日报自动化](https://github.com/EFSing/us_watchlist/pull/5)。合并前从 GitHub 重新核对各基线、HEAD 和 CI。若采用 squash 或 rebase，逐层更新后续 PR 基线并复核差异及 CI。

本轮审计核验 #1 `b5e341b`、#2 `bbb43e5`、#3 `b3c085e` 的堆叠及 Windows／Linux CI。11-16 和 11-17 的 Candidate／Yahoo 观察以同一 SHA 的 HTML 重新生成。正式股票池决策更新为 iShares IWB 官方权益成份，历史 Candidate 入口保留原含义。[#1 CI](https://github.com/EFSing/us_watchlist/actions/runs/44282631026) · [#2 CI](https://github.com/EFSing/us_watchlist/actions/runs/44301101372) · [#3 CI](https://github.com/EFSing/us_watchlist/actions/runs/44311422189)

全新 Windows 设备在唯一目标路径为空时执行。

```powershell
git clone --branch codex/us-iwb-daily-automation https://github.com/EFSing/us_watchlist.git D:\ChatGPT\archive\us_stock_watchlist
Set-Location -LiteralPath D:\ChatGPT\archive\us_stock_watchlist
git status --short --branch
```

已有 checkout 先检查本地改动，再 `git fetch origin --prune`，切换审阅分支并在可快进时执行 `git pull --ff-only`。按 [README](README.md) 安装并运行测试、`smoke`、`b-offline`、`bc-offline`。

11-16 和 11-17 的官方 IWB 原件在本机 `.runtime/data/iwb/`，11-18 的真实报告和冻结输入在 `.runtime/data/iwb-validation/2026-11-18/`。基池、覆盖与来源 SHA 见 [实测记录](docs/IWB_DAILY.md)。早期 Candidate 原件和 HTML 仍在 `.runtime/data/` 和 `.runtime/artifacts/bc-offline/`。真实归档通过原件与清单恢复。

11-18 中文报告从同一份输入复渲染，位于本机 `.runtime/data/iwb-validation/2026-11-18-zh/report.html`。
逐股机器记录及输入身份核验见 [中文日报复渲染](docs/IWB_DAILY.md#中文日报复渲染)。

下一步是审查 Draft 栈。获得合并授权后，通过手动派发验证 hosted runner 的 Yahoo 和报告归档，再单独审查定时启用。当前生产调度和通知关闭。归档有限留存、补跑及恢复见 [自动化说明](docs/IWB_AUTOMATION.md)。长期归档、历史点时行情与拆股量能等待来源和存储决策。
