# Skill / Runtime / Agent 目录与记录标准（通用）

> **定位：** 以后写**任何**新 Skill 都按本文件落地目录与记录习惯。  
> **目的：** 把标讯自动化踩过的坑固化成约束，避免根目录脏、日志混写、多副本漂移、业务模板假通用。  
> **权威副本：** `C:\Users\user\.agents\standards\skill-workspace-directory-standard.md`  
> **配套：** 同目录 `skill-recording-standard.md`（何时写、模板正文）；`templates/` 可直接复制。

**不是**「标讯专属目录说明」。标讯特例见文末 **附录 A**。

---

## 0. 先分清三层（硬约束）

| 层 | 是什么 | 放什么 | 绝不放 |
|:---|:---|:---|:---|
| **A. Skill 包**（可分发安装源） | 给人/给 Agent 装的流程+脚本+文档 | `SKILL.md`、正式 scripts、references、assets、变更账 | 运行产物、密钥、调试脚本、本机路径硬编码 |
| **B. Runtime**（业务运行目录） | 用户指定的独立工作盘，如 `D:\xxx_workflow` | 按 run 的产物、本机配置**引用**、业务归档 | Skill 源码长期分叉当「真源」；根目录乱堆临时文件 |
| **C. Agent workspace**（OpenClaw/QClaw 家） | Agent 的家目录 | 身份配置、运维摘要、工单、临时探针 | 业务大文件（xlsx/下载包整树）、密钥明文 |

```text
改代码 / 改规则  →  优先改 A 的权威源，再同步到 B 的安装副本
跑业务          →  产物只写 B
记「今天怎样」  →  摘要写 C（可选从 B 摘）
```

**坑（已踩）：** 只改 B 的脚本副本 → 重装/发版/另一台机器 bug 复活。

---

## 1. 核心原则（所有 Skill 通用）

1. **根目录不脏**：Agent workspace 根只放身份/配置类 md；不放 `.py`/截图/临时 json/散落报告。  
2. **运行日志 ≠ 维护日志**：跑批结果 vs 修 bug 记录，分目录。  
3. **产物按 run 隔离**：每次执行一个 `run_id` 目录，禁止覆盖式 dump 到固定文件名当唯一真相。  
4. **Skill 与 Runtime 分离**：禁止把 runs/output/下载写进 Skill 安装目录。  
5. **密钥外置**：密码/Token/Webhook 不进 Skill、不进 workspace 日志、不进会打包的 zip。  
6. **命名消歧**：同名目录在不同层语义不同，见 §2。  
7. **有权威源**：业务逻辑只认一份源码；安装副本只同步。  
8. **不确定先 tmp**：归类不清 → workspace `tmp/`，事后归档或删，不进根目录。

---

## 2. 命名消歧（必读，防抄歪）

| 名字 | 所在层 | 含义 | 典型内容 |
|:---|:---|:---|:---|
| `runs/<run_id>/` | **B Runtime** | **机器产物树** | xlsx、json、截图、pipeline_manifest、99_logs |
| `runs/YYYY-MM-DD.md` | **C Workspace** | **给人看的运行摘要** | run_id、成败、失败阶段、产物路径指针 |
| `changes/YYYY-MM-DD.md` | **C Workspace** | 维护日志 | 问题/根因/改了哪些文件/同步勾选/验证 |
| `issues/ISSUE-…` | **C Workspace** | 工单 | 待跟进缺陷 |
| `issue-log/` | **A Skill** | 可分发的问题库 | 随版本走的已知问题 |
| `改动说明.md` / `CHANGELOG` | **A Skill** | 版本总账 | 发版给人看 |
| `lessons/` | **A 或 C** | 可复用教训 | 规则级；重要的应回写 A |

**禁止：** 把 Runtime 的 xlsx 整包丢进 Workspace 的 `runs/`。  
**禁止：** 把 Workspace 的运维 md 写进 Skill 的 `scripts/`。

---

## 3. A. Skill 包标准结构

### 3.1 最小正式 Skill（推荐）

```text
[skill-name]/
├── SKILL.md                 # 流程 + 指向本规范 + 权威源说明
├── 改动说明.md 或 CHANGELOG  # 强烈建议：版本级变更
├── scripts/                 # 正式脚本；薄封装可省略，见 3.2
├── references/
│   ├── skill-workspace-directory-standard.md  # 本规范副本或链接说明
│   └── …业务文档
├── assets/                  # 可选：模板样板
├── issue-log/               # 可选但正式发布建议有
│   ├── TEMPLATE.md
│   └── entries/
└── lessons/                 # 可选：可复用业务规则
    └── lessons_log.md
```

