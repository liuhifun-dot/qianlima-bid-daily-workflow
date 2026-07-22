# 给其他 Agent：四类记录目录落地说明（v01）

> **文件名（请记住）：** `给其他Agent_四类记录目录落地说明_v01.md`  
> **所在位置（发布包 Skill 根目录）：**  
> `G:\Codex Project\标讯自动化\01_正式发布\qianlima-bid-daily-workflow_20260706_v07-release01_source\qianlima-bid-daily-workflow\给其他Agent_四类记录目录落地说明_v01.md`  
>  
> **完整规范正文：** 同目录 `references/logging-and-records.md`（§0 中英对照 + 伪代码）  
> **给人看的改动总账：** 同目录 `改动说明.md`  
>  
> **本文用途：** 你方定时任务 / 运行目录（如 `D:\bid_workflow`）按同一套 **A/B/C/D** 对齐。  
> **不要**把运行产物塞进 Skill 安装包；**不要**写密钥。

---

## 1. 为什么要分四类

| 乱叫 | 正确归类 |
|:---|:---|
| 随便叫 log | 可能是 A 会话、也可能是 B 程序输出 |
| 中文「日志」和英文 `issue-log` 混用 | 两个完全不同的目录 |
| 把 pipeline 整包拷进 Skill | 包膨胀、哈希炸、发布不可控 |

**硬规则：按「来源 + 路径」归类，不按文件名是否含 log。**

---

## 2. 强制对照表（中英必须同时对上）

| 类别 | 中文名 | 英文别名（写配置/提示词用） | **固定路径** | 放什么 |
|:---:|:---|:---|:---|:---|
| **A** | **日志** | `session-log` / `session_archives` | Skill 包内：`…/qianlima-bid-daily-workflow/日志/` **或** 你方镜像的 `session-log/`（若做英文别名目录，内容必须与 A 同一类） | 某次定时/E2E **人工整理**的结论、节点摘要、截图索引、验收报告 |
| **B** | **运行产物** | `run-artifacts` / `runtime-output` | **运行目录**：`D:\bid_workflow\runs\<run_id>\`、`D:\bid_workflow\output\`（或你方等价路径） | pipeline **自动**生成的 manifest、xlsx、jsonl、checkpoint、`*pipeline_log*`、阶段 JSON |
| **C** | **问题工单** | `issue-log` | Skill：`issue-log/`（或你方 `issue-log/` 镜像） | 待修：时间、节点、问题、解法、状态；链到 B 的 run_id |
| **D** | **经验教训** | `lessons` | Skill：`lessons/` | 长期规则，写 `lessons_log.md`；从 resolved 工单提炼 |

**不是 A–D：**

- `%TEMP%\qlm_bid_cdp_*.lock` → CDP **锁**，不是日志  
- `scripts/` → 源码  

**文件名含 `log` 但路径在 `runs/` / `output/` → 仍是 B，不是 A。**

---

## 3. 你方（定时任务 Agent）建议目录怎么摆

### 3.1 运行目录（生产，例：`D:\bid_workflow`）— 以 B 为主

```text
D:\bid_workflow\                    # 运行目录（prepare_runtime 产物，不是 Skill 安装包）
  03_脚本工具\                      # 脚本
  runs\<run_id>\                    # ★ B：每次正式跑
    pipeline_manifest_*.json
    03_body\ 04_attachment\ …
    99_logs\                        # ★ B：分段日志建议写这里
  output\                           # ★ B：导出 xlsx、指针、live jsonl
  logs\ 或 运行会话\                # 可选：仅放「指向 runs 的索引」，不要复制整盘 runs
```

### 3.2 Skill / 知识侧 — A / C / D

任选一种：

**方案甲（推荐）：直接引用发布包 Skill 目录**

- A：`…发布包…/qianlima-bid-daily-workflow/日志/`  
- C：`…/issue-log/`  
- D：`…/lessons/`  

**方案乙：在 workspace 镜像三份空壳**

```text
你的_workspace/
  session-log/     # = A（英文名；与中文「日志」同义，只放会话结论）
  issue-log/       # = C
  lessons/         # = D
