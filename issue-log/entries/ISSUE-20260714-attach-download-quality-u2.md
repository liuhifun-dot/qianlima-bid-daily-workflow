# ISSUE-20260714-attach-download-quality-u2

| 字段 | 内容 |
|:---|:---|
| **记录时间** | 2026-07-14 |
| **更新时间** | 2026-07-14 |
| **状态** | mitigated |
| **优先级** | P0 |
| **节点** | Phase2B/2C |
| **脚本/模块** | `qianlima_cdp_body_attachment_reader_20260624_v05.py` |
| **来源** | 复测 U2；T6 冒烟 `ok=0/3`；agent.jsp 共用 req + `javascript:;` |
| **标签** | `attach` `download` `fileItem` `filepathId` `u2` |

## 1. 问题

看门狗（P0）已防卡死，但附件**下载成功率极低**：

- 多附件共用同一 `agent.jsp?req=...`，真正区分靠 `fileValidate(group,index)` / VIP `.fileItem[data-filepath-id]`
- 打开 agent.jsp 中间页时「点击此处」常为 `javascript:;`，SPA 抓不到文件
- 偶发抓到字节后 `file_type=unknown` 被校验拒绝（无魔数 sniff）

## 2. 根因（实机探针）

对 `bid-613407915`：

- 点 `.fileItem`「下载」→ `getFileStreamPreCheckPermission` → `getZBFileStreamByPathId` → OSS（zip/pdf）
- `context.request`（带 Cookie）可稳定拉取；页面 `fetch` 受 CORS 限制

## 3. 修复（2026-07-14 U2）

1. `detect_attachments` **优先** `.fileItem` + `filepathId`
2. 新主路径：`download_via_filepath_stream`（VIP 流式 API）
3. 回退：`fileitem_click` expect_download；再 preview_api / SPA / requests
4. 名称去「（86KB）」体积后缀；`sniff_file_type` 魔数识别
5. SPA：无效 HTML response 不立刻 fail after 1s，继续轮询

## 4. 验证

- 冒烟 run：`u2_attach_fix_20260714_174939`
- **5/5 `download_ok=True`**（此前同项目 0/3）
- 项目 `attach_status=partial`：4/5 文本可读；1 个扫描 PDF OCR weak_text（下载已成功）
- 证据：`改动说明/_retest_20260714b/u2_results.json`

## 5. 后续

- [ ] 外链-only（无 fileItem）项目回归
- [ ] `prepare_runtime` 刷新 runtime 哈希（U2 改脚本后）
- [ ] 生产 `D:\bid_workflow` 按需同步（未自动）
