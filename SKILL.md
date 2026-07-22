---
name: qianlima-bid-daily-workflow
description: Execute, test, repair, package, or review the daily Qianlima VIP bid workflow for lighting, road lighting, solar lighting, photovoltaic, charging-pile, and related project leads. Use for 标讯自动化, 千里马VIP两天日期筛选, 批量导出, 导出记录待生成/校验中/生成中/刷新/下载, 正文与附件读取, PDF/OCR证据复判, Excel日报, 本地和共享盘归档, 钉盘上传, 钉钉Webhook, QClaw/WorkBuddy冷启动, 定时任务, or workflow troubleshooting.
---

# Qianlima Bid Daily Workflow

## 核心边界

- 按 Phase 0、1、2A、2B/2C、2D、3、4 顺序执行。
- 不跳过失败阶段，不用历史下载冒充本次结果，不把 dry-run 写成正式成功。
- 不清浏览器数据，不删除 Cookie，不关闭用户正在使用的浏览器，不同时强制登录 CDP 和 Kimi。
- 不把账号、密码、Webhook、Token、Cookie、钉盘 ID 或私密地址写入 Skill、日志、日报或 Obsidian。
- 钉盘没有 doc_url、共享盘失败、DWS 未授权时，不发送正常钉钉日报。
- 正文或附件证据不完整时，不得推荐；按证据门槛进入待人工复核或硬排除。
- 只在独立运行目录执行脚本。禁止把 runs、output、日志、下载文件写入安装后的 Skill。

## 首次安装

新电脑、首次安装或权限变化时，先读取 references/first-install-and-permissions.md。

1. 先读取根目录 release-manifest.json，运行 scripts/verify_release_manifest_20260623_v01.py；版本、状态或任一哈希不一致时停止。
2. 正式版使用 scripts/prepare_runtime_20260622_v02.py 创建独立运行目录。
   候选包测试必须额外传入 --allow-release-candidate，并使用全新的测试运行目录；禁止把候选目录用于生产定时任务。
3. 在 Skill 外创建本机敏感配置。
4. 运行 runtime_preflight_20260622_v02.py；它必须校验运行目录的 release_id 和文件哈希。
5. 正式运行前使用 --check-online。
6. permission_required 时列出需要用户完成的登录或授权，不要猜配置。

## 目录规范

