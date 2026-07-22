# 问题总表（INDEX）

> 新问题插在表格**上方**。状态：`open` / `mitigated` / `resolved` / `wontfix`。  
> 详情见 `entries/` 同名文件。

| ID | 记录时间 | 节点 | 一句话问题 | 解法摘要 | 状态 | 优先级 | 文件 |
|:---|:---|:---|:---|:---|:---:|:---:|:---|
| ISSUE-20260714-attach-download-quality-u2 | 2026-07-14 | Phase2B/2C | 附件下载成功率极低（agent.jsp 共用 req） | fileItem+filepathId 流式 API + 魔数 sniff | mitigated | P0 | [entries/…](entries/ISSUE-20260714-attach-download-quality-u2.md) |
| ISSUE-20260714-attach-download-watchdog | 2026-07-14 | Phase2B/2C | 附件下载后静默卡死整管线 | 分段日志+下载/预览看门狗+附件预算 | mitigated | P0 | [entries/…](entries/ISSUE-20260714-attach-download-watchdog.md) |
| ISSUE-20260714-quota-zero | 2026-07-14 | Phase1 | 导出额度 0 导致待生成无法下载 | fail-fast + 可选 fallback 开关 | mitigated | P0 | [entries/…](entries/ISSUE-20260714-quota-zero.md) |
| ISSUE-20260714-cdp-contention | 2026-07-14 | Phase0/1/2B | 专用 CDP 被本机双开互踩 | 单写锁等 5～10 分钟 | resolved | P0 | [entries/…](entries/ISSUE-20260714-cdp-contention.md) |
| ISSUE-20260714-dingtalk-backup | 2026-07-14 | Phase34 | 抄送 webhook 未配置导致只发主群 | backup 字段 + 预检布尔 | resolved | P1 | [entries/…](entries/ISSUE-20260714-dingtalk-backup.md) |
| ISSUE-20260714-soft-continue | 2026-07-14 | Phase2B | body_empty 误整批失败或假绿 | soft-continue 白名单+比例 | mitigated | P1 | [entries/…](entries/ISSUE-20260714-soft-continue.md) |
| ISSUE-20260714-attach-rename | 2026-07-14 | Phase2B | 附件重试 WinError 183 | rename 幂等 | resolved | P1 | [entries/…](entries/ISSUE-20260714-attach-rename.md) |
