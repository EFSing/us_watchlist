# B 常规时段离线验证

`us-watchlist b-offline` 使用 `configs/b_demo/replay.toml`。合成样本覆盖匹配、未发生突破、
整窗中缺一个交易日、首次突破后回踩失败，以及非活跃 IWB 证券。样本时间窗口同样是合成数据。
报告输出在 `.runtime/artifacts/b-offline/synthetic/`。

## IWB 来源和时点

数据中台现有 US 日报 ZIP 内的 `daily-report.json` 带有
`candidate_markets.US.candidate_records`。仅在审计行数等于原始 `seed_count`，且每行是唯一
US 证券、同一持仓日期、官方 IWB 持仓来源及已知上市状态时使用。项目按 `ACTIVE` 决定本轮
初始资格。数据中台的候选入选标志、排名和历史覆盖只属于它自己的筛选。

真实归档核验样本的 IWB 名单日期为 2026-11-16，1,021 条，活跃 1,020 条。日报对应交易日
2026-11-17，归档在 2026-11-18 03:15:11 UTC（北京时间 11:15:11）上传。用下载所得原 ZIP
比对 GitHub 的 SHA-256，验证上传前拒绝、上传后才可消费。归档受上游保留期约束。
[数据中台审计代码](https://github.com/EFSing/stock-data-pipeline/blob/eded221958d92b581df98af36e50c746c70b8354/trading/production_candidate_runtime.py#L302) · [验证用归档](https://github.com/EFSing/stock-data-pipeline/actions/runs/44228564297/artifacts/14393429856)

## 离线输入约定

从 `configs/b_demo/replay.toml` 复制清单结构，在 `.runtime/data/` 准备实际输入。
使用 `us-watchlist b-offline --config .runtime/data/replay.toml`。相对文件路径以清单为准。

| 字段或文件 | 约定 |
| --- | --- |
| 顶层 | `market = "US"`、`mode = "offline_replay"`、`session = "regular"`、目标交易日、UTC cutoff，及显式 `max_seed_age_days`（自然日） |
| `iwb` | 上游原 ZIP 路径、GitHub 运行产物 URL、Actions API 的 `created_at`（填 `uploaded_at`）和 `digest` 的 SHA-256（去掉前缀） |
| `history.calendar` | 由可信交易日历提供最后 76 个连续预期常规会话，最后一行为目标日；CSV 列为 `date,opens_at,closes_at,ohlcv_available_at` |
| `history.ohlcv` | 长表 CSV 列为 `date,symbol,open,high,low,close,volume`，每只股票、每会话一条，符号使用上游审计的规范形式 |
| `history` 元数据 | 数据源、两份 CSV 的 SHA-256、`price_basis = "split_adjusted"` 及 UTC `adjustments_known_at` |

清单提供日历和输入可用证据。导出方须保证会话连续、时间戳代表整批数据的实际可用时间，
且 OHLC 与成交量采用截至 cutoff 已知的同套拆股调整，现金股息调整排除在此口径之外。
CLI 校验时点、哈希、日期、重复、顺序和价格基准。真实文件的日历完整性及调整出处仍由
导出方提供证据。截止时间须在目标收盘后且在同一 UTC 日期。归档或行情晚于 cutoff、
市场或时段不符及来源哈希冲突时，整轮报错。有单只股票缺少窗内行情时，该证券显示
`INCOMPLETE_HISTORY`。

## B 形态与结果

`us_breakout_retest_shape_v1` 使用最后 76 个常规会话，从靠近目标日的扫描窗中取首次
合格突破。突破要求收盘越过此前 60 个会话的最高收盘价，成交量达到前 20 个会话均量的
1.8 倍，且较前收至少上涨 3%。目标收盘需在平台价的 97%–104%，突破后均量低于突破量的
70%，且目标收盘达到前收或 5 会话均线。首次突破的回踩失败直接进入诊断。
[A 股 B 形态参考](https://github.com/EFSing/ashare_watchlist/blob/0a6e9060997df4d79f5d7d8e3bb01ac822b8296d/scripts/b_breakout_retest.py#L192)

交付内容是形态诊断。完整正式候选还涉及策略资格、风险距离、目标位、成交及成本口径。
输出由模式、日期、策略版本和已校验清单指纹确定。相同输入的重试复用 HTML。
