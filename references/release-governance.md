# Release Governance

## 目的

隔离正式包、测试包、安装 Skill 和运行目录，防止 Agent 从备份或临时脚本中选择错误版本。

## 四类目录

### 1. Skill 构建源

只用于编辑和打包。必须只有 SKILL.md、scripts、references、assets。

### 2. 已安装 Skill

由 .skill 安装到用户 Skill 目录。视为只读。禁止写入 runs、output、日志、下载和敏感配置。

### 3. 生产运行目录

由 prepare_runtime_20260622_v02.py 从已验证 Skill 创建。定时任务只调用这里的总入口。

### 4. 测试运行目录

从当前生产运行目录或当前 Skill 部署副本创建，命名：

    标讯自动化SOP_测试运行包_YYYYMMDD_HHMM_问题名

测试修改不能直接算正式修复。

## 冻结旧正式包

当前历史正式包：

    <冻结的生产正式包目录>

默认冻结。不要在实验中直接修改。只有经过测试和发布报告的文件才能同步回该目录，或由用户决定切换到新的生产运行目录。

## 机器可读版本身份

- Skill 根目录必须存在 release-manifest.json。
- 安装、准备运行目录前必须运行 verify_release_manifest_20260623_v01.py。
- 版本号、release_status 或任一文件 SHA256 不一致时停止。
- 正式部署只接受 release_status=released。
- release_candidate 只能用 prepare_runtime 的 --allow-release-candidate 创建隔离测试目录；不得覆盖生产运行目录或定时任务。
- 不能只根据目录名或脚本文件名判断版本。
- .skill 整包 SHA256 使用发布目录中的外部校验文件记录；包内 manifest 的 package_sha256 字段说明采用分离校验，避免自引用哈希。
## 当前发布文件

发布时只保留 SKILL.md 当前有效文件清单列出的脚本。scripts 中不允许存在：

- 备份
- 修复前副本
- 参考版
- debug 脚本
- 临时探针
- pycache
- 运行产物
- 敏感配置

历史材料放在 Skill 外的版本化归档目录。

## 修复流程

1. 从当前发布版创建测试副本。
2. 只在测试副本修改。
3. 用最小复现验证原错误。
4. 跑相关阶段回归。
5. 写修复报告：
   - 修改文件
   - 根因
   - 修改内容
   - 验证命令
   - 验证结果
   - 影响阶段
   - 未验证边界
6. 运行入口完整性检查。
7. 运行 Skill 结构校验。
8. 打包新版本。
9. 人工盯屏跑一次正式全流程。
10. 用户确认后再更新生产运行目录或定时任务。

缺少第 3、6、7、9 步时，不能称为正式修复。

## 入口完整性

总入口必须引用当前发布文件：

- run_daily_pipeline_20260622_v04.py
- gen_report_archive_push_formal_20260622_v06.py
- qianlima_cdp_body_attachment_reader_20260624_v05.py
- validate_cdp_body_attachment_reader_20260622_v03.py
- bid_business_rejudge_20260622_v04.py
- qianlima_auto_login_20260622_v02.py
- 权威模板 v05

所有引用必须存在；不得指向归档目录、测试目录或旧版脚本。

## 浏览器架构

- Phase 1 正式无人值守主线：专用 CDP Chrome。
- Phase 2：auto 沿用已登录通道，可选 CDP v04 或 Kimi。
- 不同时强制登录两个通道。
- 临时只读标题的 CDP 脚本禁止作为证据通道。
- 扫描 PDF/不支持附件可以进入待人工复核，不能伪装读取成功。

## 无人值守边界

自动恢复：

- Kimi stale PID。
- 普通登录超时且外部配置有账号密码。
- Phase 1 待生成、继续导出、校验中、生成中、刷新。
- 目标行短时后台等待。

硬停止：

- 验证码或访问验证。
- 两个浏览器通道都不可用。
- Phase 2 输入输出不一一对应。
- 正文/附件校验失败。
- Excel 校验失败。
- 共享盘失败。
- DWS 授权或上传失败。
- 缺少 doc_url。

硬停止时写失败报告，可发独立失败告警，不发正常日报。

## dry-run

dry-run 用于模板和逻辑彩排。输出必须是：

    status=dry_run_complete
    full_run_success=false

任何 Agent 把 dry-run 说成全流程成功都属于验收失败。

## 敏感配置

敏感配置永远不进入 Skill 或发布归档。发布前搜索以下内容：

- access_token
- webhook
- password
- Cookie
- Token
- 真实账号值
- 钉盘 ID

变量名和配置键可以存在，真实值不能存在。

## 发布物

每次正式打包至少输出：

- 版本化 .skill
- 文件 SHA256 清单
- Skill 校验结果
- 脚本 AST/帮助入口结果
- 离线彩排结果
- 已解决问题
- 未验证边界

不要在 active Skill 内创建 README、安装指南、changelog 或交接文档；对应内容放 references 或 Skill 外发布报告。

