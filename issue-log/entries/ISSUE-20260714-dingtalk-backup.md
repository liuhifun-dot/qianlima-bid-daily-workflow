# ISSUE-20260714-dingtalk-backup

| 字段 | 内容 |
|:---|:---|
| **记录时间** | 2026-07-14 |
| **状态** | resolved |
| **优先级** | P1 |
| **节点** | Phase34 |
| **脚本/模块** | `gen_report_archive_push_formal_20260622_v06.py`, `runtime_preflight_...` |
| **标签** | `dingtalk` |

## 1. 问题

代码支持 `dingtalk_webhook_url_backup`，配置缺字段时 `backup_webhook_configured=false`，只发主群。

## 2. 解法

- 配置写入 backup  
- preflight 布尔 warning  
- 发送结果结构化 `backup_webhook.success`；失败不否 full_run  

## 3. 验证

配置有 backup 时 preflight 为 true；发送结构 mock PASS；真实补发 errcode=0（用户提供链接后）。
