# ISSUE-20260714-soft-continue

| 字段 | 内容 |
|:---|:---|
| **记录时间** | 2026-07-14 |
| **状态** | mitigated |
| **优先级** | P1 |
| **节点** | Phase2B |
| **脚本/模块** | `run_daily_pipeline_20260622_v04.py` |
| **标签** | `phase2b` `body_empty` |

## 1. 问题

个别 VIP `body_empty` 时 needs_retry 后整批失败；或 soft-continue 过松导致「假绿」。

## 2. 解法

- 末次 needs_retry：仅 retry_reasons 全为 body_empty，且 body_ok 比例 ≥50%（≤2 条要求全 ok）才继续  
- `--no-soft-continue` / `--soft-continue-min-body-ratio`  

## 3. 后续

- [ ] body_empty 页面个案（站点/权限）单独排查  
