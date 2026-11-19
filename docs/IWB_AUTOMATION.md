# 独立 IWB 收盘日报审阅运行

[日报工作流](../.github/workflows/iwb-daily.yml) 提供默认分支上的 `workflow_dispatch`。预留的计划为纽约时间交易周工作日 17:37，启用须单独审阅得准并显式开启变量。计划任务按 XNYS 判定节假日和短市，在实际收盘至少 30 分钟后运行。任务串行发布。数据中台 `eded221958d92b581df98af36e50c746c70b8354` 的 US 日报提供调度、串行、有限重试和留痕参考。本项目的输入来自 iShares、Yahoo 和本仓库产物。[数据中台参考工作流](https://github.com/EFSing/stock-data-pipeline/blob/eded221958d92b581df98af36e50c746c70b8354/.github/workflows/us-daily-report.yml)

## 手动补跑和失败诊断

1. 合并获准后，在本项目 **Actions → US IWB B+C Daily → Run workflow** 选择默认分支。空 `trade_date` 使用最近完成的 XNYS 会话，也可指定 `YYYY-MM-DD`。先验证交易日与收盘。
2. 当前会话从已归档的本地还原版本出发。缺版本或持仓日期距目标至少五个自然日时查询 iShares 最新持仓。刷新收据记录成份差异和源错误。失败中止本轮并保留既有版本，超过十个自然日的版本不能运行。当历史版本缺失时可手填官方 `holdings_date`，官方回应须与该日期吻合。补跑仍是 Yahoo 和 IWB 的事后观察。
3. 当 Yahoo 目标 OHLCV 覆盖低于 95%，或任一规则没有证券满足完整历史要求，保留首次证据，75 秒后仅重采一次。逐票请求最多试两个 Yahoo 主机，整批限流短路。每次采集在 10 分钟后停止派发新批次。数据源及归档 API 的临时网络错误最多尝试两次。资格冲突、输入损坏和策略故障直接失败。诊断分别保存缺行情原因、逐轮状态、输入 SHA 和旧版本来源。
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

幂等复用与跨设备下载覆盖产物可访问期。过期后可从同一用户保留的副本核验，作长期存储须另行批准。GitHub hosted runner 的 Yahoo 可达性与限流需要在启用前单次验证，Windows 真实观察与 CI 的合成归档传输分别提供现阶段证据。正式定时与通知保持关闭。[GitHub 产物保留说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)
