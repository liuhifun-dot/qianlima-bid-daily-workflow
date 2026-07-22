# 标讯自动化日报工作流

> **版本：** v1.2（2026-07-22）  
> **Skill 名：** `qianlima-bid-daily-workflow`  
> **本仓库内容：** **干净正式包**（脚本 + 资源 + 参考文档 + 本说明），**不含**运行日志、复测记录、内部改动流水账。

一套面向 **照明 / 路灯 / 光伏 / 充电桩** 等相关领域的 **千里马 VIP 标讯日流程** 自动化：登录与批量导出 → 规则筛选 → 正文/附件取证 → 业务复判 → Excel 日报 → 本地/共享盘归档 → 钉盘与钉钉推送。

---

## 这个项目是干什么的？

每天（或按工作日）自动完成「找标 → 筛标 → 核证据 → 出表 → 存档推送」，减少在 VIP 上手动点选与抄表，并保留可复核的证据与结论。


---

## 能做什么？

| 阶段 | 能力 |
|:---|:---|
| **0 预检** | CDP Chrome、登录态检查，必要时自动登录 |
| **1 导出** | 按日期批量导出千里马 Excel，并完成导出记录生成/下载 |
| **2A 初筛** | 标题/元数据硬规则排除 + 业务召回 |
| **2B/2C** | 读 VIP 正文与附件（docx/pdf/xlsx 等） |
| **2D 复判** | 推荐 / 待人工复核 / 排除 |
| **3 日报** | 按模板生成照明招标线索日报 Excel 并校验 |
| **4 归档推送** | 本地/共享盘 → 钉盘 → 钉钉短消息 |

---

## 需要什么工具？

| 类别 | 要求 |
|:---|:---|
| 系统 | Windows（当前按 Windows 路径与生产验证） |
| Python | 3.11+ |
| 浏览器 | Chrome + **CDP 端口**（默认 9222） |
| 账号 | 千里马 VIP |
| 正式推送（可选） | 钉钉机器人 Webhook；钉盘需 **dws**（DingTalk Workspace CLI）并登录 |
| Agent（可选） | QClaw / OpenClaw 等，用于定时编排 |
| 敏感配置 |（账号/webhook/钉盘 ID/归档路径），用 `--config` 或 `QLM_BID_CONFIG` |

常用环境变量：`QLM_BID_CONFIG`、`QLM_BID_RUNTIME`（运行目录，如 `D:\bid_workflow`）。

---

## 工作流步骤（简版）

```text
0 预检     → 日期、CDP/登录
1 导出     → 日期筛选、批量导出、下载校验
2A 初筛    → 硬排除 + 召回
2B/2C 证据 → 正文 + 附件
2D 复判    → keep / needs_review / reject
3 Excel    → 出表 + 校验
4 归档推送 → 本地/共享盘 → 钉盘 → 钉钉
```

正式成功：校验通过并完成归档与钉盘链接后，再发正常钉钉日报。失败只发失败告警。

---

## 仓库里有什么（干净包）

```text
├── README.md              # 本说明（给人）
├── SKILL.md               # Agent 执行说明
├── 更新说明_v1.2.md       # 本版变更摘要
├── release-manifest.json  # 版本与文件哈希
├── scripts/               # 正式脚本
├── assets/                # Excel 样板、规则
└── references/            # 安装与分阶段参考文档
```

**故意不包含：** 运行日志、e2e 原始输出、内部改动流水账、issue 工单库、临时调试脚本、本机密钥。

运行产物请写到 **独立运行目录**（`prepare_runtime` 创建），不要写回本仓库。

---

## 快速开始（概念）

1. 克隆本仓库。  
2. 安装 Python 依赖，准备 Chrome CDP。  
3. 在仓库**外**建敏感配置。  
4. `python scripts/verify_release_manifest_20260623_v01.py --root .`  
5. `python scripts/prepare_runtime_20260622_v02.py …` 创建运行目录。  
6. 在运行目录用总入口 `run_daily_pipeline_20260622_v04.py` 执行。  

更细规则见 `SKILL.md` 与 `references/`。

---

## 版本

| 项 | 说明 |
|:---|:---|
| 当前 | **v1.2** |

仓库：https://github.com/liuhifun-dot/qianlima-bid-daily-workflow  
