# Runtime Requirements and External Interfaces

## 适用范围

在新电脑安装、首次正式运行、定时任务部署、权限变化或运行环境迁移时读取。详细安装顺序见 first-install-and-permissions.md。

## 运行目录原则

安装后的 Skill 是只读能力包，不是生产运行目录。使用：

    python scripts/prepare_runtime_20260622_v02.py --runtime-root "<本机运行目录>"

运行目录包含当前脚本、权威模板、runs、output、runtime 和 logs。敏感配置始终放在 Skill 和运行目录之外。

## 本机敏感配置

默认路径：

    <本机外部敏感配置路径>

可以用 QLM_BID_CONFIG 指定其它绝对路径。只检查字段存在，不输出字段值。

## 软件和接口

| 项目 | 用途 | 验证 |
|---|---|---|
| Chrome | 千里马登录和页面操作 | Chrome 可执行文件存在 |
| CDP 9222 | Phase 1 正式主线、Phase 2 正文附件（专用 profile） | /json/version 可访问；总入口 `cdp_run_lock` 单写等锁 5～10 分钟 |
| dingtalk_webhook_url_backup | 日报抄送（可选） | preflight：`dingtalk_webhook_backup_configured` 布尔 |
| Kimi WebBridge 10086 | 可选正文/附件通道 | running=true 且 extension_connected=true |
| Python 3.10+ | 全部脚本 | python --version |
| openpyxl/pandas | Excel 读取、生成、校验 | import 成功 |
| requests/pyyaml | HTTP 和配置 | import 成功 |
| websocket-client/websockets | CDP/Kimi 通信 | import 成功 |
| playwright | 正式 CDP 正文附件读取 | import 成功 |
| python-docx/pdfplumber | DOCX/PDF 提取 | import 成功 |
| pymupdf/pillow/pytesseract/Tesseract | Kimi 扫描 PDF OCR | import/可执行文件成功 |
| DWS CLI | 钉盘上传 | --version 和 drive upload --help 成功 |
| DWS OAuth | 钉盘授权 | auth status 成功 |
| Webhook | 钉钉消息 | 外部配置字段存在 |
| 共享盘 | 公司归档 | 固定 UNC 路径可访问 |

## 浏览器通道

### Phase 1

无人值守正式主线使用专用 CDP Chrome。该 profile 必须保持千里马登录态。Phase 1 页面状态机已经针对待生成、继续导出、校验中、生成中、刷新和下载设计。

### Phase 2

正式总入口仅支持 evidence-provider `auto` / `cdp`，二者均调用：

- `qianlima_cdp_body_attachment_reader_20260624_v05.py`（CDP endpoint 用 `http://localhost:PORT`）
- `validate_cdp_body_attachment_reader_20260622_v03.py`（needs_retry 时编排器最多整批重读 1 次）

包内 Kimi 脚本为兼容保留，**正式流水线不再调用**。不要同时强制登录 CDP 和 Kimi（互踢）。

Chrome 150+ 探测 CDP 时必须用 `localhost`，不要用 `127.0.0.1`。

### CDP 正文附件能力

当前 v05：

- 新建独立标签页并只关闭该标签页。
- 切换招标详情并核对正文身份。
- 识别附件。
- 解析千里马跳转页真实下载地址。
- 支持 DOCX、文本 PDF、XLSX、安全 ZIP。
- 扫描 PDF、图片、RAR/7Z、无真实下载地址的外链进入未完成证据，不伪装成功。
- 配套 v03 校验器要求输入输出项目一一对应。
- 只用登录地址、明确登录超时提示或可见密码表单判断 need_login；正文中的“未注册用户请先登录”不构成登录失效。
- 正文身份核对允许公告装饰前缀、公开选取包装标题和页面插入“企业信息”，但仍拒绝与项目标题无关的正文。

### Kimi 能力

Kimi 通道保留在线预览和 OCR 能力。stale PID 可自动修复；验证码必须人工处理。

## DWS 规则

不要固定相信某个版本号。选择 DWS 时必须实际运行：

    dws --version
    dws drive upload --help
    dws auth status --format json

发现全局 dws 损坏时，继续检查 WorkBuddy 内置 DWS；只使用实际返回成功的命令。当前本机曾验证 WorkBuddy DWS v1.0.33 可用，但以后仍以功能探测为准。

调用 DWS 子进程前只对该子进程移除异常 NODE_OPTIONS。上传失败、授权失败或没有 doc_url 时停止，不发正常钉钉日报。

## 归档路径

本地归档与共享盘路径 **不得写死在脚本内**，只能来自：

1. 环境变量 `QLM_LOCAL_ARCHIVE` / `QLM_SHARE_ARCHIVE`
2. CLI：`--local-archive-dir` / `--share-archive-dir`
3. 外部敏感配置字段：`local_archive_dir` / `share_archive_dir`

示例（配置文件，路径按本机填写）：

    local_archive_dir: "<本地归档目录>"
    share_archive_dir: "<共享盘 UNC 归档目录>"

未配置时 Phase 4 正式运行会 GateError 停止（dry-run 可用运行目录内临时路径）。
需要变更时先更新外部配置并重新运行预检。

## 预检

静态检查：

    python <运行目录>\03_脚本工具\runtime_preflight_20260622_v02.py

正式/定时运行前在线检查：

    python <运行目录>\03_脚本工具\runtime_preflight_20260622_v02.py --check-online --auto-recover-browser

状态：

- ready：可正式执行。
- static_checks_passed：只证明本机依赖大致齐全。
- permission_required：需要用户登录、授权或连接网络。
- blocked：缺少依赖或工具不兼容。

## 完整成功定义

dry-run、no-send、附件跳过、正文只读标题、DWS 未上传都不能称为完整成功。

完整成功必须同时满足：

- Phase 1 本次文件下载校验通过。
- Phase 2 正文/附件证据校验通过。
- Phase 3 Excel 校验通过。
- 本地和共享盘归档成功。
- 钉盘返回 doc_url。
- 钉钉返回成功。
- full_run_success=true。


