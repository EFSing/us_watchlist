# 关键架构决策

## 2026-11-18 · 参考审计与取舍

两仓库均按远端默认分支读取 `AGENTS.md`、`HANDOFF.md`、`docs/CURRENT_STATUS.md`、
`docs/DECISION_LOG.md`，并对照提交、关键 PR、CI 与实现。审计未发现影响本初始化的治理冲突。
A 股的本地遗留工作区有未提交改动，停在旧日报清理分支 `f213288`；审计采用远端默认分支。

| 参考 | 核实内容 | 本项目采用的设计 |
| --- | --- | --- |
| A 股 `master` `0a6e906` | #113 和 #114 已合并，抽查精确 PR head 的 correctness、`master` correctness 均成功。#113 的重点展示消费同轮 T-known manifest；历史 Score 留在 canonical/tracker，退出产品展示 | 点时冻结输入、保留缺口、报告只读投影、研究结果和正式资格分别建立证据 |
| 数据中台 `main` `eded221` | #134、#137、#139、#140 已合并且相应 PR CI 成功；#140 合并提交 CI 通过，最新 docs-only checkpoint 带 `[skip ci]`。独立的 US 收盘 reconciliation 运行有失败记录，其结果不作为可消费股票池的证据 | 采用数据中台作为上游，复用 IWB 股票池的时点与来源验证思路，保持正式入池政策的独立决策 |

A 股的主要耦合集中在 `scripts/`。B 1.1 同时调用旧 B 和 A 平台工具，策略版本与共享
计算交织。C 的 `c_daily_watchlist.py` 同时处理输入、规则和 HTML；`render_daily_close_html.py`
读 tracker 并直接调用研究模块和优选预览；`track_perf.py` 同时访问行情、读写 tracker 和聚合。
`generation_contract.py`、`b_shadow_monitor.py` 与 `b_structure_volume_observation.py`
各有 canonical JSON 实现或变体，不同版本的回放、校验脚本和 `data/` 历史材料增加了迁移面。
后续如迁移 B／C，只移植经 US 语义验证的纯计算，并在各自版本内用契约表达差异；canonical
序列化、行情读取与写入保持各自唯一入口。

数据中台的 `IwbOfficialHoldingsAdapter` 通过官方历史 `asOfDate` 查询 IWB Equity，
以响应的 `Fund Holdings as of` 为实际日期，按 XNYS 会话有界回退并保留来源及上市状态；
`select_candidate_universe` 再做历史、流动性等资格筛选。上游代码和治理同时区分候选与人工
正式策略池。本项目先冻结只读边界，实际导出接口、可用时间和正式筛选粒度需明确后接入。

证据包括 [A 股审计提交](https://github.com/EFSing/ashare_watchlist/commit/0a6e9060997df4d79f5d7d8e3bb01ac822b8296d)、
[A 股 #113](https://github.com/EFSing/ashare_watchlist/pull/113)、
[A 股 #114](https://github.com/EFSing/ashare_watchlist/pull/114)、
[A 股默认分支 CI](https://github.com/EFSing/ashare_watchlist/actions/runs/44231742747)、
[数据中台审计提交](https://github.com/EFSing/stock-data-pipeline/commit/eded221958d92b581df98af36e50c746c70b8354)、
[数据中台 #134](https://github.com/EFSing/stock-data-pipeline/pull/134)、
[数据中台 #137](https://github.com/EFSing/stock-data-pipeline/pull/137)、
[数据中台 #139](https://github.com/EFSing/stock-data-pipeline/pull/139)、
[数据中台 #140](https://github.com/EFSing/stock-data-pipeline/pull/140)、
[数据中台合并 CI](https://github.com/EFSing/stock-data-pipeline/actions/runs/44051752409)和
[独立 US reconciliation](https://github.com/EFSing/stock-data-pipeline/actions/runs/44272687086)。

## 2026-11-18 · 共享契约与单向依赖

采用 `src/` 模块化单体。只有编排层组合业务模块；计算通过不可变契约消费快照，基础合同放在
`domain`。策略版本按 US 项目独立标识。研究可扩展出量能、浪形和优选实验，审阅后通过策略 PR
晋级。行情时段、快照可用时间与资料实际日期显式建模，保证能够独立验证盘后和隔夜时点。

## 2026-11-18 · 工程基线与发布身份

采用 Python 3.12 起步，以标准库承载运行与测试，减少新机搭建成本。单个合成报告由本地集成的
原子发布器负责，一个交易日和时段只有一个相应烟测输出。相同内容可重试，不同输入或渲染内容
碰到同一身份时报错。运行产物和临时审计对象都只使用项目指定路径。

## 2026-11-18 · IWB 只读接入与 B 离线形态验证

股票池使用数据中台的完整 IWB 名单。当前从日报候选审计取回每个 seed 的日期、来源及上市状态，
逐条核对来源、唯一性和原始 seed 数。归档文件上传时间作为保守的可用时刻，避开以持仓生效日
代替实际可见时间的问题。

第一版 B 离线只验证突破回踩形态。用一套点时拆股调整的常规时段 OHLCV，存在任一预期会话
缺口的股票进入数据诊断。保持 A 股 B 的首次合格突破及回踩语义，版本在 US 仓库内独立。
历史回放、模型评估与未来收益证据分别对待。具体口径见 [B 离线验证](B_OFFLINE.md)。

## 2026-11-18 · US Candidate 与 Yahoo Chart 离线观察

使用数据中台发布的 `candidate_included_symbols` 作为 B 和后续研究策略的共同起始集合，
完整 IWB 名单用于来源校验。保持所有行业、资格及排序决策在相应的 US 策略版本中。
沿用上游直接 Yahoo Chart 能力。保存带采集时刻的原始响应和会话日历，逐股检查拆股边界。
Yahoo 快照仅形成观察日证据，缺历史可用时间和已验证拆股量能口径时标为历史点时未验证。
