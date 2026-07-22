# 首次安装与权限预检

## 目的

在新电脑、首次安装、账号切换或定时任务部署前执行本文件。先验证工具、登录态和权限，再运行正式流程。不要在 Skill 目录内保存账号、密码、Webhook、Token、Cookie 或钉盘 ID。

## 1. 安装 Skill

把正式 .skill 安装到 QClaw 用户 Skill 目录。安装后的目录只允许包含：

- SKILL.md
- scripts/
- references/
- assets/

不要在安装目录内运行日报，也不要让脚本把 runs、output、日志或下载文件写入 Skill。

## 2. 创建独立运行目录

执行：

    python scripts/prepare_runtime_20260622_v02.py --runtime-root "<本机运行目录>"

建议每台电脑固定一个运行目录，例如：

    <独立运行目录>

该命令只复制当前有效脚本和权威模板，不复制敏感配置。更新已存在的运行目录时，必须先验证新 Skill，再显式使用 --update。

## 3. 创建本机敏感配置

在 Skill 外创建配置文件。默认路径：

    <本机外部敏感配置路径>

需要提供：

- 千里马账号
- 千里马密码
- 订阅页 URL
- dingtalk_webhook_url
- dingtalk_drive_space_id
- dingtalk_drive_parent_id_for_dws
- dingtalk_drive_share_url
- 本地归档目录
- 共享盘归档目录

配置文件可以使用真实值，但任何 Agent 只能检查字段是否存在，不能在回复、日志、日报、Skill 或 Obsidian 中复述真实值。

也可以设置环境变量：

    QLM_BID_CONFIG=<本机敏感配置绝对路径>
    QLM_LOCAL_ARCHIVE=<本地归档目录>
    QLM_SHARE_ARCHIVE=<共享盘归档目录>
    DWS_CLI=<可用的 dws.cmd 绝对路径>
    CHROME_EXE=<Chrome 绝对路径>

## 4. 安装运行依赖

至少需要：

- Google Chrome
- Python 3.10+
- openpyxl
- pandas
- requests
- pyyaml
- websocket-client
- websockets
- playwright
- python-docx
- pdfplumber

Kimi PDF OCR 分支还需要：

- pymupdf
- pillow
- pytesseract
- 本机 Tesseract OCR

Phase 4 还需要：

- DingTalk Workspace CLI (dws)
- 有效的 DWS OAuth 授权
- 钉盘目标目录权限
- 钉钉机器人 Webhook
- 固定共享盘权限

## 5. 执行预检

先做静态检查：

    python <运行目录>\03_脚本工具\runtime_preflight_20260622_v02.py

首次正式运行或定时任务部署前必须做在线检查：

    python <运行目录>\03_脚本工具\runtime_preflight_20260622_v02.py --check-online --auto-recover-browser

结果含义：

- ready：可进入正式运行。
- static_checks_passed：只完成静态检查，不能证明正式运行权限齐全。
- permission_required：停止，由 Agent 明确列出需要用户授权或登录的动作。
- blocked：停止，先修复缺失依赖或不兼容工具。

预检不会输出真实账号、密码、Webhook、Token 或钉盘 ID。

## 6. 权限申请规则

遇到下列情况必须停止并请求用户操作：

- DWS 未授权：请求用户执行 dws auth login。
- 共享盘拒绝访问：请求用户连接公司网络或授予共享盘权限。
- 千里马出现验证码或 Access Verification：请求人工处理。
- 本机敏感配置缺失：请求用户创建或提供路径。
- Chrome/CDP 和 Kimi 都不可用：先自动启动专用 CDP Chrome 并恢复普通登录；只有配置缺失、验证码、风险验证或启动失败时才请求用户。

可自动恢复：

- Kimi stale PID。
- 普通登录超时且本机配置有账号密码。
- Phase 1 的待生成、校验中、生成中、刷新、继续导出。

## 7. 首次正式运行

先做一次人工盯屏的全流程运行。通过标准：

- Phase 1 下载的是本次目标记录，不是历史文件。
- Phase 2 正文和附件证据校验通过。
- Excel 校验通过并保留全部原始标讯。
- 本地归档、共享盘、钉盘上传全部成功。
- 钉盘返回 doc_url。
- 钉钉返回成功。
- full_run_success=true。

dry_run_complete 只表示彩排完成，不能写成正式成功。

## 8. 定时任务

只在人工盯屏全流程通过后部署定时任务。定时任务启动前运行在线预检；任何硬门禁失败时：

1. 停止正常日报。
2. 写失败报告。
3. 发送独立失败告警（如果配置）。
4. 不发送正常钉钉日报。


