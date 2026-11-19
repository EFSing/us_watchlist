# 跨设备恢复

从 `codex/us-research-daily-plans` 恢复本轮审阅。最终验收时 `main` 为 `7c7761a`，六项 PR 均为 Draft，
每项基线为上一项的 HEAD。合并前从 GitHub 重新核对各基线、HEAD 和 CI。

| 顺序 | 范围 | 本轮核对的 HEAD 和 CI |
| --- | --- | --- |
| [#1](https://github.com/EFSing/us_watchlist/pull/1) | 工程骨架及依赖约束 | `b5e341b` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44282595287) |
| [#2](https://github.com/EFSing/us_watchlist/pull/2) | Candidate、共用行情及 B 形态 | `bbb43e5` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44301093073) |
| [#3](https://github.com/EFSing/us_watchlist/pull/3) | C 两套规则及联合日报 | `b3c085e` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44305791841) |
| [#4](https://github.com/EFSing/us_watchlist/pull/4) | IWB 官方基池及中文日报 | `eccab3e` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44452538909) |
| [#5](https://github.com/EFSing/us_watchlist/pull/5) | 手动审阅工作流及归档恢复 | `3121d5b` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44452539315) |
| [#6](https://github.com/EFSing/us_watchlist/pull/6) | 结构、量能、参考计划及首页 | [审阅分支 push CI](https://github.com/EFSing/us_watchlist/actions?query=branch%3Acodex%2Fus-research-daily-plans+event%3Apush)，按最新 HEAD 核对 |

`PROJECT_GOVERNANCE_STATE_CONFLICT` 已核对。#5 描述的 [CI 链接](https://github.com/EFSing/us_watchlist/actions/runs/44449651887)
对应旧 HEAD `ab5db7a`。当前验收证据使用表中的 push CI 及 [`3121d5b` 的 PR CI](https://github.com/EFSing/us_watchlist/actions/runs/44452545394)，
二者均成功。11-16 和 11-17 的 Candidate／Yahoo 证据按历史口径恢复。当前正式基础池采用 iShares IWB 官方权益成份。

全新 Windows 设备在唯一目标路径为空时执行。

```powershell
git clone --branch codex/us-research-daily-plans https://github.com/EFSing/us_watchlist.git D:\ChatGPT\archive\us_stock_watchlist
Set-Location -LiteralPath D:\ChatGPT\archive\us_stock_watchlist
git status --short --branch
```

已有 checkout 先检查本地改动，再 `git fetch origin --prune`，切换审阅分支并在可快进时执行 `git pull --ff-only`。按 [README](README.md) 安装并运行测试、`smoke`、`b-offline`、`bc-offline`。

11-16 和 11-17 的官方 IWB 原件在本机 `.runtime/data/iwb/`，11-18 的真实报告和冻结输入在 `.runtime/data/iwb-validation/2026-11-18/`。基池、覆盖与来源 SHA 见 [实测记录](docs/IWB_DAILY.md)。早期 Candidate 原件和 HTML 仍在 `.runtime/data/` 和 `.runtime/artifacts/bc-offline/`。真实归档通过原件与清单恢复。

11-18 中文报告从同一份输入复渲染，位于本机 `.runtime/data/iwb-validation/2026-11-18-zh/report.html`。
逐股机器记录及输入身份核验见 [中文日报复渲染](docs/IWB_DAILY.md#中文日报复渲染)。

11-18 最终验收版在 `.runtime/data/iwb-validation/2026-11-18-final-review/report.html`。首页显示 B 数值门槛通过 5 只，
其中 3 只同时处于 2→3 价格结构代理，标为「结构研究重点观察（未验证）」。B 31、C 3／0，2→3 代理共 9 只。
旧研究版留在 `2026-11-18-research/`。冻结对照与 HTML SHA-256 见 [B+C 参考研究](docs/BC_REFERENCE_RESEARCH.md)。

下一步等待合并授权。获准后按 #1 → #6 处理，逐项将基线指向 `main`，核对原审阅 HEAD 与逐层差异，
使用 merge commit 保留各 HEAD，并核对每步 `main` 的 CI。合并与手动派发分别授权。Hosted runner 的实时 Yahoo
可达性及真实日报归档仍待手动验收。正式调度和通知关闭，IBKR 未接入执行。归档及恢复见 [自动化说明](docs/IWB_AUTOMATION.md)。
