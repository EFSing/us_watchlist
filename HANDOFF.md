# 跨设备恢复

从 `main` 恢复。2026-11-19 已核对远端默认分支 `main` 为
`60c04f24986cf90ad65fd7a52322041aa980edc7`，#1～#6 均已合并，六个合并提交的 CI 均成功。
`PROJECT_GOVERNANCE_STATE_CONFLICT` 已核对。下方 Draft 快照属于合并前审阅，当前操作依据为本节和
[当前状态](docs/CURRENT_STATUS.md)。

| 已合并 PR | `main` 合并提交 | 合并 CI |
| --- | --- | --- |
| [#1](https://github.com/EFSing/us_watchlist/pull/1) | `4dba2eb0c173a610b1b7c586675d4a7f81fd1ee4` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472242242) |
| [#2](https://github.com/EFSing/us_watchlist/pull/2) | `fafd06847b5d21b55a956c59a58ccdbc234c9a9f` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472384982) |
| [#3](https://github.com/EFSing/us_watchlist/pull/3) | `345891a0073e30c7b2d9e369d1aa519010de1840` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472535095) |
| [#4](https://github.com/EFSing/us_watchlist/pull/4) | `d7fdcaff839df0c5941f7c6b2497ad14de42393c` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472675353) |
| [#5](https://github.com/EFSing/us_watchlist/pull/5) | `75074995e1f7c6b0424dd2592696a8bd5f1cfbc0` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472860181) |
| [#6](https://github.com/EFSing/us_watchlist/pull/6) | `60c04f24986cf90ad65fd7a52322041aa980edc7` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44473004144) |

2026-11-18 的 hosted runner 手动验收已完成，仅从 `main` 派发一次，持仓日期留空。
覆盖 1,020／1,020，B 31、C 均衡 3、C 保守 0，三个私有产物已下载并校验。
已具备单独申请每日定时的运行证据，实际启用待授权。正式定时和通知关闭，IBKR 执行未接入。
详见 [验收与恢复](docs/IWB_AUTOMATION.md#2026-11-18-hosted-runner-验收)和 [Actions 运行](https://github.com/EFSing/us_watchlist/actions/runs/44476972797)。

当前独立审阅分支为 `codex/iwb-hosted-acceptance-governance`（本次治理及验收证据）和
`codex/iwb-c-reference-stop-risk`（C 止损距离与研究风险警示）。[C 审阅 PR #7](https://github.com/EFSing/us_watchlist/pull/7)

## 合并前审阅快照

原审阅从 `codex/us-research-daily-plans` 恢复，当时 `main` 为 `7c7761a`，六项 PR 均为 Draft，
每项基线为上一项的 HEAD。

| 顺序 | 范围 | 当时核对的 HEAD 和 CI |
| --- | --- | --- |
| [#1](https://github.com/EFSing/us_watchlist/pull/1) | 工程骨架及依赖约束 | `b5e341b` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44282595287) |
| [#2](https://github.com/EFSing/us_watchlist/pull/2) | Candidate、共用行情及 B 形态 | `bbb43e5` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44301093073) |
| [#3](https://github.com/EFSing/us_watchlist/pull/3) | C 两套规则及联合日报 | `b3c085e` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44305791841) |
| [#4](https://github.com/EFSing/us_watchlist/pull/4) | IWB 官方基池及中文日报 | `eccab3e` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44452538909) |
| [#5](https://github.com/EFSing/us_watchlist/pull/5) | 手动审阅工作流及归档恢复 | `3121d5b` [push CI](https://github.com/EFSing/us_watchlist/actions/runs/44452539315) |
| [#6](https://github.com/EFSing/us_watchlist/pull/6) | 结构、量能、参考计划及首页 | [审阅分支 push CI](https://github.com/EFSing/us_watchlist/actions?query=branch%3Acodex%2Fus-research-daily-plans+event%3Apush)，按最新 HEAD 核对 |

合并前另一次 `PROJECT_GOVERNANCE_STATE_CONFLICT` 涉及 #5 描述的 [CI 链接](https://github.com/EFSing/us_watchlist/actions/runs/44449651887)，
对应旧 HEAD `ab5db7a`。当时审阅采用表中的 push CI 及 [`3121d5b` 的 PR CI](https://github.com/EFSing/us_watchlist/actions/runs/44452545394)，
二者均成功。11-16 和 11-17 的 Candidate／Yahoo 证据按历史口径恢复。当前正式基础池采用 iShares IWB 官方权益成份。

## 工作树与冻结证据恢复

全新 Windows 设备在唯一目标路径为空时执行。

```powershell
git clone --branch main https://github.com/EFSing/us_watchlist.git D:\ChatGPT\archive\us_stock_watchlist
Set-Location -LiteralPath D:\ChatGPT\archive\us_stock_watchlist
git status --short --branch
```

已有 checkout 先检查本地改动，再 `git fetch origin --prune`，切换 `main` 并在可快进时执行
`git pull --ff-only`。需要评审具体改动时切换到对应 PR 分支。按 [README](README.md) 安装并运行测试、
`smoke`、`b-offline`、`bc-offline`。

11-16 和 11-17 的官方 IWB 原件在本机 `.runtime/data/iwb/`，11-18 的真实报告和冻结输入在 `.runtime/data/iwb-validation/2026-11-18/`。基池、覆盖与来源 SHA 见 [实测记录](docs/IWB_DAILY.md)。早期 Candidate 原件和 HTML 仍在 `.runtime/data/` 和 `.runtime/artifacts/bc-offline/`。真实归档通过原件与清单恢复。

11-18 中文报告从同一份输入复渲染，位于本机 `.runtime/data/iwb-validation/2026-11-18-zh/report.html`。
逐股机器记录及输入身份核验见 [中文日报复渲染](docs/IWB_DAILY.md#中文日报复渲染)。

11-18 最终验收版在 `.runtime/data/iwb-validation/2026-11-18-final-review/report.html`。首页显示 B 数值门槛通过 5 只，
其中 3 只同时处于 2→3 价格结构代理，标为「结构研究重点观察（未验证）」。B 31、C 3／0，2→3 代理共 9 只。
旧研究版留在 `2026-11-18-research/`。冻结对照与 HTML SHA-256 见 [B+C 参考研究](docs/BC_REFERENCE_RESEARCH.md)。

本轮从私有 Actions 恢复的日报、持仓和运行收据位于
`.runtime/data/iwb-validation/2026-11-18-hosted-44476972797/`，分别存于 `daily/`、`pool/` 和 `attempt/`。
