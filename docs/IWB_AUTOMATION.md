# 独立 IWB 收盘研究日报

[日报工作流](../.github/workflows/iwb-daily.yml) 提供默认分支手动补跑和 GitHub Actions 原生定时。
`America/New_York` 周一至周五 17:37 对应夏令时 21:37 UTC、标准时 22:37 UTC。
仓库变量 `US_IWB_SCHEDULE_ENABLED=true` 放行定时作业，变量缺失或为 `false` 时跳过定时作业。
设置 `US_IWB_VPS_SCHEDULE_ENABLED=true` 时，定时入口切换为 VPS 的 `workflow_dispatch`。
各入口共用串行发布组，Actions 作业的令牌仅有 `actions: read` 和 `contents: read`。
[GitHub 调度语法](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## 邮件交付与 Bark 故障告警

新日报沿用既有 Gmail → QQ 的 SMTP 配置方式，但 `us_watchlist` 是独立仓库，旧仓库的 Secrets 不会自动继承。
请在本仓库 **Settings → Secrets and variables → Actions → Repository secrets** 单独设置：

| Secret | 含义 |
| --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME`、`SMTP_FROM` | Gmail 发信地址 |
| `SMTP_PASSWORD` | Gmail 应用专用密码，不使用账户登录密码 |
| `SMTP_TO` | 实际接收报告的 QQ 邮箱 |
| `SMTP_USE_TLS` | `true`（STARTTLS） |
| `BARK_ENDPOINT` | 既有 Bark 完整 POST 地址，包含所需设备鉴权 |

只有日报状态为 `SUCCESS`、`PARTIAL_COVERAGE` 或已验证归档的 `REUSED_PUBLISHED_REPORT` 时，且本轮所有归档步骤成功，
才发送中文摘要邮件并附上与 `report.html` 字节相同的完整 HTML 附件。`PARTIAL_COVERAGE` 在邮件主题与正文中明确显示「部分覆盖」。
同一交易日手动补跑若复用归档，仍会再发送一次邮件，便于补发；正式日报身份及行情不会重复生成。
定时作业复用归档时只校验已有产物。归档成功后若邮件失败，按手动补跑流程补发。
未配置 SMTP、邮件验证或发送失败均使本次运行失败，原已发布的私有日报归档仍保留。

失败告警由独立的后置 Actions 作业处理：只要日报作业结论为 `failure`，即向 `BARK_ENDPOINT` 发送一次
包含交易日、日报状态及运行链接的 Bark。采集、归档、SMTP 任一环节失败均适用。成功不发 Bark；
XNYS 休市及定时开关关闭导致的正常跳过不发邮件或 Bark。平台未创建工作流运行、整次运行被取消、
或 Bark 服务自身不可用时，GitHub Actions 无法保证手机端收到告警。

首次启用前需先在审阅 PR 的合成测试和 CI 中验证分流，再在密钥配置完成后手动运行一次，检查
`IWB_EMAIL_SENT`、QQ 邮箱收到正文及完整附件；用隔离故障样本验证 Bark 送达，不发送真实交易指令。

定时事件根据 GitHub API 的原始 `created_at` 锁定纽约目标日，无手动日期参数。XNYS 休市记为
`SKIPPED_XNYS_CLOSED`，开市日采用该会话的常规收盘时刻，短市同样等待至少 30 分钟。作业启动、
每轮采集启动及 Yahoo 采集完成均须在纽约目标日。跨日记为 `SKIPPED_SCHEDULE_EXPIRED`，保留已取得的诊断。
提前触发或未达收盘等待时间记为
`SKIPPED_NOT_READY`。GitHub 可能延迟创建或丢弃事件，`created_at` 是原始运行创建时间，验收时与预定时刻分别核对。

新定时采集逐股要求目标日有效 OHLCV、正确的常规会话和已冻结的响应时间。Yahoo `regularMarketTime` 须属于纽约目标日，
达到 XNYS 当日收盘且早于或等于收到响应的时点。未获确认的目标日线从筛选输入剔除，记入逐股诊断并计入覆盖缺口。
该字段是 Yahoo 的就绪依据，后续修订及历史点时仍待验证。手动历史补跑继续核对 XNYS、行情时段、可用时间及发布门槛。

## VPS 定时触发

VPS 使用 systemd 在纽约工作日 17:37 调用 GitHub API，向 `main` 发送明确的纽约会话日期
`vps_trade_date`。Actions 使用与原生定时相同的 XNYS、收盘等待、跨日和 Yahoo 就绪校验，诊断收据
以 `trigger=vps_schedule` 标明来源。VPS 只负责触发，采集、归档、邮件和作业失败 Bark 都由 Actions 执行。

部署使用审阅过的文件。将 [触发脚本](../src/us_watchlist/integrations/github_dispatch.py) 安装至
`/usr/local/lib/us-iwb-dispatch/github_dispatch.py`，将 [服务](../deploy/systemd/us-iwb-dispatch.service) 和
[定时器](../deploy/systemd/us-iwb-dispatch.timer) 安装至 `/etc/systemd/system/`。创建只含本仓库
`Actions: write` 权限的细粒度令牌，以 root 所有、权限 `0600` 写入
`/etc/us-iwb-dispatch/github-token`，并在到期前轮换。服务通过 systemd 的 `LoadCredential` 读取。
[GitHub 触发权限](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)

切换顺序如下。

1. 执行 `systemctl daemon-reload`，用 `systemd-analyze verify` 检查单元。保持定时器关闭，
   先用服务发起一次验证请求。留存日志中的运行链接，确认 VPS 开关关闭时作业跳过。
2. 将 `US_IWB_VPS_SCHEDULE_ENABLED` 设为 `true` 并回读，执行
   `systemctl enable --now us-iwb-dispatch.timer`，核对 `systemctl list-timers us-iwb-dispatch.timer`。
   此时原生 cron 的作业跳过，手动补跑继续可用。回滚时停用 timer，再将 VPS 开关设为 `false`，
   核对原生开关为 `true`。
3. 从 `journalctl -u us-iwb-dispatch.service` 取得运行链接，核对 Actions 作业、日报归档及邮件。
   平台拒绝请求或响应不明时先查当日运行列表。服务只提交一次，关机错过的会话按手动补跑流程处理。
   API 接受请求只确认已创建运行，后续仍依赖 GitHub runner。

## 首次定时验收

1. 核对默认分支 `main`、精确提交的 push CI 已成功、日报工作流为 active，回读仓库变量为 `true`。
   若有变量关闭期间的计划事件，核对日报作业跳过且无产物。
2. 等待下一个正常 XNYS 会话的 17:37 自然触发。记录运行 URL、`run_id`、`run_attempt`、`event=schedule`、
   默认分支、代码 SHA、纽约目标日、预定时刻、GitHub 原始创建时刻和 runner 实际开始时刻。保留该日给定时作业生成规范日报。
3. 从 `workflow.json`、`run.json` 及 `yahoo.zip` 的 `manifest.json` 核对 XNYS 实际收盘、至少 30 分钟等待期、
   同一纽约交易日的采集起止时刻、逐股响应时刻与 Yahoo `regularMarketTime`。记录 IWB 版本、来源及实际可用时刻。
   如有重试，核对前一轮失败原因、证据、重采时刻和最终状态。
4. 核对目标日有效 OHLCV 至少 95%，分别记录 120 日完整历史覆盖、B／C 均衡／C 保守的匹配数和历史不足数。
   从 HTML 审计与运行收据逐股核对 SNDK（如适用）和其他异常。接受符合发布条件的 `SUCCESS` 或
   `PARTIAL_COVERAGE`，保留缺口及各规则资格。参考计划、量能、2→3 结构和 C 止损距离以未验证的研究观察展示。
5. 下载规范日报、尝试诊断及本次新发布或引用的成份 ZIP，记录产物名称、ID、来源运行及保留期。
   用 Actions 提供的 digest 核对 ZIP SHA-256，用 `iwb-verify` 核对报告身份、输入、HTML、官方成份与 Yahoo ZIP 的 SHA-256。
   首次定时验收时核对本次实际启用的通知版本和结果，IBKR 调用及真实订单均不得发生。命中已有归档可验证恢复，
   首次前瞻验收须取得该日的新采集。

若没有 `schedule` 运行、作业失败或未发布，先核对变量、工作流版本、队列、XNYS 状态及诊断。记录未完成的定时验收，
获准后按下节指定该交易日补跑，并保留真实取得时刻。补跑属于事后观察，另选交易日完成自然触发验收。

## 手动补跑和失败诊断

1. 获准手动运行后，在本项目 **Actions → US IWB B+C Daily → Run workflow** 选择默认分支。空 `trade_date` 使用最近完成的 XNYS 会话。
   定时失败补跑明确填写原目标 `YYYY-MM-DD`，尤其是跨日后。先验证交易日与收盘。
2. 当前会话从已归档的本地还原版本出发。缺版本或持仓日期距目标至少五个自然日时查询 iShares 最新持仓。刷新收据记录成份差异和源错误。失败中止本轮并保留既有版本，超过十个自然日的版本不能运行。当历史版本缺失时可手填官方 `holdings_date`，官方回应须与该日期吻合。补跑仍是 Yahoo 和 IWB 的事后观察。
3. 当 Yahoo 目标 OHLCV 覆盖低于 95%，或任一规则没有证券满足完整历史要求，保留首次证据，75 秒后仅重采一次。逐票请求最多试两个 Yahoo 主机，整批限流短路。每次采集在 10 分钟后停止派发新批次。iShares 和归档目录的临时网络错误最多尝试两次，归档下载最多三次。资格冲突、输入损坏和策略故障直接失败。诊断分别保存缺行情原因、逐轮状态、输入 SHA 和旧版本来源。
4. 成功及达到目标日覆盖要求的 `PARTIAL_COVERAGE` 使用同一报告身份。已存在规范报告时先恢复并核验文件 SHA，再复用该身份。失败只进入诊断。不同内容与同一已存在版本冲突会显式失败。GitHub 一条并发组可替换等待中的作业，多个手动补跑应逐次提交。

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
每次恢复以 [仓库变量实际值](https://github.com/EFSing/us_watchlist/settings/variables/actions) 和
[日报工作流状态](https://github.com/EFSing/us_watchlist/actions/workflows/iwb-daily.yml) 为准。
[GitHub 产物保留说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)

## 长期前瞻研究证据

保持 90／30／7 天 Actions 保留期。由一名维护者每周在最早一份 7 天诊断到期前导出并校验私有归档，覆盖上次导出以来的
所有交易日及失败运行。导出的证据先存项目本地 `.runtime/data/iwb-validation/`。每月按纽约交易月汇总证据和
SHA-256 清单，在经批准的私有位置封存，并抽样下载核对哈希与可恢复性。月度清单记录缺日、失败和已保全的完整输入。
逐日文件用规范报告身份及输入／报告 SHA-256 去重，同内容复用，异内容报冲突。缺失或失败的交易日单独留收据和失败原因。

- 精简证据为压缩 JSON 和 SHA-256 清单。保留交易日、预定／启动／采集时间、事件类型、运行 URL、代码 SHA、
  股票池版本及成员符号、输入及报告 SHA、策略版本、逐股资格和缺口、匹配及其研究值。未来收益和执行观察用各自的时间、
  版本及来源追加记录，引用当日身份和哈希。
- 完整 Yahoo ZIP、官方持仓原件及 HTML 继续留在短期归档。优先保全首次定时验收、缺口／修订调查及经批准的复盘样本。
  11-18 hosted 日报的 Yahoo ZIP 约 4 MB，按约 250 个交易日估算每日保存约 1 GB／年，仅包含 Yahoo ZIP。
  精简记录可追踪当时筛选，完整复算需要保存相同输入原件。
- 长期位置优先使用现有私有 GitHub 仓库月度 Release 资产，需用户批准研究数据访问范围和发布方式。若现有设置启用了
  immutable releases，可在发布完该月资产后锁定。如暂未批准或不可用，使用经批准的现有私有备份，由清单和恢复校验验证字节一致性。
  Actions 保持只读权限。长期写入、付费存储及仓库权限变更另行授权。
  [GitHub Release 资产限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas) · [不可变 Release](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)

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
- 定时草稿对两份冻结输入应用新的目标日资格检查后，目标日覆盖仍均为 1,020／1,020，完整 120 日历史分别为
  云端 994／1,020、本地 995／1,020。逐套比对 1,020 条记录的匹配、原因和可用会话数，差异限于 SNDK。
  云端逐股证据明确记录 `YAHOO_REGULAR_HISTORY_GAP 2/120`。
