# IWB B+C 研究模拟持仓

离线研究账本从已经发布的 IWB 归档读取 B 突破回踩和 C 均衡的逐股筛选及参考计划。
历史三规则归档中的 C 保守也按原契约校验并写入账本。同一研究链可以从三规则归档推进到双规则归档。
新模拟政策仅可配置 B 突破回踩和 C 均衡，绩效表只在有 C 保守历史计划时列出该规则。
打开 `iwb-paper` 输出目录中的 `report.html`，可在同一份日报查看筛选结果和模拟持仓。页首的
「模拟持仓」直接跳到仓位区，待检查计划、当日记录、绩效和模拟来源可展开。
本地命令无需网络或 SMTP。Actions 可显式启用独立的前瞻账本和邮件伴随视图。

## 美股 B V2 单账户模拟

默认配置见 [iwb_paper_us_b_v2.json](../configs/iwb_paper_us_b_v2.json)。该配置允许
`us_breakout_retest_v2` 的 `B_NUMERIC_QUALIFIED:UNKNOWN` 组以一个模拟单位成交。
开盘检查要求实际 RR 至少 1.8、目标余量至少 4%、开盘溢价至多 3%，并要求开盘在结构底线上方。
持仓使用 V2 结构退出、已确认低点与 ATR14 × 0.5 止损及 2R 触发、回吐 1R 的利润保护。
C 均衡继续作为研究观察。

- 每账户最多持有 8 只，每个 XNYS 会话最多新开 3 只。股票及发行人身份用共用 IWB 映射。
  已持有同股或同发行人时拒绝再开。退出日起立即进入冷却，随后 5 个 XNYS 会话也禁止重开，第 6 个会话可重新检查。
- 预约开盘退出和开盘跳空止损在开盘先结算并释放名额。盘中触及止损的持仓在该次开盘占用名额。
  当日新开并止损的成交同样计入当日新开仓额度。行情缺证的存量持仓继续占用名额。
- T+1 开盘按原日报核心精选次序检查，非精选按首次转强、2→3 阶段、参考入场止损距离升序、计划 RR 降序和代码排序。
  若设置 `core_only: true`，仅检查原日报核心精选。价格门槛通过后依次检查重复、冷却、开放仓位上限和当日新开仓上限。
- V2 省略 `_account` 时沿用逐信号独立模拟，候选排序字段和发行人身份只在单账户账本冻结。
  配置和协议共同决定研究身份，已有研究从原首日和原配置恢复。

## PROSPECTIVE 前瞻运行

`iwb-paper` 的默认模式为 `historical-replay`。显式传入 `--mode prospective` 时默认选择 V2，
新会话使用 `--available-at` 传入可核验的 UTC 发布时间。恢复已冻结的会话时直接使用账本内的可用时间。

```powershell
us-watchlist iwb-paper --mode prospective --ledger-root $ledger --start-date $tradeDate --trade-date $tradeDate --directory $verifiedDaily --policy configs/iwb_paper_us_b_v2.json --initialize --available-at $publishedAtUtc
```

Actions 以 runner 核验本轮规范日报的实时时刻、或 GitHub 既有规范日报归档的 `created_at` 作为可用时间。
归档时间晚于 T+1 开盘的信号没有模拟成交。需要盘后决策的开放仓位在下一开盘前缺少可用证据时停更。
历史冻结数据的重新筛选属于 `HISTORICAL_REPLAY`，使用原行情采集时间作为复算口径。

