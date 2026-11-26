# IWB 基础池与 B+C 日报

[iShares Russell 1000 ETF](https://www.ishares.com/us/products/239707/ishares-russell-1000-etf) 的官方持仓是正式基础池的成份来源。基金是指数代理，权益证券数随多股类与持仓变化而变化。股票池保留全部权益行，现金、期货等单列。无上市市场和待发行的权益留在基池，单列资格原因。官方股类分隔符统一映射到 Yahoo 的连字符。遇到重复符号、未知交易所、币种异常、过期、日期不符或同日原件冲突时拒绝更新。已验证的版本保留。

`iwb-refresh` 原样冻结 CSV，将官方持仓日期、来源、采集 UTC 和原件 SHA-256 一起保存至 `.runtime/data/iwb/IWB_<date>.zip`。重复取得同一原件沿用首次采集证据。若已存在前一版本，刷新摘要列出新增、移除和上市状态变化。历史 `--holdings-date` 必须与官方响应日期完全一致。

`iwb-report` 选交易日当日或之前的最新本地版本，持仓日期上限为 10 个自然日。每轮冻结版本文件，采集 120 个 XNYS 常规会话的 Yahoo Chart 日线，逐票核验 SHA、市场、会话、价格基准与拆股边界。B 突破回踩与 C 均衡独立计算，完整历史资格分别为 76、60 个会话。日报区分基池、可取行情证券、目标日可用 OHLCV 和分策略匹配状态。目标日 OHLCV 覆盖低于 95%，或任一活跃规则完全缺少合格历史或执行失败时，命令返回失败并保留可生成的诊断。个别证券的历史缺口允许保留部分结果。这些阈值用于审阅版数据运行判断。

```powershell
us-watchlist iwb-refresh
us-watchlist iwb-report --trade-date 2026-11-18 --output .runtime/data/iwb-daily/2026-11-18 --code-sha (git rev-parse HEAD)
```

示例日期应与本机可用版本匹配。输出目录保存 `holdings.zip`、`yahoo.zip`、`plan.json`、`inputs.json`、`run.json` 和单文件 `report.html`。原输入和代码身份相同的本地复跑复用原件及报告。需要重新采集时使用新目录。以现时采集的历史行情做补跑时仍标为事后观察。B 为 76 日突破回踩形态诊断，完整 B v1.1 和 B/C 收益研究另需证据。Yahoo 股价历史修订时间、拆股量能与历史点时均未验证。

## 实际验证

2026-11-16 和 2026-11-17 的官方版本各含 1,021 只权益证券、6 条非权益记录。两版本成份和上市状态一致。HOLX 保留在基池，标记无上市市场。11-18 交易日报使用 11-17 持仓版本，在 11-19 02:48 UTC 取得官方文件，02:52 UTC 完成采集。Yahoo 返回全部 1,020 份上市证券响应，1,020 只通过目标日 OHLCV 校验。15 只遇到拆股事件，保留最后一次拆股日之后的会话。整轮状态为 `PARTIAL_COVERAGE`。

| 独立规则 | 通过完整历史要求 | 匹配 | 历史不足 |
| --- | ---: | ---: | ---: |
| B 76 日突破回踩形态 | 1,011 | 31 | 9 |
| C BALANCED_A | 1,013 | 3 | 7 |
| C CONSERVATIVE_B | 1,010 | 0 | 10 |

| 证据 | SHA / Git 提交 |
| --- | --- |
| 11-16 官方 CSV | `aa02b4d4c5f1927f9a7dbd92f393b285b1f8356ff9b431c49b197fbca499f054` |
| 11-17 官方 CSV | `307b54a21892ccfa22d108e0eb03dae9e4c59d920f03a9877c6875ac64fe2085` |
| 11-18 Yahoo ZIP | `6f63240bdd6448b53b4261bdb6f1e51483fe41ab090c8024fa0a022d44535f4a` |
| 11-18 输入清单 | `0bf070736ea3e03097f9b47c5891314444378be8934611124e2106d475500687` |
| 11-18 HTML | `7724c8bf377d18af5e7fa0e6e83ced06b0e5782bea760636de0ada27aba8067c` |
| 实际渲染代码 | `b12201b6970ab239c539ea0790eaf21ea6b376c9` |

实际证据在本机 `.runtime/data/iwb-validation/2026-11-18/`，报告从同一冻结输入重跑两次得到相同身份及 SHA。

## 中文日报复渲染

从 11-18 的冻结 `holdings.zip`、`yahoo.zip`、`plan.json` 和 `inputs.json` 在独立目录离线复渲染。
保留清单中的原代码标识以便逐字节核对输入，中文渲染代码见 [#4](https://github.com/EFSing/us_watchlist/pull/4)。
基线重跑复现上表旧 HTML SHA。新版重复渲染字节一致，SHA-256 为
`cc8d1b5dd108a21398b3daef405433fefb6e7edf3ec474ee46202dba12fc83d0`。
两版逐字段核对了 3,060 条机器记录及输入清单。B 匹配 31 只，C 均衡规则匹配 CHH、GME、H，
C 保守规则为零。运行收据的基池、覆盖、逐股数据诊断及策略统计一致。

中文版本位于本机 `.runtime/data/iwb-validation/2026-11-18-zh/report.html`。Chrome 离线验证了
1440 × 1000 桌面与 390 × 844 手机视口的导航、未匹配搜索、默认折叠和原始 JSON 下载。
截图位于 `.runtime/artifacts/bc-offline/iwb-review-2026-11-18/`。