**规则：**

- 只进正式脚本与文档；`__pycache__`、调试脚本、e2e 原始 dump 不进包。  
- 有版本校验时用 `release-manifest.json`（按你们发布流程）。  
- SKILL.md 必须写清：**产物写到哪（Runtime）**、**密钥从哪读**、**禁止写 Skill 目录**。

### 3.2 薄封装 Skill（无业务大码）

```text
[thin-skill]/
├── SKILL.md
├── run_xxx.py               # 只解析参数，调用权威 scripts
└── （可选）references/
```

必须在 SKILL.md 写死或环境变量声明：

- `QLM_…_SCRIPTS` / `SKILL_SCRIPTS` → 权威脚本目录  
- `…_RUNTIME` → 运行目录  
- `…_CONFIG` → 敏感配置路径  

**坑：** 薄封装 zip 单独发给别人却不给权威 scripts → 无法跑。一体部署包要带 monorepo 或完整 Skill。

---

## 4. B. Runtime 标准骨架（业务自填子目录）

**路径由用户指定，禁止在 Skill 里写死盘符当唯一路径。**

```text
[runtime]/
├── config/                  # 或仅存放「指向外置敏感配置」的说明；密钥优先外置
├── runs/
│   └── <run_id>/            # 本 run 全部产物（子结构由业务定）
│       └── … 
├── logs/                    # 可选：跨 run 的程序/项目运行摘要
├── archive/                 # 可选：业务归档（大文件可以在这里，不在 Agent 家）
└── （可选）templates/、scripts/  # 若安装脚本从 Skill 复制而来：它们是副本，不是权威源
```

**规则：**

- 一次运行一个 `run_id`；失败重跑新 id 或明确 resume，不覆盖混淆。  
- 子目录名称**按业务**定（不要为了「像标讯」强行 `02_模板`/`03_脚本工具`）。  
- 若采用「prepare 复制 scripts 到 runtime」：SKILL 与 changes 中必须写 **同步清单**（§6）。

**跨 run 摘要（可选）：**  
`logs/项目运行日志_YYYYMMDD.md` 或 `logs/journal.md`——这是 **B 层**程序账，不是 C 层 `runs/*.md`。

---

## 5. C. Agent workspace 标准结构

平台会提供部分身份文件；下列运维目录**首次启用须自建**（不要假设「全自动」）。

```text
workspace/
├── AGENTS.md / SOUL.md / USER.md / MEMORY.md / TOOLS.md / IDENTITY.md / HEARTBEAT.md
├── tasks/                 # 进行中任务、todo、lessons 草稿
├── runs/                  # 运行摘要 md（给人看）← 不是 xlsx 产物树
├── changes/               # 维护日志
├── issues/                # 问题工单
├── memory/                # 每日短记 YYYY-MM-DD.md
├── references/            # 本规范等通用文档
├── skills/                # 已安装 Skill 副本
├── archive/
│   ├── code/              # 废弃脚本
│   └── YYYY-MM/           # 历史 md/说明（不要塞业务大包）
└── tmp/                   # 探针/截图/临时 json，用完即删
```

### 5.1 写入规则

| 类型 | 写入 | 谁写 | 保留 |
|:---|:---|:---|:---|
| 运行摘要 | `runs/YYYY-MM-DD.md`（可加 `_HHMM`） | 定时/全链路跑完 | 长期 |
| 维护日志 | `changes/YYYY-MM-DD.md` | 修问题、改配置、改 cron | 长期 |
| 工单 | `issues/ISSUE-YYYYMMDD-短标题.md` | 发现需跟进缺陷 | 长期 |
| 任务过程 | `tasks/…` | 专项进行中 | 完成后归档 |
| 经验（可复用） | `tasks/lessons.md` → **重要的回写 Skill `lessons/`** | 用户纠正/踩坑 | 长期 |
| 每日记忆 | `memory/YYYY-MM-DD.md` | 有决策/上下文才写（非每句废话） | 长期 |
| 调试 | `tmp/` | 随时 | **7 天可清；任务结束应删** |
| 机器产物 | **Runtime** `runs/<run_id>/` | pipeline | 按业务策略 |