跨 Skill 通用标准（本机权威）：`C:\Users\user\.agents\standards\`  
包内副本：
- `references/workspace-directory-standard.md`（三层模型、命名消歧、同步清单；标讯见附录 A）
- `references/workspace-recording-standard.md`（何时写 runs/changes/issues、模板）

以下为摘要。

### Skill 包结构（安装源）

```
qianlima-bid-daily-workflow/
├── SKILL.md              流程说明 + 目录规范
├── release-manifest.json 版本校验
├── scripts/              正式脚本（23个）
├── references/           参考文档（含目录规范模板）
└── assets/               Excel 格式样板等资源文件
```

### 安装后创建的运行目录（skill 外，由 prepare_runtime 建立）

```
D:\bid_workflow\
├── 02_模板\              Excel 格式样板（prepare_runtime 从 assets/ 复制）
├── 03_脚本工具\          正式脚本（prepare_runtime 从 scripts/ 复制）
├── config\               配置文件（cdp_auth.yaml 等，手动创建）
├── filter_rules\         筛选规则
├── runs\<run_id>\        每次 run 的产物
│   ├── 99_logs\          运行日志 JSON
│   ├── 03_body\          正文证据
│   ├── 06_report\        Excel 报告
│   └── 07_archive_push\  归档推送产物
├── tasks\                lessons.md + SOP
├── 项目运行日志_YYYYMMDD.md   运行日志（pipeline 自动写）
└── 每日标讯筛选结果\       归档
```

### Agent workspace 目录（OpenClaw 管理，skill 不涉及）

详见 `references/workspace-directory-standard.md` 第 3 节。

### 写入规则

| 文件类型 | 写入位置 | 说明 |
|----------|----------|------|
| 运行日志 | `D:\bid_workflow\项目运行日志_YYYYMMDD.md` | pipeline 自动写，无需手动维护 |
| 维护日志 | `workspace\changes\YYYY-MM-DD.md` | 人工修复问题时写 |
| 问题工单 | `workspace\issues\` | 发现问题建工单 |
| 经验沉淀 | `workspace\tasks\lessons.md` | 用户纠正时写 |
| 调试脚本 | `workspace\tmp\` | 用完即删，不保留 |
| 临时文件 | `workspace\tmp\` | 用完即删 |
| 截图 | `workspace\tmp\` | 用完即删 |

### 禁止行为

- 禁止把 runs、output、日志、下载文件写入 Skill 安装目录
- 禁止在 workspace 根目录写非配置文件
- 不确定归类的文件 → `workspace\tmp\`，事后归档或删除

## 当前有效文件

只调用下列脚本；未列出的备份、旧版、调试脚本不能执行。

- 总入口：run_daily_pipeline_20260622_v04.py
- Phase 1：bid_export_auto_v1.py
- Phase 2A：bid_screening_20260622_v02.py
- Kimi 正文：kimi_vip_body_read_20260622_v04.py
- Kimi 附件/OCR：kimi_attachment_preview_read_20260622_v06.py
- CDP 正文+附件：qianlima_cdp_body_attachment_reader_20260624_v05.py
- CDP 证据校验：validate_cdp_body_attachment_reader_20260622_v03.py
- Phase 2D：bid_business_rejudge_20260622_v04.py
- Phase 2 校验：validate_phase2_rejudge_20260622_v02.py
- Phase 3/4：gen_report_archive_push_formal_20260622_v06.py
- Excel 构建：report_builder_20260615_v1.py
- Excel 校验：validate_excel_template_contract_20260603_v02.py
- 登录恢复：qianlima_auto_login_20260622_v02.py
- 浏览器自动恢复：ensure_browser_channel_20260622_v01.py
- 首次预检：runtime_preflight_20260622_v02.py
- 版本校验：verify_release_manifest_20260623_v01.py

权威模板：

    assets/照明招标线索日报_格式样板_20260616_v05.xlsx

运行时模板由 prepare_runtime 复制到运行目录的 02_模板。

## Phase 0：预检与浏览器所有权

1. 校准本机日期，计算昨天 00:00:00 至今天 23:59:59。
2. 执行在线预检；无人值守任务使用 --auto-recover-browser。
3. 检查 Kimi 10086（主通道）和 CDP 9222（备选通道）的真实登录态。
4. **单通道模式**（2026-07-10 更新）：
   - 同一千里马账号不能同时登录两个通道（会互踢）
   - Phase 1（千里马导出）当前只支持 CDP 通道
   - 如果 Kimi 已登录但 CDP 未登录，停止执行并提示用户手动切换
   - 后续计划：Phase 1 改造为支持 Kimi 通道
5. Kimi 通道自动恢复：daemon 未运行时，自动清理残留 PID、启动 Chrome、启动 daemon、等待扩展连接。
6. 如果普通登录超时且外部配置有账号密码，自动恢复。
7. 验证码、Access Verification、账号二次验证属于硬停止。

### 通道分工（2026-07-10 更新）

**当前状态：单通道模式**

| 阶段 | 支持通道 | 说明 |
|------|----------|------|
| Phase 1 | 仅 CDP | 千里马导出脚本只支持 CDP |
| Phase 2B/2C | Kimi 或 CDP | 优先 Kimi，失败时回退 CDP |
| Phase 2D/3/4 | 不依赖浏览器 | 纯数据处理 |

**互踢问题**：
- 同一千里马账号不能同时登录两个通道
- 如果 Kimi 已登录，不能自动启动 CDP（会互踢）
- 需要手动在 CDP Chrome 中登录，或从 Phase 2 断点续跑

**后续计划**：
- Phase 1 改造为支持 Kimi 通道
- 改造完成后，Kimi 可作为主通道运行全流程

### Kimi WebBridge 通道状态（主通道）

**定位**：Kimi WebBridge 为主通道，CDP 为备选通道。

**环境要求**：
- 只在 Chrome 中启用 Kimi WebBridge 扩展（禁用 Edge 等其他浏览器的同名扩展）
- 两个扩展同时连接 daemon 会导致 502 和连接不稳定
- daemon 版本 v1.11.1，扩展版本 v1.11.0+

**自动恢复逻辑**（`ensure_browser_channel_20260622_v01.py` 已集成）：
1. 检查 daemon 状态（`extension_connected`）
2. 如果 daemon 未运行：
   - 检测 Chrome 是否运行 → 未运行则自动启动
   - 清理残留 `daemon.pid`（仅在进程不存在时删除，安全）
   - 启动 daemon
   - 等待扩展连接（最多 15 秒）
3. 验证千里马登录态
4. 如果登录态无效，尝试自动登录

**已知问题与修复状态（2026-07-09 测试确认）**：

| 问题 | 表现 | 状态 | 解决方案 |
|------|------|------|----------|
| **多扩展冲突** | extension_id 频繁变化，502 | ✅ 已修复 | 只保留 Chrome 的扩展，已禁用 Edge 扩展 |
| **间歇性 502** | daemon 与扩展通信中断 | ✅ 已修复 | 升级 daemon 到 v1.11.1 + 单浏览器 |
| **No current window** | Chrome 最小化/后台时找不到窗口 | ✅ 已修复 | 升级后稳定 |
| **group_title 写入乱码** | 标签组名称显示 `????` | ✅ 已修复 | 升级 v1.11.1 后正常显示中文 |

**使用建议**：
- 正式定时任务优先使用 Kimi 通道
- CDP 通道作为备选，Kimi 断开时自动回退
- 扩展升级命令：`kimi-webbridge upgrade`
- 详细文档：`references/kimi-webbridge-usage.md`

**健康检查命令**：
```bash
~/.kimi-webbridge/bin/kimi-webbridge status
```
- `running: true` + `extension_connected: true` → 正常
- 502 时：等待 30 秒重试，或重启 daemon

## Phase 1：两天日期导出

操作前读取 references/phase1-qianlima-export.md。

通过条件不是“点击了导出”，而是：

- 页面显示昨天至今天的自定义日期；
- 导出配置为全部搜索结果、Excel、拓展字段；
- 导出记录目标行按时间、条数、格式和状态识别；
- 待生成时点击生成；
- 配额弹窗出现时点击继续导出；
- 校验中或生成中时等待并点击目标行刷新；
- 目标行变为已生成/下载；
- 下载文件时间、大小、工作表和行数校验通过。

不能识别目标行时停止，绝不下载历史可下载行。

- Agent 只启动一次 Phase 1 Python 脚本，不在网页上自行连续点击。
- 给 Phase 1 至少 15 分钟运行时间；脚本每 15 秒输出心跳，心跳持续时不得终止进程或询问用户。
- 同一目标行的生成和继续导出只提交一次；随后每 15 至 20 秒刷新状态。
- 配额提示中的剩余额度必须更新为本次目标数量；目标行一旦锁定，不因旧行已有下载而切换。
- 外层编排器必须给 Phase 1 至少 25 分钟，且大于脚本内部 20 分钟状态机超时。
- 进程异常退出时读取 `qianlima_phase1_checkpoint_*.json`，用 `--resume-context` 继续原目标行；禁止重新发起导出。

## Phase 2A：标题与元数据初筛

操作前读取 references/phase2-screening-rules.md。

- 先做硬排除，再做业务召回和边界分层。
- 标题级排除必须保存明确证据。
- 关键词只是召回线索，不是最终结论。
- 保留全部原始标讯，便于人工发现漏筛。

## Phase 2B/2C：正文和附件证据

总入口参数：

    --evidence-provider auto|cdp|kimi

auto 沿用当前已登录通道。

CDP 通道：

- 使用 Playwright 连接已有 CDP Chrome。
- 新建并只关闭自己创建的标签页，不关闭浏览器。
- 切换招标详情，校验正文与项目标题一致。
- 识别附件并解析千里马两步下载地址。
- 外部 SPA 下载页先尝试有时限的浏览器下载事件和网络响应捕获；约 30 秒内没有真实文件则返回结构化证据缺口，不循环等待。
- 支持 DOCX、PDF、XLSX 和安全 ZIP 子文件。
- 扫描 PDF、图片、RAR/7Z、无法下载的外链不得标记读取成功。
- 每个输入项目必须有一条输出。
- 运行 CDP 证据校验器后才能进入 Phase 2D。
- 校验状态只允许 ok、needs_retry、blocked；needs_retry 必须恢复当前项目并重试，blocked 必须停止正式流程。
- 单项目出现登录超时时，关闭已知弹窗、回到 VIP 根地址核对账号、必要时自动登录，再重试原项目一次；仍失败则停止。

Kimi 通道：

- 使用既有登录态读取 VIP 正文和附件预览。
- PDF 先提取文本，必要时 OCR。
- stale PID 可以自动修复；验证码不能绕过。

**通道优先级规则**：
- Kimi WebBridge 为主通道，CDP 为备选通道。
- 当 `--evidence-provider auto` 时，优先使用 Kimi 通道。
- 如果 Kimi 通道在 Phase 2B/2C 运行中断开（WebBridge 崩溃、端口无响应、502、No current window），自动回退到 CDP 通道。
- 回退前记录日志：`[回退] Kimi 通道不可用，切换到 CDP 通道`。
- 如果 CDP 也不可用，停止流程并报告错误。

**Kimi 通道稳定性说明**：
- Kimi WebBridge v1.11.1 升级后稳定性已验证（2026-07-09 测试：8/9 通过）
- 正式定时任务优先使用 Kimi 通道
- CDP 通道作为备选，Kimi 不可用时自动回退

证据门槛：

- body_read_ok=false 不能 keep。
- attachment_required=true 且 attachment_read_ok=false 只能 needs_review，除非有独立硬排除证据。
- 任一必读附件未解析完成，不能把“读到一个附件”当全部成功。
- 短文本、错项目正文、登录页和 HTML 跳转页不是证据。

## Phase 2D：业务复判

- 只输出 keep、needs_review、reject。
- **合法全排除场景**：当天 Phase 2A 将所有项目硬规则排除（都是 reject 且带硬筛选理由）时，根本没有项目需要读 VIP 正文，VIP 正文 JSON 为空是**正常结果**。此时校验器 validate_phase2_rejudge_20260622_v02.py 会自动放行（VIP 空降级为 warning），正常生成“全排除”日报。**严禁为了过校验而手动构造 business JSON 或 VIP JSON（违反“绝不编造”底线）。**
- 但如果存在 keep/needs_review 项，或 VIP summary 有 blocking 状态（need_login/captcha/error/login_timeout），VIP 空仍报 error 拦截，必须先恢复登录/重读正文。
- --allow-incomplete-vip 只能与 --dry-run 同时使用；输出必须标记 evidence_incomplete=true，不得正式归档或发送钉钉。
- keep 使用“推荐候选”，不能写“确认投标”。
- reject 必须有标题硬排除证据或正文/附件证据。
- 服务词只在标题或项目名称、项目类型、采购范围、招标内容明确描述采购标的时才可硬排除；禁止投标条款、监理单位和开工通知中的“监理”只是背景。
- 标题明确为施工、EPC、工程总承包、安装或建设，且正文有工程量清单、施工或安装证据时，不得仅凭背景服务词排除。
- 选聘资产评估、值班用房租赁、检验检测/监测、纯咨询设计、纯道路硬化、无安装的纯设备采购属于明确排除。
- 学校/医院小额照明、综合改造、村镇提升、市政道路、光伏/充电桩边界不清时读取正文和附件；证据不足进入 needs_review。

## Phase 3：Excel 日报

操作前读取 references/phase3-excel-contract.md。

- 基于 v05 权威模板生成。
- 公告类型只允许“招标公告”和“中标通知”。
- 统计使用推荐候选、待人工复核、排除。
- 推荐、待复核、排除摘要分区。
- 保留全部原始标讯及复判关联字段。
- ?????? Phase 2D `page_attachments` ????????????????????
- ????????????????????????????????????????????
- ?????????????????????????
- ??????????????????????????/??????????
- ??????????????????????????
- 推荐顺序与钉钉一致。
- 校验失败时停止 Phase 4。

## Phase 4：归档、钉盘和钉钉

操作前读取 references/phase4-archive-dingtalk.md。

固定顺序：

1. 本地归档。
2. 共享盘归档。
3. DWS 上传钉盘并取得 doc_url。
4. 发送钉钉短消息。

**钉钉 webhook 发送规则**：
- 必须使用 Python（urllib 或 requests），禁止使用 PowerShell 发送包含中文的 webhook 消息。
- PowerShell 的 `Invoke-RestMethod` 在处理中文 UTF-8 编码时有问题，会导致乱码。
- 备份 webhook 也必须使用 Python 发送。

任一门禁失败都停止正常日报。dry-run 只生成报告和消息草稿，结果必须显示：

    status=dry_run_complete
    full_run_success=false

正式成功必须显示：

    status=full_run_complete
    full_run_success=true

## 断点续跑

- 先读最新 run manifest、pipeline manifest 和运行日志。
- 已有有效原始 Excel 时，从 2A 开始并显式传 --raw-export。
- 已有通过校验的业务复判 JSON 时，从 34 开始并显式传 --business-json。
- 不凭聊天记忆猜路径，不从头重复下载。

## 失败报告

硬停止时记录：

- run_id
- 失败阶段
- 页面 URL 或命令
- 错误原文
- 最后成功产物
- 截图或页面文本
- 已尝试恢复动作
- 下一步人工动作
- 是否发送钉钉

正常日报未成功时，只允许发送独立失败告警。

## 按需读取

- 首次安装和权限：references/first-install-and-permissions.md
- Phase 1：references/phase1-qianlima-export.md
- Phase 2：references/phase2-screening-rules.md
- Phase 3：references/phase3-excel-contract.md
- Phase 4：references/phase4-archive-dingtalk.md
- 故障恢复：references/troubleshooting.md
- **工作区记录规范（runs/changes/issues）：references/workspace-recording-standard.md**
- 基准样本：references/verified-baseline-cases.md
- 环境依赖：references/runtime-requirements.md
- 修复发布：references/release-governance.md
- 团队知识规划：references/team-knowledge-obsidian-plan.md
- 候选测试协议：references/candidate-test-protocol.md
- 给人看的改动总账：改动说明.md

