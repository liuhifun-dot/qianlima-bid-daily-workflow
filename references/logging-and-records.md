# 记录体系：记什么、记哪里、何时记、怎么记

本文统一包内四类「记录」的分工，避免 `日志` / `log` / `issue-log` / `lessons` / 运行目录 `runs` 混用。

**硬性禁止：** 账号、密码、完整 Webhook URL/token、Cookie、钉盘私密 ID 等敏感信息写入 Skill 包内任何记录。

---

## 0. 中英别名强制对照表（Agent 必读）

> **字母 A/B/C/D、中文名、英文别名、路径必须一致。**  
> 不要只看文件名里有没有 `log` 三个字母。

| 类别 | 中文名 | 英文别名（写文档/提示词时用） | **唯一路径** | 典型文件名例子 |
|:---:|:---|:---|:---|:---|
| **A** | **日志** | `session-log` / `session_archives` | Skill：`qianlima-bid-daily-workflow/日志/` | `e2e_*/报告_*.md`、`nodes/*.txt`、截图 |
| **B** | **运行产物** | `run-artifacts` / `runtime-output` | **运行目录**：`…/runs/<run_id>/`、`…/output/` | `pipeline_manifest_*.json`、`*pipeline_log*`、`*.jsonl`、checkpoint、xlsx |
| **C** | **问题工单** | `issue-log` | Skill：`issue-log/` | `INDEX.md`、`entries/ISSUE-*.md` |
| **D** | **经验教训** | `lessons` | Skill：`lessons/` | `lessons_log.md` |

**不是记录类别（勿塞进 A–D）：**

| 名称 | 是什么 |
|:---|:---|
| `%TEMP%\qlm_bid_cdp_*.lock` | CDP **单写锁文件**，不是日志 |
| `scripts/` 源码 | 程序，不是记录 |

### Agent 归类伪代码（必须按此填目录）

```text
function classify_and_store(content, meta):
  // meta: {is_auto_run_output, is_human_summary, needs_code_fix, is_long_rule, path_hint}

  if contains_secret(content):
    REFUSE  // 禁止写入 A/B/C/D 任一处的明文密钥

  if meta.is_auto_run_output or path under runs/ or output/:
    STORE → B  // run-artifacts，即使文件名含 log / .jsonl
    return "B"

  if meta.needs_code_fix or meta.is_incident_ticket:
    STORE → C  // issue-log/entries + INDEX
    // 可链接到 B 的 run_id 或 A 的会话路径
    return "C"

  if meta.is_long_rule and meta.from_resolved_issue:
    STORE → D  // lessons/lessons_log.md
    return "D"

  if meta.is_human_summary or meta.is_e2e_report or meta.is_session_archive:
    STORE → A  // 日志/
    return "A"

  // 文件名启发（仅辅助，路径优先）
  if filename matches *pipeline_log* or *live*.jsonl or *checkpoint*:
    STORE → B
  if path contains "issue-log":
    STORE → C
  if path contains "lessons":
    STORE → D
  if path contains "日志" or path contains "session-log":
    STORE → A

  DEFAULT → 若是某次测试结论则 A；若是程序吐出则 B
```

**多 Agent 约定一句话：**

- 中文说「写到日志」= **A** = 目录 `日志/`  
- 英文说 `session-log` = **同一 A**  
- 英文文件名 `foo_log.txt` 若在 `runs/` 里 = **B**，不是 A  
- `issue-log` = **C**（英文目录名，不要改成「日志」）

---

## 1. 总览一览表

| 类型 | 目录（Skill 包内） | 运行时等价位置 | 记什么 | 何时记 | 谁写 |
|:---|:---|:---|:---|:---|:---|
| **A. 运行会话日志** | `日志/` | 可选同步；主产物仍在 runtime | 某次测试/排障的会话：命令、节点输出、报告、截图 | 手工 E2E、排障会话、验收 | 人/Agent |
| **B. 程序运行产物** | （一般不进 Skill） | `runtime/runs/<run_id>/`、`output/` | pipeline 自动产生的 manifest、xlsx、阶段 JSON、脚本 live log | 每次 `run_daily_pipeline` / 子脚本 | 程序 |
| **C. 问题工单** | `issue-log/` | 不复制进 runtime | 要跟进的问题：节点、现象、解法、状态 | 失败需改代码/SOP、UI 变更、用户要求记录 | 人/Agent |
| **D. 经验教训** | `lessons/` | 不复制进 runtime | 从已解决工单提炼的**长期规则** | issue `resolved` 后可选提炼 | 人/Agent |