### 5.2 禁止

- ❌ workspace 根目录出现非配置的 `.py` / `.json` / `.png` / 散落 `.txt`  
- ❌ 业务大文件进 `archive/` 当「备份盘」  
- ❌ 密钥写进 runs/changes/memory  
- ❌ 调试脚本写进 Skill `scripts/` 或 Runtime 正式脚本树且不标明临时  

### 5.3 AGENTS.md 应粘贴的摘要

新 Agent 时，把 **§1 原则 + §5.1 表 + §5.2 禁止** 贴进 `AGENTS.md`（短），长文链到 `references/` 本文件。

---

## 6. 代码权威与同步清单（填坑专用）

修 bug / 改规则时，**权威源唯一**（通常是 monorepo 或正式 Skill 源目录）。

在 `changes/YYYY-MM-DD.md` 固定勾选：

```markdown
### 同步
- [ ] 权威源（G 盘 monorepo / 正式 skill 源）
- [ ] 本机 Runtime 脚本副本（若有 prepare 复制）
- [ ] Agent workspace `skills/` 安装副本
- [ ] 其他机器 / 生产盘
- [ ] 是否需要重打包 `.skill` / 部署 zip
```

**坑：** 只勾生产盘、不回写权威源 → 下次打包带旧代码。

---

## 7. 新 Skill 落地清单（复制即用）

创建新 Skill 时：

- [ ] 建 A 层最小结构（§3.1 或 §3.2）  
- [ ] SKILL.md 写清 Runtime / Config 环境变量或路径约定  
- [ ] `references/` 放入**本规范副本**（或写明权威路径）  
- [ ] 需要版本管理则加 改动说明 +（可选）issue-log / lessons  
- [ ] 规划 B 层 runtime 骨架（**按业务子目录**，不抄标讯编号除非同类）  
- [ ] 规划 C 层：确认 workspace 有 runs/changes/issues/tmp/archive  
- [ ] AGENTS.md 贴写入表  
- [ ] 首跑后写一条 `runs/`；若修过则写 `changes/`  

---

## 8. 与「记录标准」分工

| 文档 | 负责 |
|:---|:---|
| **本文件** | 三层模型、目录树、命名消歧、禁止项、同步权威、新 Skill 清单 |
| `skill-recording-standard.md` | 何时写、md 模板字段、runs/changes/issues 正文 |

两处冲突时：**命名与分层以本文件为准；写入时机与模板以 recording 为准。**

---

## 附录 A：标讯自动化特例（仅该业务）

以下**不是**通用默认，仅 `qianlima-bid-daily-workflow`：

```text
Runtime 示例 D:\bid_workflow\
├── 02_模板\
├── 03_脚本工具\          # prepare_runtime 从 Skill scripts 复制 → 副本
├── config\
├── runs\<run_id>\        # 03_body / 06_report / 07_archive_push / 99_logs …
├── 项目运行日志_YYYYMMDD.md
└── 每日标讯筛选结果\
```

- 权威源：正式发布源码包 / monorepo，不是长期只改 `03_脚本工具`。  
- Phase / 复判 / 钉盘字段：只写在标讯的 journal 模板里，**不要**写进通用 § 正文。  
- 薄封装：`02_Skill薄封装_分阶段`，依赖 `QLM_BID_SCRIPTS` + `QLM_BID_RUNTIME` + `QLM_BID_CONFIG`。

---

## 附录 B：历史坑 → 本标准如何挡

| 坑 | 标准挡法 |
|:---|:---|
| 根目录 80+ 散落 md | §5 根只放配置 + archive 按月 |
| 运行账和维护账混在一起 | §2 + §5.1 runs vs changes |
| 全排除修了 D 没回写 G | §6 同步清单 |
| 假通用：`02_模板` 强加给新业务 | §4 通用骨架 + 附录 A 隔离 |
| `runs/` 一词三用 | §2 消歧表 |
| 密钥进包/进日志 | §1.5 + §5.2 |
| 薄封装发给别人缺脚本 | §3.2 一体部署说明 |
| 以为 OpenClaw 会建好 changes | §5「须自建」 |

---

*版本：2026-07-20 · 从标讯生产 Agent 实践提炼为跨 Skill 标准*
