# ISSUE-20260714-attach-download-watchdog

| 字段 | 内容 |
|:---|:---|
| **记录时间** | 2026-07-14 |
| **更新时间** | 2026-07-14 |
| **状态** | mitigated |
| **优先级** | P0 |
| **节点** | Phase2B/2C |
| **脚本/模块** | `qianlima_cdp_body_attachment_reader_20260624_v05.py` |
| **来源** | 标神工单 `ISSUE-20260714-attach-download-watchdog_待转交_v01.md`；run `D:\bid_workflow\runs\20260714_110303` |
| **标签** | `attach` `watchdog` `timeout` `2c` |

## 1. 问题

附件下载后静默过久 → 外层 pipeline 假死/SIGKILL；无分段日志；requests 读超时 600s；预览/SPA 死循环等待。

## 2. 发布包已做（P0）

- 分段日志：`runs/<run_id>/99_logs/phase2c_attach_*.log`（PROJECT/ATTACH/DL/SPA/PREVIEW/OCR）
- 下载：读超时 90s + 字节 stall 60s + hard 300s
- SPA：wall 45s + 信号 stall
- 预览 PDF.js：wall 60s + stall 45s
- 单附件预算 180s / 单项目 420s
- OCR 进度心跳（此前已做）stall 300s / hard 30min

## 3. 验证

- py_compile PASS
- 端到端重跑 `bid-613432521`：待生产/联调实测

## 4. 后续

- [ ] 用卡死项目实机验证不再 375s 静默
- [ ] D 盘生产脚本同步到新哈希
