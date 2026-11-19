# B 常规时段离线验证

`us-watchlist b-offline` 默认执行合成样本。样本包含 1 个形态匹配、1 个无合格突破、
1 个历史缺口、1 个首次突破回踩失败，以及活跃但未进入上游 Candidate 的证券。

## 共用股票池

输入来自数据中台 US 日报原 ZIP。适配器核对 GitHub Actions API 的 ZIP SHA-256、
归档上传时间、日报交易日、完整 IWB 审计行数和来源，交叉检查
`candidate_included_symbols`、`candidate_included_count` 和逐行 `included`。
Candidate 用日报日期判定生效，以归档上传时间判定最早可见。
IWB 持仓日期仅用于来源与滞后校验。上游 `PARTIAL` 状态随报告保留。
归档受上游保留期约束。
[上游 Candidate 导出契约](https://github.com/EFSing/stock-data-pipeline/blob/eded221958d92b581df98af36e50c746c70b8354/trading/production_candidate_runtime.py#L306)

## Yahoo 在线采集与本地离线观察

安装可选日历依赖后，先采集一次，再用同一清单离线出报告。清单和实际输入放在
`.runtime/data/`。`[iwb]` 填写原 ZIP 路径、远端运行产物 URL、API 的
`created_at` 和 `digest` 中的 SHA-256。相对路径以清单所在目录为基准。

```toml
market = "US"
mode = "yahoo_observation"
session = "regular"
target_date = 2026-11-17
max_seed_age_days = 7

[iwb]
file = "pipeline/report.zip"
artifact = "https://github.com/EFSing/stock-data-pipeline/actions/runs/44228564297/artifacts/14393429856"
uploaded_at = 2026-11-18T03:15:11Z
sha256 = "61b3a9687d80f2dfa526b31d1cb75a1196fd29a628e3c646edf75c58f1ac9f19"

[history]
bundle = "yahoo-20261117.zip"
# 采集后将命令输出的 SHA-256 填入 bundle_sha256。
```

```powershell
python -m pip install --no-cache-dir ".[yahoo]"
us-watchlist capture-yahoo --config .runtime/data/replay.toml
us-watchlist b-offline --config .runtime/data/replay.toml
```

- 采集复用上游采用的 Yahoo Chart v8 日线接口与双 host 读取方式。冻结原始响应、请求 URL、
  逐票捕获时刻及 SHA-256。默认冻结 120 个 XNYS 常规会话，支持 `--sessions 76..252`。
  离线时核对 ZIP、逐票响应、股票池、交易日、常规开盘时间戳和截止时刻。
  [上游 Yahoo Chart 实现](https://github.com/EFSing/stock-data-pipeline/blob/eded221958d92b581df98af36e50c746c70b8354/providers.py#L1072)
- 观察使用 Yahoo 的 `quote` OHLCV，排除 `adjclose`。查询拆股事件直到采集日。
  涉及拆股的证券仅保留最近已报告拆股日之后的行情，目标日之后的 OHLCV 不进入计算。
  逐票保留提供商故障、无行情及缺失会话。Yahoo 成交量的历史拆股调整与数据修订时间仍待核实。
  [Yahoo 调整收盘定义](https://help.yahoo.com/kb/SLN28256.html)
- 报告注明 `Historical point-in-time status: UNVERIFIED`。观察截止为整批采集完成时刻。
  同日归档晚于收盘时，报告列出实际上传时间。采集只验证供应商在采集时返回的日线及策略行为。

如已有独立点时数据，可继续使用 `mode = "offline_replay"` 和显式 `cutoff`。清单
示例见 [合成配置](../configs/b_demo/replay.toml)。该模式要求报告交易日早于或等于目标日，
截止在目标 UTC 日，归档及所有完整会话在此时已可用。导出方应提供连续 XNYS 日历及来源、
日历 CSV 和 OHLCV CSV 的 SHA-256、以当时可见拆股为基础的价格与成交量及
`adjustments_known_at`。报告标注外部点时声明待复核。

## B 形态与完整 B v1.1 的差距

`us_breakout_retest_shape_v1` 使用最近 76 个常规会话。首次合格突破要求收盘越过此前
60 会话最高收盘、成交量达到此前 20 会话均量的 1.8 倍，且较前收上涨至少 3%。
回踩时目标收盘处于平台的 97%–104%，突破后均量低于突破量的 70%，且收盘达到前收或
5 会话均线。首次突破的回踩失败保留为诊断。

完整 A 股 B v1.1 至少需要 120 根个股日线及指数、行业证据。其资格还受收盘价、加速过热、
涨幅耗尽、有效支撑等约束。A 股规则以支撑下方 2% 为止损参考，风险距离需大于 0 且不超过 9%，
目标以符合距离的前高或量价压力为先，缺足够压力位时采用 2.5 倍风险距离，再核对 RR 和上方套牢量。
这些市场相关规则和成交成本的美股定义尚未确定。本轮 B 形态匹配只作为离线研究记录。
[A 股 B v1.1 规则契约](https://github.com/EFSing/ashare_watchlist/blob/85abb04acb86e3396f635218e7087c00a0d8339a/scripts/b_breakout_retest_v1_1.py#L72)

## 2026-11-17 实际观察

归档含 1,021 条 IWB 审计记录、1,020 条活跃证券和 1,000 只实际 Candidate，状态为
`PARTIAL`。目标收盘为 2026-11-17 21:00 UTC，归档于次日 03:15:11 UTC 上传。
Yahoo 采集于次日 12:06:08 UTC 完成。120 会话覆盖 2026-05-29 至 2026-11-17。
1,000 只均取得响应及目标日行情，与上游记录逐票比较收盘，绝对差异均不超过 0.0001 美元。
Yahoo ZIP SHA-256 为 `a0e911f518c7c8cc3b868087abd091581c875bb7a168971007611f3ee86a970c`。
[验证用归档](https://github.com/EFSing/stock-data-pipeline/actions/runs/44228564297/artifacts/14393429856)

B 在 1,000 只中有 993 只具备完整 76 会话，11 只匹配，877 只无合格突破，
105 只首次突破后回踩失败。15 只出现拆股事件，7 只在最近一次拆股后未满 76 会话。
此次运行使用已收盘实际行情，目标收盘点时有效性标为未验证。
