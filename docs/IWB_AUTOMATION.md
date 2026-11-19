# 独立 IWB 收盘日报审阅运行

[日报工作流](../.github/workflows/iwb-daily.yml) 提供默认分支上的 `workflow_dispatch`。预留的计划为纽约时间交易周工作日 17:37，启用须单独审阅得准并显式开启变量。计划任务按 XNYS 判定节假日和短市，在实际收盘至少 30 分钟后运行。任务串行发布。数据中台 `eded221958d92b581df98af36e50c746c70b8354` 的 US 日报提供调度、串行、有限重试和留痕参考。本项目的输入来自 iShares、Yahoo 和本仓库产物。[数据中台参考工作流](https://github.com/EFSing/stock-data-pipeline/blob/eded221958d92b581df98af36e50c746c70b8354/.github/workflows/us-daily-report.yml)

## 手动补跑和失败诊断

1. 获准手动运行后，在本项目 **Actions → US IWB B+C Daily → Run workflow** 选择默认分支。空 `trade_date` 使用最近完成的 XNYS 会话，也可指定 `YYYY-MM-DD`。先验证交易日与收盘。
2. 当前会话从已归档的本地还原版本出发。缺版本或持仓日期距目标至少五个自然日时查询 iShares 最新持仓。刷新收据记录成份差异和源错误。失败中止本轮并保留既有版本，超过十个自然日的版本不能运行。当历史版本缺失时可手填官方 `holdings_date`，官方回应须与该日期吻合。补跑仍是 Yahoo 和 IWB 的事后观察。
3. 当 Yahoo 目标 OHLCV 覆盖低于 95%，或任一规则没有证券满足完整历史要求，保留首次证据，75 秒后仅重采一次。逐票请求最多试两个 Yahoo 主机，整批限流短路。每次采集在 10 分钟后停止派发新批次。iShares 和归档目录的临时网络错误最多尝试两次，归档下载最多三次。资格冲突、输入损坏和策略故障直接失败。诊断分别保存缺行情原因、逐轮状态、输入 SHA 和旧版本来源。
4. 成功及达到目标日覆盖要求的 `PARTIAL_COVERAGE` 使用同一报告身份。已存在规范报告时先恢复并核验文件 SHA，再复用该身份。失败只进入诊断。不同内容与同一已存在版本冲突会显式失败。GitHub 一条并发组可替换等待中的派发，多个手动补跑应逐次提交。

## 归档和跨设备恢复

使用本项目私有 GitHub Actions 的现有产物能力，通过源码和运行凭证关联证据。上传保留期如下，受仓库设置和平台配额约束。

| 产物名称 | 保留期 | 内容 |
| --- | ---: | --- |
| `us-iwb-v1-pool-YYYY-MM-DD` | 90 天 | 不可变官方 CSV、成份日期、来源、获取 UTC 与 SHA |
| `us-iwb-v1-daily-YYYY-MM-DD` | 30 天 | 股票池、Yahoo ZIP、输入清单、运行收据、单文件 HTML |
| `us-iwb-attempt-<run_id>-<run_attempt>` | 7 天 | 流程状态、成功报告引用、失败轮次的可用输入和诊断 |

新设备可从 **Actions** 对应运行下载产物。将 IWB 版本解包至 `.runtime/data/iwb/`，将日报解包至 `.runtime/data/iwb-daily/<date>/`，校验后打开 `report.html`。

```powershell
us-watchlist iwb-verify --trade-date 2026-11-18 --directory .runtime/data/iwb-daily/2026-11-18
```

幂等复用与跨设备下载覆盖产物可访问期。过期后可从同一用户保留的副本核验，作长期存储须另行批准。
正式定时与通知保持关闭。[GitHub 产物保留说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)

## 2026-11-18 hosted runner 验收

2026-11-19 从 `main` 手动派发一次，运行提交
`60c04f24986cf90ad65fd7a52322041aa980edc7`。runner 为 `ubuntu-latest`（实际镜像 `ubuntu-26.04`），
令牌权限为 `actions: read` 和 `contents: read`。日志确认 `trade_date=2026-11-18`、
`holdings_date` 为空，XNYS 常规会话在 2026-11-18 21:00 UTC 收盘。Actions 结论为 `success`。
[运行 #44476972797](https://github.com/EFSing/us_watchlist/actions/runs/44476972797) ·
[作业日志](https://github.com/EFSing/us_watchlist/actions/runs/44476972797/job/135399775316)

- iShares 官方最新持仓端点返回 2026-11-17 版，权益 1,021 只，其中 1,020 只有有效上市市场。
  HOLX 因无有效市场排除，另排除 6 条非权益行。云端获取时刻为 2026-11-19 07:06:04 UTC。
- 120 个 XNYS 会话请求中，1,020 只均由 `query1.finance.yahoo.com` 首次成功返回，目标日 OHLCV
  为 1,020／1,020（100%，发布线 95%）。无 429、备用主机调用或第二轮重采。限流、重试和失败
  保留分支的验证来自 CI 合成测试。该次真实运行发布了成功的工作流诊断收据。
- B、C 均衡和 C 保守各评估 1,020 只，分别匹配 31、3、0，历史不足 10、8、11，无策略错误。
  历史缺口、拆股保护和无有效市场记录使日报状态为 `PARTIAL_COVERAGE`。
  规范身份为 `US_2026-11-18_regular_IWB_BC_v1`。固定版本的三个 Actions 出现 Node.js 20
  退役提示，runner 使用 Node.js 24 并完成运行。

### 私有归档恢复与 SHA-256

三个 ZIP 已通过私有 Actions 下载端点恢复，按服务端 digest 核验 ZIP 字节和预期文件名。
日报通过 `iwb-verify`，独立成份归档内的 IWB ZIP 与日报内附 ZIP 逐字节一致，
Yahoo 归档内的逐股原始响应全部通过清单 SHA 验证。HTML 的交易日、输入身份和三个独立策略记录
与运行收据一致。恢复位置为 `.runtime/data/iwb-validation/2026-11-18-hosted-44476972797/`。

| Actions 归档 | ZIP SHA-256 |
| --- | --- |
| [规范日报](https://github.com/EFSing/us_watchlist/actions/runs/44476972797/artifacts/14505819685) | `8f326a08187255a34645e750ada2dd4b5687a7ef8b9126ce57ac52b73afbc866` |
| [官方成份](https://github.com/EFSing/us_watchlist/actions/runs/44476972797/artifacts/14505849682) | `6226f3c3aed180fb2b4705e5e8c31de81f42ed2f527d0ba77ca563332bec4e39` |
| [运行诊断](https://github.com/EFSing/us_watchlist/actions/runs/44476972797/artifacts/14506701982) | `b8b8aa707e1a3074cdde9dc8701763da59e454b80f2eb5083ef17b4428494cc5` |

| 冻结文件 | SHA-256 |
| --- | --- |
| iShares 官方 CSV | `307b54a21892ccfa22d108e0eb03dae9e4c59d920f03a9877c6875ac64fe2085` |
| `holdings.zip` | `5ddade2d3d2afefca7f693a2fcec7622191f2fc3186a13140fc9b403a617739d` |
| `yahoo.zip` | `b4dd705d2b9b807f7bf60d54b8b47256a82f1db07524f4c9ac407a65e4cb1210` |
| `plan.json` | `aa3d54a3a7f446fb7093db572eaaf51ac610b1616e4948a1512ad1de7817d011` |
| `inputs.json` | `facfbb4d81c7ebaede37135e7f2984010f13f4a53d858a708714517d67192167` |
| `run.json` | `cb0236333cf8f15959b8a8a3427363e4f945afd61707e9c6afaff463b49bd8ea` |
| `report.html` | `dd6d84e40681031644602ab26ed8a96dc0768a4b674ede88a5d4cdbd5666163f` |
| `workflow.json` | `309d94fba2b435920474687367bc87ab5a30180a39fb48d7e0bf861bbb1b781d` |

### 本地冻结对照

- 本地最终验收版与云端的 iShares 成份日期、CSV SHA、成份及上市状态一致。持仓 ZIP 的获取
  收据时刻不同。两版使用同一 XNYS 日历和 120 个会话，本地冻结清单保留原 `code_sha`
  `b12201b6970ab239c539ea0790eaf21ea6b376c9`。本地 Yahoo ZIP 与输入清单 SHA 分别为
  `6f63240bdd6448b53b4261bdb6f1e51483fe41ab090c8024fa0a022d44535f4a` 和
  `0bf070736ea3e03097f9b47c5891314444378be8934611124e2106d475500687`。
- 两份原始 Yahoo 响应的规范化 OHLCV 差异集中于 SNDK。云端原件只含 11-17、11-18 两根，
  本地原件含 120 根。共有两根的成交量不同，11-18 的最高价也有小幅差异。SNDK 在三套规则中
  从未匹配变为历史不足，云端各多一条历史不足。其他 1,019 只的规范化 OHLCV 一致。
- 三套匹配集合一致，C 均衡为 CHH、GME、H。34 条研究记录的结构、三项量能和参考计划一致。
  B 有 22 只回踩早期、9 只 2→3，数值门槛通过 AAPL、AHR、JAN、OGE、UI，交集为 AHR、JAN、UI。
  有效参考计划为 B 30／31 和 C 3／3。详见 [本地冻结研究](BC_REFERENCE_RESEARCH.md#最终验收首页)。
- 在 Windows 以 `main` 的代码和已归档云端输入离线重算，输入清单逐字节一致。除 11 项 C 日对数
  斜率的末位浮点差异（最大绝对差约 `1.41e-18`），逐股筛选记录及研究记录一致。斜率尾差可在
  同输入的 Linux 和 Windows 间复现，未改变规则诊断。云端与本地采集均为事后观察。
