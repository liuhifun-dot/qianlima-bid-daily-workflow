# ISSUE-20260714-cdp-contention

| 字段 | 内容 |
|:---|:---|
| **记录时间** | 2026-07-14 |
| **状态** | resolved |
| **优先级** | P0 |
| **节点** | Phase0 / Phase1 / Phase2B |
| **脚本/模块** | `cdp_run_lock_20260714_v01.py`, `run_daily_pipeline_20260622_v04.py` |
| **标签** | `cdp` `lock` |

## 1. 问题

同机双开流水线或脏 9222 导致导出页 no_rows、互点、CDP 断开。专用号登录会踢其它会话，但**调试端口仍可能被本机另一路自动化占用**。

## 2. 解法

- 按 port 文件锁；等锁默认 600s（下限 300s）  
- stale PID 回收；不默认 kill 外机 Chrome  
- 单专用号不做多 port 真并行登录  

## 3. 验证

锁 acquire/stale/release 单测 PASS；完整双 pipeline 长等未做。