**原则：**

- **B 是机器事实**（某次 run 发生了什么）  
- **A 是人为整理的会话档案**（方便打开看）  
- **C 是待办工单**（后面重点改什么）  
- **D 是沉淀规则**（下次别再犯）

不要把 B 整包拷进 Skill 当「安装包内容」；Skill 保持可发布、可校验。

---

## 2. A. `日志/` — 会话级测试/排障档案

### 2.1 是什么

中文目录名 **`日志`**（不是 `log`）。  
用于：**一次测试计划、一次 E2E、一轮补丁验证** 的人工可读归档。

### 2.2 目录建议

```text
日志/
  README.md                          # 本层说明
  <会话名>/                          # 例：e2e_full_20260714_fullrun3
    00_session.json 或 README.md     # 会话元数据：目的、时间、操作者
    nodes/                           # 分节点原始输出（可选）
    screenshots/                     # 截图（可选）
    报告_*.md                        # 结论报告
  <主题>_YYYYMMDD.md                 # 不绑会话的分析/计划也可放顶层
```

**会话名建议：** `e2e_YYYYMMDD_简述`、`patch_YYYYMMDD_主题`、`smoke_YYYYMMDD`。

### 2.3 应保存的内容

| 内容 | 是否建议 | 说明 |
|:---|:---:|:---|
| 目的与范围 | 是 | 测什么、不测什么 |
| 命令行（可脱敏） | 是 | 无 token |
| run_id、exit code | 是 | 可链到 runtime |
| 失败 Phase / 报错摘要 | 是 | 可贴关键几行，勿整文件密钥 |
| 截图 | 失败时强烈建议 | 导出弹窗、记录行、登录门 |
| 结论与下一步 | 是 | pass/fail + 是否开 issue |
| 完整 pipeline 几十 MB 日志 | 可选 | 大文件优先留在 runtime，Skill 里只留摘要+路径 |

### 2.4 何时写

- 做完整 E2E / 候选包验收  
- 用户要求「写测试报告」  
- 排障超过一次尝试、需要留档给后续  

### 2.5 何时不写

- 单次 `--help`、纯语法检查  
- 已自动落在 runtime 且无人工结论时，可不重复抄进 `日志/`  

---

## 3. B. 运行目录 `runs/` / `output/` — 程序自动日志

### 3.1 是什么

由 `prepare_runtime` 生成的**独立运行目录**内，例如：

```text
_test_runtime_e2e_full/
  runs/<run_id>/
    pipeline_manifest_*.json
    02_screening … 07_archive_push/
    99_logs/
    06_report/*.xlsx
  output/
    latest_qianlima_export_path.txt
    qianlima_mainline_live_*.jsonl
    qianlima_phase1_checkpoint_*.json
```

### 3.2 记什么

- 脚本 print / JSONL live log  
- checkpoint、指针、业务 JSON、日报、钉钉发送结果（结果 JSON 勿把 token 再抄进 Skill）  

### 3.3 何时记

- **每次程序跑就自动产生**，无需人工「决定记不记」  
- Agent 排障时应**先读这里**，再决定是否摘到 `日志/` 或 `issue-log/`  

### 3.4 与 Skill 的关系

- **默认不**把整个 `runs/` 提交进 Skill 发布包  
- 若要在 Skill `日志/` 留证据：复制**摘要报告 + 少量截图 + run_id 路径说明**即可  

---

## 4. C. `issue-log/` — 问题工单（重点改）

详见 `issue-log/README.md`。

### 4.1 记什么

| 字段 | 必填 |
|:---|:---:|
| 记录时间 | 是 |
| 节点（Phase0/1/2A…） | 是 |
| 问题现象 | 是 |
| 解法或未解+下一步 | 是 |
| 状态 open/mitigated/resolved/wontfix | 是 |
| 优先级 P0–P2 | 建议 |
| 链到 `日志/` 或 runtime 路径 | 建议 |
| 截图路径 | 失败 UI 建议 |