PR-3 合并且对应 `main` CI 通过后，在 [仓库 Actions Variables](https://github.com/EFSing/us_watchlist/settings/variables/actions)
先设置 `US_IWB_PAPER_START_DATE=YYYY-MM-DD`，使用拟开始跟踪的 XNYS 交易日，再设置 `US_IWB_PAPER_ENABLED=true`。
部署、失败恢复和邮件规则见 [自动化运行手册](IWB_AUTOMATION.md#启用前瞻单账户模拟)。

## 原始协议的样本与成交口径

| 环节 | 口径 |
| --- | --- |
| 信号日 T | 先校验 IWB 收据、文件 SHA-256、股票池、Yahoo 原件及 XNYS 会话，逐一对照同一归档的筛选记录和研究匹配。每个模式、起始交易日、政策、协议、策略、股票和信号日得到稳定计划身份。重复出现的股票可形成独立样本。 |
| 研究资格 | 分别保存匹配、B 数值通过／未通过／缺证、C 策略版本、风险警示及模拟样本开关。同一计划留存结构、三项量能及坐标、参考触发／止损／目标／RR 和输入出处。旧归档缺少警示字段时显示未知。缺参考价位或信号日价格证据的样本直接标为 `UNAVAILABLE`。 |
| T+1 开盘 | 仅检查下一个实际 XNYS 会话。要求 T 的采集时间早于该开盘，T+1 只使用常规时段开盘价判定。当开盘小于触发、达到或跌破止损、达到或超过目标时标记 `NOT_FILLED`。在合法区间内记录实际 RR、目标相对开盘的剩余空间和开盘相对参考入场的溢价。无配置时合法价位样本标记 `UNAVAILABLE`。 |
| 资格启用 | 每个策略与研究资格组必须显式设置条目。已提供政策但未选入的资格组标记 `NOT_FILLED` 并保存原因。每个启用组显式指定实际 RR 下限、目标余量下限、开盘溢价上限及退出模型。阈值比较含边界，JSON 数字字符串是十进制比例；`null` 明确表示该指标没有附加阈值。 |
| 持仓和固定止损 | 开盘成交后按每日收盘估值。开盘达到或跌破生效止损时以开盘退出，否则当日最低价触及生效止损时以止损价退出。MFE、MAE 与 R 使用实际入场价减初始止损作为 1R。止损日只计入已知在退出前的开盘和模拟退出价，避免把后续日内波动写进持仓。 |
| 利润保护研究模型 | 可显式选 `LEGACY_R_PROTECTION`。沿用参考系统的 MFE 达到 2R 后保留 MFE 减 1R 的保护线。收盘跌破保护线，下一实际交易日开盘退出；否则上调从下一会话开始生效的止损。先检查当日已有止损，再使用完整日线更新保护线。也可选择 `FIXED_STOP`。 |
| 结构及目标 | 使用归档中的当日同策略结构或筛选原因供观察。达到目标是里程碑，日线同日触及止损和目标时仅确认已知顺序。策略专属的结构退出及 ATR 向上移动止损未启用。 |
| 绩效 | 每个计划使用一个模拟单位。记录每单位美元变动、价格收益率及 R，均为毛值，未建模滑点、费用、股息、资金预算和组合收益。按策略、B 数值资格及风险组统计。胜率以已结束记录为分母，盈利指已实现 R 大于 0。缺证停更的开放持仓仍计为开放，使用最后一次可信估值并标记过期。 |

参考审计锁定 `EFSing/stock-data-pipeline` 的 `eded221958d92b581df98af36e50c746c70b8354`。
该版本只跟踪新确认且 `ENTRY_ALLOWED` 的 Setup 事件，在 T+1 以开盘处理入场区间、目标余量及实际 RR；
管理规则还消费该系统特有的结构锚点、swing 和 ATR。本项目采用其中的会话、固定止损及可显式选择的 R 保护语义。
B/C 的资格、入场区间及适用退出模型由本项目独立审阅。
[参考账本](https://github.com/EFSing/stock-data-pipeline/blob/eded221958d92b581df98af36e50c746c70b8354/trading/paper_lifecycle.py)
· [参考持仓管理](https://github.com/EFSing/stock-data-pipeline/blob/eded221958d92b581df98af36e50c746c70b8354/trading/position_management.py)

## 账本与恢复

- 路径为 `<ledger-root>/HISTORICAL_REPLAY/<study-sha>/<trade-date>/`。同研究保留 `study.json`、
  每个会话的 `day.json` 和输入归档。日记录只保存所需候选、价位、行情诊断与原归档身份，绑定前一实际会话的
  SHA-256。恢复从明确的首日重放至目标日，由同一协议产生完整状态事件及合计。
- 首日使用 `--initialize` 显式创建研究。后续运行缺清单或任何前序会话时失败。保存 CLI 输出的账本摘要，下一日可传
  `--expect-previous <SHA-256>` 和独立收据核对。恢复需要对应协议的代码和政策，保留整个链和最后可信摘要，
  从只读备份取回缺失原件。幂等重试复用同一日记录，不同内容竞争同一身份时保留先写入的完整账本。
- 合并日报以原日报 SHA-256 读取账本根下 `.report-sources/` 的冻结原件，账本和缓存齐全时可重新生成
  相同视图。来自旧账本的首次合成需要通过 `--directory` 指定对应日期的原归档，之后可以省略该参数。
  `--standalone` 可复现旧版 `paper-report.html` 和 `paper-email.txt`，适用于旧产物核对。
  若需用其他证据修正已接受的一日，须在另一离线研究目录从明确的起点复算并保留原链。
- Yahoo 仅使用经现有适配器认可的同一价格基准日线。检查此前冻结的 OHLC 是否与当前快照中的该日 OHLC 一致，
  Yahoo 拒绝、价格重述、拆股窗口、零成交量及移出当前 IWB 范围等无法验证情形会停止该样本的转换或估值。
  缺证的 T+1 不向后顺延。开放持仓一旦有未解决的缺日，后续保留最后可信状态，避免跳过可能已经发生的退出。
- GitHub Actions 核验私有归档 ZIP digest 与内容 SHA。独立模拟伴随归档保留 90 天，包含首日至目标日的完整账本。
  恢复依赖未过期的归档及可用的中间规范日报。长期停跑可能超出保留窗口，长期私有备份另行批准。
  见 [归档与恢复](IWB_AUTOMATION.md#归档和跨设备恢复)。

## 验收与用法

从 [11-18 运行](https://github.com/EFSing/us_watchlist/actions/runs/44476972797) 和
[11-19 运行](https://github.com/EFSing/us_watchlist/actions/runs/44698935120) 分别取得规范日报 ZIP，
校验 GitHub ZIP digest 后解包到下列目录。研究代码只读验证原日报及冻结输入。

```powershell
$first = '.runtime/data/iwb-validation/2026-11-18-hosted-44476972797/daily'
$second = '.runtime/data/iwb-validation/2026-11-19-hosted-44698935120/daily'
$ledger = '.runtime/artifacts/iwb-paper-acceptance'
us-watchlist iwb-paper --ledger-root $ledger --start-date 2026-11-18 --trade-date 2026-11-18 --directory $first --initialize
us-watchlist iwb-paper --ledger-root $ledger --start-date 2026-11-18 --trade-date 2026-11-19 --directory $second
us-watchlist iwb-paper --ledger-root $ledger --start-date 2026-11-18 --trade-date 2026-11-19
```

| 交易日 | 冻结输入 | 历史复算 |
| --- | --- | --- |
| 2026-11-18 | B 31（数值通过 5、未通过 25、缺证 1），C 均衡 3，C 保守 0 | 33 条待开盘检查。DD 缺参考价位，无法确认。 |
| 2026-11-19 | B 4（CDW、DLTR、SIRI、VIK，数值通过 0），C 均衡与保守均为 0。Yahoo 目标行情 1018／1020，FDX、SNDK 缺失。 | 11-18 的 33 条计划中，19 条开盘低于触发，14 条价格通过基本检查但模拟政策待定。新建 4 条待检查。持仓 0，已退出 0。 |

两份原 `report.html` 的 SHA-256 依次为
`dd6d84e40681031644602ab26ed8a96dc0768a4b674ede88a5d4cdbd5666163f` 和
`bafd73d226445c82b79e59d18aa283451d3e6853b6f177ae1b24ad9f3ae258c7`。
无政策的 11-19 账本摘要为 `1c6f80ee151833571a1c4cbfb0d19749b26064a1120a1fc0585e55560e7f3538`，
从仅含已发布账本及前序日文件的恢复路径重建出相同摘要。
11-18 的旧收据对 C 没有风险警示布尔字段，复算保留未知。归档观察时间用作历史模型的计划时间，复算输出
标记 `HISTORICAL_REPLAY`。这两份日报的模拟仓位均为事后计算。

合成用例在 `tests/test_iwb_paper.py`。`demo_days()` 与 `run_day()` 可复现零、一、两笔开放样本，
并覆盖入场日止损、之后估值、跳空退出、状态冲突与跨日重建。Edge 在 1440、390 和 320 像素宽度验收，
检查对应持仓卡片数及页面横向溢出。合成政策仅用于测试。

`--policy` 接收以策略版本为键的 JSON，例如合成 B 测试使用以下条目。C 策略分别使用
`C_PRICE_RESEARCH:CLEAR` 或 `C_PRICE_RESEARCH:WARNING`。

```json
{
  "us_breakout_retest_shape_v1": {
    "B_NUMERIC_QUALIFIED:UNKNOWN": {
      "min_actual_rr": "2",
      "min_target_upside": "0.05",
      "max_open_premium": "0.08",
      "exit_model": "FIXED_STOP"
    }
  }
}
```

### 四日单账户冻结复算

用 2026-11-18、19、20、23 的原始持仓和 Yahoo 归档，在隔离目录用 PR #19 的 B V2 重新评估，生成
`.runtime/artifacts/iwb-paper/us-b-v2-account-preview/`。四天 24 个规范日报原件的 SHA-256 在验证前后一致。
下表的委托数包含所有待检查参考计划，括号内是获默认政策启用的资格数，仍须核验 T+1 价位和账户额度。

| 交易日 | 新委托（启用资格） | 开盘成交价（USD） | 退出与止损调整 | 收盘持仓与浮动 R |
| --- | ---: | --- | --- | --- |
| 11-18 | 51（34） | 无 | 无 | 无 |
| 11-19 | 8（7） | BF-B 30.54、AHR 58.28、JAN 32.65 | BF-B 盘中以 29.77 止损，-1.00R | AHR -0.30R、JAN -0.64R |
| 11-20 | 19（14） | EG 426.32、PNR 69.48 | 无 | AHR -0.33R、JAN -0.65R、EG -0.21R、PNR -0.30R |
| 11-23 | 45（32） | CHE 548.96、OGE 51.24 | 无 | AHR +0.12R、JAN -0.20R、EG -0.15R、PNR +0.16R、CHE +0.96R、OGE +0.09R |

四天均无上调止损或预约退出。Chromium 在 1440、390 和 320 像素宽度核对持仓卡数、页面导航和展开后的横向溢出，
截图随各日期预览保存。回放期间的持仓和收益为毛值，长期留档、成本、其他资格组与 IBKR 模拟另行审阅。

## B/C 统一持仓协议 V2

`iwb-paper --protocol us_iwb_paper_position_v2` 显式选择新版离线协议。省略参数继续使用
`us_iwb_paper_open_v1`，包括既有 `FIXED_STOP` 和 `LEGACY_R_PROTECTION` 对照。V2 用同一组
入场门槛和分组键。每个启用组将 `exit_model` 换成下方结构，三个入场门槛仍须显式填值或 `null`。
下面的周期和倍数只供合成验收与参考对照。没有配置时仍只记录开盘检查。

```json
{
  "reject_open_at_or_below_structure": false,
  "structure_exit": true,
  "pivot": {"radius": 2, "min_separation": 3, "require_rebound": true},
  "atr_trail": {"period": 14, "multiple": "0.5"},
  "profit_protection": {"trigger_r": "2", "giveback_r": "1"}
}
```

- B 冻结已有回踩 L2 作为结构失效线，并保留 L0、H1 和原参考计划。C 均衡和历史归档中的 C 保守分别冻结
  原筛选的第一低点作为失效线，保留第二低点、前高和反弹高点。初始硬止损沿用各自参考计划，
  实际开盘成交价减初始硬止损为终生固定 1R。启用结构规则的组缺有效原始锚点时记为缺证。
- 结构退出可独立启用。`pivot: null` 时结构退出使用冻结的初始结构线，ATR 移动止损要求
  配置 pivot。关闭结构开盘检查、结构退出且将三个子模型均设为 `null`，即 V2 固定止损组。
  组别逐一配置，资格未知的 C 记录仍保留未知。
- 成交日之后的低点从左右各 `radius` 个已结束会话确认。低点须严格低于左窗且低于或等于右窗，
  以首次等价低点为准。同一根日线兼为高低 pivot 时跳过。若要求反弹，等待之后的局部高点也完成
  右窗，期间更低的暂定 pivot 可替换原候选。两次入选低点须相隔至少 `min_separation` 个会话，
  新低点必须严格高于当前结构底线。确认日期和低点日期均留证。
- ATR 使用信号日以前及当天的连续同基准种子，最多取周期加一根，再按实际持仓会话递推 Wilder ATR。
  种子不足时从连续样本预热。一律用决策日收盘的 ATR。结构候选为确认低点减 ATR 倍数，
  须高于当天生效线且低于收盘。利润保护达到配置的浮盈门槛后，以累计最高价减配置的 1R 倍数。
  两条候选与当日生效止损取最大值，下一会话生效。
- 先执行预约退出，再查开盘跳空和盘中硬止损。存续至收盘时，结构破坏优先于利润线破位。
  同时破位保留双原因，预约精确下一会话开盘，当日不再抬止损。目标仍是一档观察值。
  退出日沿用前一日的命中状态，MFE 和 MAE 只计入确定在退出前可见的开盘或执行价格。
  报告中的逐笔最大峰值回吐为历日 MFE 与收盘或退出 R 的最大差。
- 历史复算使用不可变 Yahoo 收据的观测时间，校验实际 XNYS 开收盘及价格基准。它提供离线研究
  截止时间，缺少独立的前瞻发布证据。需要盘后决策的仓位若在下一会话开盘时仍缺当日证据则停更。
  拆股、前日 OHLC 重述及缺精确会话行情沿用保守停更，预约退出保留原定日期和原因。
- V2 以协议和政策参与研究身份哈希。从首日冻结原件新建会话链。旧链和旧伴随视图按 V1 恢复。
  合并日报适用于 V1 和 V2 的离线视图。启用前瞻伴随归档时，邮件可附经过校验的合并日报。

2026-11-18 和 2026-11-19 的冻结归档已按两个协议离线复算。V1 复现既有账本摘要和两份伴随视图的
原字节。V2 无政策的 11-19 摘要为
`8c129d108f8b1f964335043b2d02684da16cd4af48a9393442f22afb644fd85a`，
可从已发布链逐字节重建两份伴随视图。真实归档仅用于证据和恢复验证，有成交的规则验收使用合成数据。
