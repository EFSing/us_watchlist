# 跨设备恢复

从远端默认分支 `main` 恢复。以 GitHub 上的分支 HEAD、PR 合并提交和对应 push CI 为准。
恢复时核对 [main 提交](https://github.com/EFSing/us_watchlist/commits/main/)、
[main CI](https://github.com/EFSing/us_watchlist/actions/workflows/ci.yml?branch=main)和
[当前状态](docs/CURRENT_STATUS.md)。

| 已合并 PR | `main` 合并提交 | 合并 CI |
| --- | --- | --- |
| [#1](https://github.com/EFSing/us_watchlist/pull/1) | `4dba2eb0c173a610b1b7c586675d4a7f81fd1ee4` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472242242) |
| [#2](https://github.com/EFSing/us_watchlist/pull/2) | `fafd06847b5d21b55a956c59a58ccdbc234c9a9f` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472384982) |
| [#3](https://github.com/EFSing/us_watchlist/pull/3) | `345891a0073e30c7b2d9e369d1aa519010de1840` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472535095) |
| [#4](https://github.com/EFSing/us_watchlist/pull/4) | `d7fdcaff839df0c5941f7c6b2497ad14de42393c` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472675353) |
| [#5](https://github.com/EFSing/us_watchlist/pull/5) | `75074995e1f7c6b0424dd2592696a8bd5f1cfbc0` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44472860181) |
| [#6](https://github.com/EFSing/us_watchlist/pull/6) | `60c04f24986cf90ad65fd7a52322041aa980edc7` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44473004144) |
| [#8](https://github.com/EFSing/us_watchlist/pull/8) | `5875fb9b671e634382aa718555d0eeaffc519cad` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44483134656) |
| [#7](https://github.com/EFSing/us_watchlist/pull/7) | `daca05278c0082ce00518c145a244a029d84ee90` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44483393328) |
| [#9](https://github.com/EFSing/us_watchlist/pull/9) | [PR 合并记录](https://github.com/EFSing/us_watchlist/pull/9) | [按合并 SHA 核对 main push CI](https://github.com/EFSing/us_watchlist/actions/workflows/ci.yml?branch=main) |
| [#10](https://github.com/EFSing/us_watchlist/pull/10) | `a5a470f918247b57133870a160d1f5a5eb9846cd` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44695960917) |
| [#11](https://github.com/EFSing/us_watchlist/pull/11) | `2381431379ac477e25e958ad826453f34b1d5a71` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44698052180) |
| [#12](https://github.com/EFSing/us_watchlist/pull/12) | `a6374739fc5fa8a0743b0ef4cb1cf2fc50c15ee3` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44707934071) |
| [#13](https://github.com/EFSing/us_watchlist/pull/13) | `e575783bc49296880891d3786dc6b9c64352ff71` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44710011716) |
| [#14](https://github.com/EFSing/us_watchlist/pull/14) | `850064f41fc74f8fbee7e9ea230a90f970990e81` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/45317211563) |
| [#16](https://github.com/EFSing/us_watchlist/pull/16) | `75f1874478686f622069d31011bd564f295ef698` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/45340472065) |

## 2026-11-24 VPS 认证迁移

北京时间 14:28，VPS 生产服务切换到仅安装在本仓库的 [GitHub App](https://github.com/settings/installations/185271631)。
部署后的只读认证检查返回 `IWB_VPS_GITHUB_APP_AUTH_OK`，`US_IWB_VPS_SCHEDULE_ENABLED=true`。
私钥在 VPS 的 `/etc/us-iwb-dispatch/github-app.pem`，属主 root，权限 `0600`。

timer 已启用并等待北京时间 11-25 06:37。首次自然 App 触发待验收，从服务日志取得运行链接，
核对触发来源、纽约目标日、日报归档和邮件。切换前的 [11-23 日报](https://github.com/EFSing/us_watchlist/actions/runs/45318327898)
验证了 VPS 调度通道。旧服务和脚本备份在 VPS 的 `/etc/us-iwb-dispatch/rollback-pat.xdCTghLt`，
旧 PAT 留作回滚。见 [VPS 运行手册](docs/IWB_AUTOMATION.md#vps-定时触发)。

## 2026-11-24 调度核对

`PROJECT_GOVERNANCE_STATE_CONFLICT` 已核对。旧交接停在 #12 且保留首次自然定时待验收的记录。
GitHub 确认 #13 已合并、对应 push CI 成功，11-20 的[自然运行](https://github.com/EFSing/us_watchlist/actions/runs/44860940918)
已有新采集、日报归档及邮件成功证据。核验版归档在 `.runtime/data/iwb-validation/2026-11-20-hosted-44860940918/`。
VPS 接管后，以仓库变量、timer 状态和真实运行收据核对启用状态。见 [VPS 切换](docs/IWB_AUTOMATION.md#vps-定时触发)。

## 2026-11-20 接手与模拟研究审阅

`PROJECT_GOVERNANCE_STATE_CONFLICT` 已核对。接手时本地 `main` 和恢复表停在 #9，
远端已合并至 #11。以合并 SHA 和对应 push CI 更新本地分支及上表。仓库定时变量读取为 `true`。
2026-11-19 的 [运行 44698935120](https://github.com/EFSing/us_watchlist/actions/runs/44698935120)
是 `workflow_dispatch`，日报归档和邮件步骤成功，继续单独核对首次自然定时运行。

研究模拟持仓已随 #12 合并。离线账本、日报视图、两日冻结复算和规则待决项见
[研究模拟持仓](docs/IWB_PAPER.md)。11-19 冻结归档在
`.runtime/data/iwb-validation/2026-11-19-hosted-44698935120/daily/`。
生产启用的阻碍是 B/C 专属模拟政策、前瞻证据的可用时间和长期账本恢复约定。

合并时的 `PROJECT_GOVERNANCE_STATE_CONFLICT` 已核对，原交接将 #12 标为 Draft，当前以
上表的合并 SHA 和 push CI 为准。使用 `iwb-paper --protocol us_iwb_paper_position_v2` 建立离线链，
输出一份包含筛选和模拟持仓的 `report.html`。V1 继续复原原研究。先审阅各组资格和退出参数，再扩大历史对照样本。

## 历史验收与调度

`PROJECT_GOVERNANCE_STATE_CONFLICT` 已通过 #8 处理。合并前 `main` 的恢复文档仍将 #1～#6 列为
Draft，GitHub 确认它们已合并且对应 CI 成功。旧审阅状态保留在下方快照。

#9 将纽约工作日 17:37 的 B+C 研究日报配置纳入 `main`。核对 `main` CI 和工作流后，按本轮授权设置
`US_IWB_SCHEDULE_ENABLED=true`。每次恢复以 [仓库 Actions 变量](https://github.com/EFSing/us_watchlist/settings/variables/actions)
的实际值和 [日报工作流状态](https://github.com/EFSing/us_watchlist/actions/workflows/iwb-daily.yml) 为准。
启用时要求首个 XNYS 交易日的自然 `schedule` 留存实际时间、覆盖、逐股异常、研究结果和归档 SHA-256。
每周在 7 天诊断到期前导出证据，每月封存并抽样复验，长期位置须经批准。
见 [首次定时验收](docs/IWB_AUTOMATION.md#首次定时验收)及[长期证据](docs/IWB_AUTOMATION.md#长期前瞻研究证据)。

## 2026-11-18 手动验收快照

2026-11-18 的 hosted runner 手动验收已完成，仅从 `main` 派发一次，持仓日期留空。
目标日覆盖 1,020／1,020，B 31、C 均衡 3、C 保守 0，三个私有产物已下载并校验。
SNDK 云端原件只有两个交易日行情，三套规则各多一条历史不足。
详见 [验收与恢复](docs/IWB_AUTOMATION.md#2026-11-18-hosted-runner-验收)和 [Actions 运行](https://github.com/EFSing/us_watchlist/actions/runs/44476972797)。

## #8、#7、#9 初始审阅快照

#8 与 #7 基于 #6 的合并提交，改动文件互不重叠。#9 草稿以 #8 的审阅 HEAD 为基线。

| 审阅项 | HEAD | 精确 HEAD 的 PR CI |
| --- | --- | --- |
| [#8 治理与手动验收](https://github.com/EFSing/us_watchlist/pull/8) | `ac0b071808d4c85b0432793bf877dc98cab17f1d` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44478000058) |
| [#7 C 止损距离](https://github.com/EFSing/us_watchlist/pull/7) | `6175df50d5e0ce2e71def1237ead9ef0d446d4d9` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44477617153) |
| [#9 定时草稿](https://github.com/EFSing/us_watchlist/pull/9) | `b6c2e7841279e988721ac943d96122d169e8b088` | [成功](https://github.com/EFSing/us_watchlist/actions/runs/44481801423) |

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
