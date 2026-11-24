# 当前状态

恢复基线为远端 `main`。#8、#7、#9 的合并顺序和历史基线见 [交接与合并清单](../HANDOFF.md)。
当前代码以 [main HEAD](https://github.com/EFSing/us_watchlist/commits/main/) 及其
[push CI](https://github.com/EFSing/us_watchlist/actions/workflows/ci.yml?branch=main) 为准。

## V1 工程初始化

- 已实现 Python `src/` 模块化单体、九层依赖约束、四种独立时段和合成数据烟测。
- 已提供包安装入口、合成配置、HTML 骨架、测试与 Windows／Linux GitHub Actions CI。
  具体执行结果见[审阅分支 Actions](https://github.com/EFSing/us_watchlist/actions?query=branch%3Acodex%2Fv1-project-bootstrap)。
- 研究层示范描述性量能，跟踪层保存烟测输入覆盖。正式策略绩效和 IBKR 模拟适配待独立开发。

## US Candidate 与 B 常规时段离线验证

- `b-offline` 读取 US Candidate 发布名单及校验后的常规时段历史。合成样本覆盖匹配、
  无突破、历史缺口与首次突破后回踩失败。Yahoo 采集与报告生成独立运行。
- 2026-11-17 实际名单为 1,000 只，IWB 审计为 1,021 条、活跃 1,020 条。
  B 的 76 日诊断匹配 11 只，7 只在拆股处理后历史不足。Yahoo 快照为事后取得，
  历史点时未验证。详情见 [B 离线验证](B_OFFLINE.md)。

## C 独立研究与联合日报

- `bc-offline` 使用同一已校验输入运行 B 和 C 的两套规则，生成带各版本研究记录的单文件 HTML。
  合成验证覆盖 C 独立于 B 匹配、两套规则的历史要求和单策略故障隔离。
- 11-16 的实际 Candidate 为 1,001 只，C BALANCED_A 匹配 MSCI，CONSERVATIVE_B 为零。
  11-17 的实际 Candidate 为 1,000 只，两套 C 均为零。按规则显示未匹配及历史不足。
  两轮为真实行情的事后观察，历史点时均未验证。详情见 [B+C 离线日报](BC_OFFLINE.md)。
- 通用离线入口包括烟测、B 验证和 B+C 联合日报。研究基准为常规交易时段。

## 正式基础池与真实 B+C 观察

- 正式基础池使用本项目冻结的 iShares IWB 官方权益成份。11-17 版本为 1,021 只权益证券，1,020 只有有效上市市场。11-18 目标会话的 Yahoo OHLCV 覆盖 1,020/1,020 只。
- 三组规则的形态匹配分别为 B 31、C BALANCED_A 3、C CONSERVATIVE_B 0。历史不足分别为 9、7、10。研究效果和历史点时标记为未验证。见 [IWB 日报和实际证据](IWB_DAILY.md)。
- 中文收盘日报显示股票池覆盖、规则结果和完整候选名单，按规则提供个股结构及量能卡片。未匹配列表支持搜索，原始逐股记录和输入证据可在折叠审计区下载。
- 上述 Candidate 运行使用各自归档，用于复现早期审阅证据。

## 独立收盘日报自动化

- 已实现 XNYS 收盘确认、手动补跑、限流与覆盖门槛下的有界重试、失败留证、跨 runner 恢复以及同一交易日的归档复用。
- 2026-11-18 的单次 GitHub hosted runner 手动验收成功。官方 IWB 成份覆盖 1,020 只有效上市证券，
  Yahoo 目标 OHLCV 覆盖 1,020／1,020，B／C 均衡／C 保守匹配 31／3／0，匹配集合与本地冻结版一致。
  SNDK 的云端 Yahoo 源响应只有两个交易日，三套规则各增加一条历史不足。未触发限流或重采。
- 私有 Actions 成份、规范日报、诊断归档已实际下载恢复并校验 SHA-256，保留期分别为 90、30、7 天。
  见 [验收与恢复](IWB_AUTOMATION.md#2026-11-18-hosted-runner-验收)。
- #9 配置纽约工作日 17:37 触发，按原运行创建日锁定目标，校验 XNYS 交易日、实际收盘和 Yahoo 目标日行情。
  日报列出目标日覆盖、120 日完整历史覆盖和各规则历史不足，逐股保留缺口。定时执行状态以仓库变量
  `US_IWB_SCHEDULE_ENABLED` 和 `US_IWB_VPS_SCHEDULE_ENABLED` 的实际值为准。
  [仓库变量](https://github.com/EFSing/us_watchlist/settings/variables/actions) · [运行手册](IWB_AUTOMATION.md#首次定时验收)
- #10 与 #11 已合并。2026-11-19 日报通过手动运行生成并归档，邮件步骤成功，Bark 失败分支按预期跳过。
  B 匹配 CDW、DLTR、SIRI、VIK，B 数值通过及两组 C 匹配均为 0。该运行提供邮件工作流成功证据，收件端与 Bark
  实际送达需各自的验收证据。[Actions 运行](https://github.com/EFSing/us_watchlist/actions/runs/44698935120)
- 2026-11-20 的自然定时在北京时间 11-21 11:24 创建，比计划晚 4 小时 47 分钟。
  首轮采集发布 `PARTIAL_COVERAGE`，目标日 1,019／1,020，120 日完整历史 995 只，B／C 匹配 6／0／0。
  日报和诊断 ZIP 已按 Actions digest 核对，HTML 通过 `iwb-verify`，邮件步骤成功。
  [Actions 运行](https://github.com/EFSing/us_watchlist/actions/runs/44860940918)
- VPS 接入由仓库变量切换，使用同一自动校验和归档发布组。上线状态以 VPS timer、变量回读及首次真实运行收据为准。
  [VPS 部署与回滚](IWB_AUTOMATION.md#vps-定时触发)
- 2026-11-24 北京时间 14:28，VPS 服务切换到仅限美股仓库的 GitHub App 认证。部署后申请安装令牌
  并读取工作流成功，timer 已启用。首次自然 App 触发预计为 11-25 06:37，待运行收据验收。
  [认证 PR](https://github.com/EFSing/us_watchlist/pull/16) · [合并后 CI](https://github.com/EFSing/us_watchlist/actions/runs/45340472065)

## B+C 结构、量能和参考计划

- [#6](https://github.com/EFSing/us_watchlist/pull/6) 增加 T 日价格结构、三项回踩量能及 B/C 独立的参考价位。
  11-18 的 31 个 B 形态中 5 只通过移植数值门槛，9 只处于 2→3 代理，交集为 AHR、JAN、UI。
  首页按股票代码显示通过名单和「结构研究重点观察（未验证）」。参考计划覆盖 B 30／31 和 C 3／3。
  美股正式 B 策略资格尚未建立，历史点时、拆股量能及收益效果未验证。
  详见 [公式与冻结验证](BC_REFERENCE_RESEARCH.md)。
- #7 展示 C 的两项参考止损距离。11-18 冻结样本中，CHH、GME、H 的两项距离均超过 9%。
  警示用于研究展示，C 的既有匹配和参考价位规则继续适用。见 [#7](https://github.com/EFSing/us_watchlist/pull/7)。

## IWB 研究模拟持仓

- 离线入口从原 IWB 归档生成按 B、C 均衡、C 保守分组的模拟计划，支持开盘检查、每日估值、止损、可选 R 保护和归属清晰的 R 统计。
  每日证据以连续 XNYS 会话串联，独立报告显示缺证及最近可信价格。
- 冻结复算保留 `HISTORICAL_REPLAY` 标识。11-18 的 33 条有效价位在次日检查中有 19 条开盘未触发，14 条研究入场资格待定，
  另有 4 条 11-19 新计划待检查。前瞻模式等待入场、退出和长期归档决策。[口径、台账与验收](IWB_PAPER.md)
- V2 在独立离线研究身份内提供共享硬止损、可选结构移动止损、R 利润保护和结构破坏次日退出。
  B 保留回踩代理，C 保留各自的两处低点及反弹锚点。入场资格和可调参数须显式按组设置。
  [V2 配置及优先级](IWB_PAPER.md#bc-统一持仓协议-v2)
- 离线入口将 B/C 筛选与模拟持仓合成一份 HTML。原日报机器记录继续作为账本的冻结依据。

## 后续需决定

1. 核对新调度入口上线并取得实际运行收据，按周导出、按月封存研究证据。
2. 原始行情和成份证据的长期访问及保存权限。审阅版使用 10 个自然日的 IWB 持仓滞后上限。
3. 美股点时行情、拆股价格和量能的来源及长期留档。B 数值移植需审阅，正式 US 资格、市场口径及成本收益仍需独立验证。
4. 如后续要扩展生产时段或 IBKR 模拟执行，另行决定具体会话、成交、成本和部署口径。
