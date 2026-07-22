# Candidate Test Protocol

## 适用范围

用于 release_status=release_candidate 的千里马标讯自动化 Skill。候选测试不得覆盖已安装生产 Skill，不得更新生产定时任务。

## 必须使用的输入

- 候选 .skill 文件。
- 同目录 release-artifact-manifest JSON。
- Skill 外部的本机敏感配置。
- 专用 CDP Chrome 或已连接的 Kimi WebBridge。
- 独立、全新的测试记录目录。

禁止使用历史已下载 Excel 冒充本次 Phase 1 成果。断点测试必须明确标注上游文件来源。

## 测试目录

每次测试新建：

    <独立候选包测试记录目录>\YYYYMMDD_HHMM_vXX_rcXX

目录内至少包含：

    candidate/
    runtime/
    测试执行记录_YYYYMMDD_v01.md
    测试结论_YYYYMMDD_v01.md

运行产物由 runtime 自行写入 runs、output、logs。不要把产物写回解压后的 Skill。

## 第一组：包与版本门禁

1. 复制候选 .skill 和外部工件清单到 candidate。
2. 对 .skill 计算 SHA256，与外部清单一致。
3. 将 .skill 按 ZIP 解压到 candidate/unpacked。
4. 读取 release-manifest.json，记录 release_id 和 release_status。
5. 执行候选完整性校验：

    python -X utf8 <EXTRACTED_SKILL>\scripts\verify_release_manifest_20260623_v01.py --allow-release-candidate

6. 再执行一次不带候选参数的校验；它必须失败，证明候选包不能被当成 released。
7. 创建测试运行目录：

    python -X utf8 <EXTRACTED_SKILL>\scripts\prepare_runtime_20260622_v02.py --runtime-root <TEST_ROOT>\runtime --allow-release-candidate

验收：

- release_id 与外部清单一致。
- files_checked 等于 payload_files_checked。
- unlisted_files 和 stale_manifest_files 为空。
- runtime manifest 中 candidate_test_mode=true。
- runtime 位于 Skill 外部。

## 第二组：静态和在线预检

先运行静态预检：

    python -X utf8 <TEST_ROOT>\runtime\03_脚本工具\runtime_preflight_20260622_v02.py --config <CONFIG> --output <TEST_ROOT>\runtime\logs\preflight_static.json

再运行在线预检：

    python -X utf8 <TEST_ROOT>\runtime\03_脚本工具\runtime_preflight_20260622_v02.py --config <CONFIG> --check-online --auto-recover-browser --output <TEST_ROOT>\runtime\logs\preflight_online.json

验收：

- 静态预检 status=static_checks_passed。
- 在线预检 status=ready、full_run_ready=true。
- 至少一个浏览器通道可用且已登录。
- DWS 已授权。
- 本地和共享盘目录可访问。
- 配置只记录“字段存在”，不得记录账号、密码、Webhook、Token 或钉盘 ID 值。

## 第三组：Phase 1 在线状态机

只启动一次 Phase 1 Python 脚本。外层等待至少 25 分钟，不由 Agent 接管页面连续点击。

    python -X utf8 <TEST_ROOT>\runtime\03_脚本工具\bid_export_auto_v1.py --cdp-port 9222 --output-root <TEST_ROOT>\runtime\output

验收：

- 日期是本机校准后的昨天至今天。
- 导出配置是全部搜索结果、Excel、拓展字段。
- 配额提示中的实际可导出数量被记录。
- 目标行按本次提交时间和额度后数量锁定。
- 同一目标行的生成/继续导出只提交一次。
- 生成中或校验中按 15 至 20 秒刷新。
- 只下载目标行，不下载历史行。
- Excel 结构、工作表、行数和文件时间通过校验。
- live JSONL、checkpoint、最终 JSON/Markdown 日志均存在。

### Phase 1 恢复测试

首次 Phase 1 成功后，使用该次 checkpoint 再执行一次：

    python -X utf8 <TEST_ROOT>\runtime\03_脚本工具\bid_export_auto_v1.py --cdp-port 9222 --output-root <TEST_ROOT>\runtime\output_resume --resume-context <CHECKPOINT_JSON>

恢复测试必须：

- 输出 skip_new_export。
- 沿用原 target_record_time 和 target_record_count。
- 不重新选择日期。
- 不重新提交批量导出。
- 从同一目标行完成下载和 Excel 校验。

## 第四组：Phase 2 证据链

使用本次 Phase 1 Excel，从 Phase 2A 开始运行。正文/附件通道使用在线预检判定的已登录通道。

验收：

- Phase 2A 保存硬排除证据和正文候选清单。
- Phase 2B/2C 输入输出项目一一对应。
- 校验状态只能是 ok、needs_retry、blocked。
- need_login、body_empty、身份不匹配或附件证据缺口不得标记 ok。
- needs_retry 必须对原项目恢复登录并重试一次。
- blocked 必须停止正式流程。
- Phase 2D 不得出现 NameError。
- 正式 Phase 2D 禁止 --allow-incomplete-vip。
- validate_phase2_rejudge 必须 ok=true 才能进入报告阶段。

需要额外用历史 12 条基准候选做一次回放，确认之前的 1 条 need_login 和 2 条 body_empty 已恢复；未恢复则候选测试不通过。

历史基准不打入正式 Skill。候选交付目录必须另带 tests/fixtures/historical12_20260623_v04；若测试目录缺失，先从发布工程的同名 fixture 复制，不能直接写成“无基准数据”并跳过。

## 第五组：Phase 3/4 候选彩排

候选包只运行 dry-run，不发送正式钉钉：

    python -X utf8 <TEST_ROOT>\runtime\03_脚本工具\run_daily_pipeline_20260622_v04.py --start-phase 34 --business-json <BUSINESS_JSON> --raw-export <RAW_XLSX> --screening-json <SCREENING_JSON> --vip-json <VIP_JSON> --template <TEST_ROOT>\runtime\02_模板\照明招标线索日报_格式样板_20260616_v05.xlsx --config <CONFIG> --dry-run

验收：

- Excel 模板校验通过。
- 原始导出数据仍保留在日报工作表。
- 分类只使用推荐候选、待人工复核、排除。
- 公告类型只使用招标公告或中标通知。
- 输出 status=dry_run_complete。
- full_run_success=false。
- 没有 DWS 上传和 Webhook 发送。
- evidence_incomplete=true 时正式模式必须失败。

## 记录格式

测试执行记录逐步追加：

- 时间。
- release_id 和 .skill SHA256。
- 命令或脚本入口。
- 输入文件。
- 预期状态。
- 实际状态。
- 产物路径。
- 关键计数。
- 截图路径。
- 问题和恢复动作。
- 是否修改候选包。

测试结论必须逐项列出：

- 通过。
- 失败。
- 未测试。
- 证据路径。
- 是否允许晋升 released。

不得只写“全流程完成”。不得把 dry-run 当正式成功。

## 晋升规则

只有以下全部满足，才可把 release_status 改为 released：

1. 包、版本和运行目录门禁通过。
2. Phase 1 正常在线测试和 checkpoint 恢复测试通过。
3. 当前数据证据链通过。
4. 历史 12 条证据缺口恢复通过。
5. Phase 3 Excel 校验通过。
6. Phase 4 权限门禁通过。
7. 人工盯屏正式全流程通过。
8. 修复报告、测试执行记录和测试结论齐全。