```

若用方案乙，必须在 `AGENTS.md` 或定时任务说明写死：

```text
session-log  ≡ A ≡ 日志
run-artifacts ≡ B ≡ D:\bid_workflow\runs + output
issue-log    ≡ C
lessons      ≡ D
```

---

## 4. 何时记、记什么（操作清单）

| 时机 | 写哪 | 写什么 |
|:---|:---:|:---|
| 每次定时跑完/失败 | **B** | 自动已有；确认 `runs/<run_id>` 在；可选在 `99_logs` 补分段耗时 |
| 需要给人看结论 / 验收 | **A** | 会话目录 + 一页报告：run_id、失败 Phase、结论、截图路径 |
| 要改代码才能好 | **C** | 复制 `issue-log/TEMPLATE.md` → `entries/ISSUE-日期-slug.md`，更新 INDEX |
| 问题已修且成规则 | **D** | 在 `lessons_log.md` 顶部追加「必须/禁止」句子，链回 ISSUE |

**禁止写入任何类：** 账号、密码、完整 webhook token、Cookie。

---

## 5. Agent 归类伪代码（可直接贴进你的 AGENTS.md）

```text
function store(content, meta):
  if secret(content): refuse

  if meta.from_pipeline_auto or path in {runs, output}:
      → B (run-artifacts)

  if meta.needs_code_fix or meta.is_ticket:
      → C (issue-log): time + phase + problem + fix + status
      link run_id from B

  if meta.long_term_rule and resolved:
      → D (lessons_log.md)

  if meta.human_session_summary or e2e_report:
      → A (日志/ 或 session-log/)

  if filename has "log" and path under runs/output:
      → B   // 不要误判成 A
```

---

## 6. 发布包里已经做好、你可直接对照的文件

| 文件 | 作用 |
|:---|:---|
| `references/logging-and-records.md` | **总规范（含 §0 中英表 + 伪代码）** |
| `日志/README.md` | A 类说明 |
| `issue-log/README.md` + `TEMPLATE.md` + `INDEX.md` | C 类 |
| `lessons/README.md` + `lessons_log.md` | D 类 |
| `改动说明.md` | 维护 Agent 每次改代码的人读总账 |
| `issue-log/SITE_UI_CHANGE_PLAYBOOK.md` | 网站改版修复流程（非自动改码） |

**你需要改动的方法（你方侧）：**

1. 定时任务文档写死 A/B/C/D 路径映射（上表）。  
2. 失败时：从 B 的 `runs/<run_id>` 摘 run_id → 开 C 工单 → 需要给人看再写 A。  
3. 不要把 `D:\bid_workflow\runs` 整树拷进 Skill 的 `日志/`。  
4. 若你方已有 `tasks/lessons.md`、`memory/*.md`：可继续作工作笔记，但**待修问题请同步一份到 C（issue-log）**，避免只在 memory 里。  

---

## 7. 与「附件卡死工单」的关系（便于你同步）

标神工单 `ISSUE-20260714-attach-download-watchdog`：

- 归类应为 **C**（issue-log），证据链在 **B**（`D:\bid_workflow\runs\20260714_110303`）。  
- 发布包维护侧：**OCR 进度心跳已部分落地**；**分段日志 / 每附件预算 / requests 600→90 / SPA 看门狗** 仍建议按该工单补全（见维护 Agent 对照结论）。

---

## 8. 一句话交给对方 Agent

> 采用发布包 `logging-and-records.md` 的 A/B/C/D：  
> **B=运行目录 runs/output；A=会话结论 日志/ 或 session-log；C=issue-log；D=lessons。**  
> 按来源归类，文件名含 log 不代表是 A。密钥禁止写入。
