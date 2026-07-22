# 千里马标讯自动化日报工作流

> **版本：** v1.2（2026-07-22）  
> **Skill 名：** `qianlima-bid-daily-workflow`  
> **状态：** 正式发布（`released`）

一套面向 **照明 / 路灯 / 光伏 / 充电桩** 等相关领域的 **千里马 VIP 标讯日流程** 自动化方案：从登录与批量导出，到规则筛选、正文/附件取证、业务复判、生成 Excel 日报，再到本地/共享盘归档、钉盘上传与钉钉简报。

本仓库对应 **完整版 Skill 源码包**（含 `scripts/`、`assets/`、`references/` 等），可安装到 QClaw / OpenClaw 等 Agent 环境，或配合独立运行目录使用。

---

## 这个项目是干什么的？

每天（或按工作日）自动完成「找标 → 筛标 → 核证据 → 出表 → 存档推送」：

| 目标 | 说明 |
|:---|:---|
| **减人工** | 减少在 VIP 上点导出、翻详情、复制字段的重复劳动 |
| **可复核** | 保留正文/附件证据与复判理由，避免「黑箱推荐」 |
| **可交接** | 独立运行目录 + 版本 manifest，方便换机器、换 Agent |
| **可通知** | 正式跑通后上传钉盘并发送钉钉短消息（需本机配置） |

**不做的事：** 不把账号密码、Webhook、Token 打进本仓库；不替你绕过验证码/二次验证。

---

## 能做什么？

- **Phase 0** 浏览器与登录预检（CDP 专用 Chrome，可自动恢复普通登录）  
- **Phase 1** 按日期范围批量导出千里马 Excel（含导出记录生成/刷新/下载状态机）  
- **Phase 2A** 标题与元数据初筛（硬排除 + 业务召回分层）  
- **Phase 2B/2C** 读 VIP 正文与附件（CDP；支持 docx/pdf/xlsx 与安全 zip 等）  
- **Phase 2D** 业务复判（推荐 / 待人工复核 / 排除）  
- **Phase 3** 按权威模板生成 **照明招标线索日报** Excel 并校验  
- **Phase 4** 本地归档 → 共享盘 → 钉盘（dws）→ 钉钉 webhook  

另有：版本校验 `release-manifest`、运行目录准备 `prepare_runtime`、问题单/改动说明/工作区目录规范文档。

---

## 需要什么工具与环境？

| 类别 | 要求 |
|:---|:---|
| **系统** | Windows（当前生产与脚本路径按 Windows 验证） |
| **Python** | 3.11+（见 `release-manifest.json`） |
| **浏览器** | Google Chrome；**CDP 调试端口**（默认 9222）与专用用户数据目录 |
| **千里马** | VIP 账号；可登录 `vip.qianlima.com` |
| **依赖库** | 以脚本实际 import 为准（如 openpyxl、playwright 相关等）；OCR 子模块见 `scripts/tpk-ocr/` |
| **钉钉（可选正式推送）** | 钉钉开放/机器人 Webhook；钉盘上传需 **DingTalk Workspace CLI（dws）** 并完成 `dws auth login` |
| **Agent（可选）** | QClaw / OpenClaw 等，用于定时任务与故障恢复编排 |
| **本机敏感配置** | **仓库外** 单独维护的 Markdown/配置（账号、webhook、钉盘 ID、归档路径）；通过 `--config` 或环境变量 `QLM_BID_CONFIG` 注入 |

### 环境变量（常用）

| 变量 | 含义 |
|:---|:---|
| `QLM_BID_CONFIG` | 本机敏感配置文件绝对路径 |
| `QLM_BID_RUNTIME` | 运行目录（产物写入处，如 `D:\bid_workflow`） |
| `QLM_CDP_PROFILE` | CDP Chrome 用户数据目录（可选） |

---

## 工作流步骤（简版）

```text
0 预检          日期校准 → CDP/登录态 → 必要时自动登录
1 导出          日期筛选 → 批量导出 → 导出记录生成/刷新 → 下载校验
2A 初筛         硬规则排除 + 业务相关召回
2B/2C 证据      读正文 + 附件（失败项有证据缺口标记）
2D 复判         keep / needs_review / reject
3 Excel 日报    按模板出表 + 契约校验
4 归档推送      本地/共享盘 → 钉盘 doc_url → 钉钉短消息
```

**正式成功条件（概念上）：** 校验通过且完成归档与钉盘链接后，才发正常钉钉日报；失败只发失败告警。  
**Dry-run：** 可只生成表与草稿，不真正发送（`full_run_success=false`）。

更细的操作说明见仓库内：

- `SKILL.md` — Agent 执行边界与阶段规则  
- `references/phase1-*.md` … `phase4-*.md` — 分阶段说明  
- `更新说明_v1.2.md` — 本版相对变更  

---

## 目录结构（仓库根 = Skill 根）

```text
qianlima-bid-daily-workflow/
├── SKILL.md                 # Agent 主说明
├── README.md                # 本文件（给人看）
├── release-manifest.json    # 版本与文件哈希
├── 更新说明_v1.2.md         # 版本更新说明
├── 改动说明.md              # 开发变更总账
├── scripts/                 # 正式 Python 脚本
├── assets/                  # Excel 样板、规则 yaml
├── references/              # 安装/阶段/故障/目录规范
├── issue-log/ · lessons/    # 问题单与经验
└── tool/                    # 可选依赖 skill 压缩包
```

**运行时请使用独立目录**（`prepare_runtime` 生成），**不要**把 runs/下载/日志写进本仓库或 Skill 安装目录。

---

## 快速开始（概念）

1. 克隆本仓库到本机。  
2. 安装 Python 依赖，准备 Chrome + CDP。  
3. 在仓库**外**创建敏感配置（勿提交 Git）。  
4. 运行版本校验：  
   `python scripts/verify_release_manifest_20260623_v01.py --root .`  
5. 用 `scripts/prepare_runtime_20260622_v02.py` 创建运行目录。  
6. 在运行目录执行总入口：  
   `python run_daily_pipeline_20260622_v04.py --config <敏感配置路径> …`  

定时任务建议：**只调用运行目录中的 `03_脚本工具`**，不要从 Agent skill 副本路径乱跑。

---

## 版本与安全

| 项 | 说明 |
|:---|:---|
| 当前发布 | **v1.2**（含 zip 附件 URL 保留、全排除 Excel 等修复） |
| 密钥 | **禁止**提交密码、Webhook、Token、Cookie、钉盘私密 ID |
| 校验 | 以 `release-manifest.json` + `verify_release_manifest` 为准 |

---

## 许可证与归属

内部/团队使用请以你们组织约定为准。对外开源若需补充 LICENSE，请仓库维护者自行添加。

---

## 相关链接

- 仓库：https://github.com/liuhifun-dot/qianlima-bid-daily-workflow  