### 4.2 何时记

- 全流/阶段失败且**需要后续改代码或 SOP**  
- 网站 UI/文案变更  
- 用户说「记一下这个问题」  
- 有明确绕过但根因未清（`mitigated`）  

### 4.3 怎么记

1. 复制 `issue-log/TEMPLATE.md` → `issue-log/entries/ISSUE-YYYYMMDD-slug.md`  
2. 更新 `issue-log/INDEX.md` 顶行  
3. UI 类修复流程见 `issue-log/SITE_UI_CHANGE_PLAYBOOK.md`  

### 4.4 不记什么

- 密钥  
- 一次性手误且无复现价值  

---

## 5. D. `lessons/` — 经验教训（长期规则）

### 5.1 是什么

从 **已 resolved 的 issue** 或多次踩坑中提炼的**通用规则**，给以后的人/Agent 直接遵守。  
不是某次 run 的流水账。

### 5.2 以前为什么是空的

历史上只放了 `lessons_template.md`，没有强制「resolved 后提炼」的流程，所以一直空。

### 5.3 何时写入

- 某 issue 状态变为 `resolved`，且规则**对以后仍有用**  
- 同一类问题出现 ≥2 次  

### 5.4 怎么写

1. 打开 `lessons/lessons_log.md`（按日期追加）  
2. 用模板结构：问题 → 原因 → 规则（可执行的句子）  
3. 可选：链回 `issue-log/entries/ISSUE-...`  
4. **不要**把整段 pipeline 日志贴进 lessons  

### 5.5 与 issue-log 的分工

| | issue-log | lessons |
|:---|:---|:---|
| 粒度 | 单次/单个故障 | 跨故障的规则 |
| 状态 | open/resolved… | 无状态，持续有效 |
| 例子 | 「2026-07-14 额度 0 卡死」 | 「额度弹窗解析到 0 必须 fail-fast」 |

---

## 6. 命名对照（避免「log」混乱）

| 你可能看到的叫法 | 实际指什么 | 应归入 |
|:---|:---|:---|
| 中文「日志」文件夹 | Skill 包 `日志/` | A 会话档案 |
| 英文 log / live jsonl | 脚本输出文件 | B 程序产物 |
| pipeline_log.txt | 某次 E2E 节点输出 | A 或 B 的拷贝 |
| issue / 问题记录 | `issue-log/` | C |
| lessons / 教学 / 经验 | `lessons/` | D |
| troubleshooting.md | 官方排障手册 | references（可链 issue/lessons） |

**发布与文档里优先用中文「日志」指 A；用「运行产物/runs」指 B；不要用裸词 log。**

---

## 7. 推荐工作流（一次失败怎么记）

```text
1. 程序失败 → 先看 runtime runs/<run_id>/ 与 output/（B）
2. 需要给人看的结论 → 写 日志/<会话>/报告.md，附关键截图（A）
3. 需要以后改代码 → 开 issue-log 工单，链到 A/B 路径（C）
4. 修好并验证 → issue → resolved；若成规则 → 写入 lessons/（D）
5. 网站改版类 → 同时遵循 SITE_UI_CHANGE_PLAYBOOK.md
```

---

## 8. 清理与副本策略

| 目录 | 进正式发布包？ | 清洗副本时 |
|:---|:---:|:---|
| `scripts/` `assets/` `references/` `SKILL.md` | 是 | 保留 |
| `issue-log/`（无密钥） | 建议保留 | 保留结构+规则；样例可保留或精简 |
| `lessons/` | 是 | 保留模板+log |
| `日志/` 下大体量 e2e 原始输出 | 否（易膨胀） | **删除会话明细**，只留 README |
| `__pycache__` / 临时 runner | 否 | 删除 |
| runtime 目录 | 不在 Skill 内 | 不拷进 Skill 包 |

---

## 9. 检查清单（Agent 自检）

- [ ] 敏感信息未写入 A/C/D  
- [ ] 会话结论在 `日志/` 或用户指定处，而非只在聊天里  
- [ ] 待修问题在 `issue-log/INDEX.md` 有行  
- [ ] 长期规则不堆在 issue 里重复贴日志，而在 `lessons/`  
- [ ] 未把 runtime 整目录塞进 Skill  
