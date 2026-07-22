# 大工作流拆成多个 Skill：拆法设计（2026-07-16）

> **目的：** 在不大改现有脚本的前提下，把「千里马日报」拆成可单独跑、可联动的小 Skill + 一个总控。  
> **前提：** 当前单体仍是 `qianlima-bid-daily-workflow`（`run_daily_pipeline`）。本文是**拆分蓝图**，不是已实现的新包。  
> **原则：** 用**文件契约**（指针 / JSON / xlsx）串联；禁止聊天记忆猜路径；密钥仍在 Skill 外。

---

## 1. 建议拆成几个？

你口头列了 4 步业务 + 1 个统筹。两种打包方式：

### 方案 A（推荐）：**4 个子 Skill + 1 个总控 = 5 个包**

| # | Skill 名（建议） | 对应现网 Phase | 人话职责 |
|:---|:---|:---|:---|
| **S1** | `qianlima-bid-export` | 0 部分 + **1** | 登录/CDP + 下载千里马导出 Excel |
| **S2** | `qianlima-bid-screen-review` | **2A→2B→2C→2D** | 筛选、正文附件核对、业务复判；**产出 md 简报草稿** |
| **S3** | `qianlima-bid-report-excel` | **3** | 复判结果 → 正式 Excel 日报（模板契约） |
| **S4** | `qianlima-bid-archive-push` | **4** | 本地/共享盘归档 + 钉盘 + 钉钉 |
| **O** | `qianlima-bid-daily-orchestrator` | 总入口 | 按序调 S1→S4，或从断点跳过已有产物 |

对应你说的：下载 / 筛选核对+md / 转 Excel / 存档发钉钉 + **大工作流统筹**。

### 方案 B（严格 4 个包）：**3 个子 + 1 个总控**

| # | Skill | 合并方式 |
|:---|:---|:---|
| S1 | 下载 | 同方案 A |
| S2 | 筛选核对 + **Excel** | 2A～3 打通（md 草稿 + xlsx 都在这步出） |
| S3 | 存档发钉钉 | 同方案 A 的 S4 |
| O | 统筹 | 调 S1→S2→S3 |

**默认按方案 A 写下文**（边界最清晰；Excel 与「发钉钉」解耦，方便你只改表不发群）。

---

## 2. 总览关系图

```text
                    ┌─────────────────────────────────────┐
                    │  O  统筹 Skill（可单独当定时任务）     │
                    │  读指针/契约 → 调子 Skill 或调脚本     │
                    └───────────────┬─────────────────────┘
           ┌────────────────────────┼────────────────────────┐
           ▼                        ▼                        ▼
    ┌────────────┐          ┌──────────────┐          ┌────────────┐
    │ S1 下载     │  raw.xlsx │ S2 筛选核对   │ business │ S3 Excel   │
    │ CDP+导出   │ ───────► │ +md 简报草稿  │ ───────► │ 正式日报    │
    └────────────┘          └──────────────┘          └─────┬──────┘
         可单独                  可单独（自备 xlsx）            │ report.xlsx
                                                             ▼
                                                      ┌────────────┐
                                                      │ S4 存档钉钉 │
                                                      │ 归档/盘/群  │
                                                      └────────────┘
                                                           可单独（自备 xlsx+json）
```

**共享运行目录（所有 Skill 约定同一 runtime，不写 Skill 安装目录）：**

```text
D:\bid_workflow\   或  测试 RT
  output\                          # 指针与导出
    latest_qianlima_export_path.txt
    latest_screening_result_path.txt
    latest_business_review_path.txt
    v2_4\...
  runs\<run_id>\                   # 本趟产物
    02_screening\ 03_body\ 04_attachment\ 05_rejudge\
    06_report\ 07_archive_push\ 99_logs\
  02_模板\                         # Excel 样板
  03_脚本工具\                     # 或各 Skill 自带 scripts 但写到同一 runtime
  filter_rules\rules_current.yaml
```

---

## 3. 每个 Skill：做什么、用哪些工具、输入输出

### S1 · 下载标讯（`qianlima-bid-export`）

| 项 | 内容 |
|:---|:---|
| **何时用** | 要从千里马拉「昨天～今天」新导出；或定时任务第一段 |
| **要不要浏览器** | **要**（CDP 9222） |
| **脚本** | `ensure_browser_channel_*`、`qianlima_auto_login_*`、`cdp_run_lock_*`、`bid_export_auto_v1.py` |
| **配置** | 本机敏感配置（账号密码）、订阅 URL、CDP port |
| **文档** | `references/phase1-qianlima-export.md`；登录刷新/锁行教训见 lessons |
| **输入** | `--start-date` `--end-date`（可默认昨今）、`--cdp-port`、`--config`、可选 `--resume-context` |
| **输出（契约）** | ① 导出 xlsx 文件 ② `output/latest_qianlima_export_path.txt` ③ `latest_qianlima_export_source.json` ④ 可选 checkpoint |
| **成功标准** | 目标行锁定 + 下载 + 表头/行数校验通过；指针写出 |
| **失败** | 登录/额度空刷/目标行丢失 → 失败告警（可选）；不进入 S2 |
| **单独跑？** | **能。** 只下载不筛 |
| **联动** | O 在成功后把 `raw_export` 路径传给 S2 |

---

### S2 · 筛选 + 核对 + md 简报（`qianlima-bid-screen-review`）

| 项 | 内容 |
|:---|:---|
| **何时用** | 已有导出 xlsx（自己下载的或 S1 产出）；要筛业务 + 读正文附件 + 复判 |
| **要不要浏览器** | **2B/2C 要** CDP；2A/2D 不要 |
| **脚本** | `bid_screening_*`、`qianlima_cdp_body_attachment_reader_*`、`validate_cdp_body_*`、`bid_business_rejudge_*`、`bid_business_rules_*`、`validate_phase2_rejudge_*`；tpk-ocr 子树 |
| **规则/资产** | `filter_rules/rules_current.yaml` 或 `assets/rules_current.yaml`；人话手册可只读 |
| **文档** | phase2 规则、`筛选规则_人话版操作手册` |
| **输入** | **必填** `--raw-export`（或读 latest 指针）；日期；`--cdp-port`；`--config` |
| **输出（契约）** | ① 筛选 JSON + latest_screening 指针 ② VIP/附件 JSON ③ **业务复判 JSON** + latest_business 指针 ④ **md 简报草稿**（推荐/复核/排除摘要，可放 `runs/.../05_rejudge/` 或 `07_archive_push/钉钉消息草稿_*.md` 的「仅草稿」模式） |
| **成功标准** | 复判 JSON 合法；校验器通过（含合法全排除）；md 可人工打开 |
| **失败** | 系统 need_login/captcha → 停；单条正文失败 → needs_review 不整批死 |
| **单独跑？** | **能。** 例如你手工从网站下了 xlsx，只跑本 Skill |
| **联动** | 吃 S1 的 raw；吐 business JSON 给 S3 |

**说明：** 今日正式包里「钉钉 md 草稿」是在 Phase3/4 脚本里生成的；拆 Skill 后建议 S2 **先出业务 md 摘要**（给人核对），S4 再出带钉盘链接的最终消息。

---

### S3 · 转成 Excel 日报（`qianlima-bid-report-excel`）

| 项 | 内容 |
|:---|:---|
| **何时用** | 已有业务复判 JSON；只要正式表、不发群 |
| **要不要浏览器** | **不要** |
| **脚本** | `report_builder_*`、`validate_excel_template_contract_*`；（可从 `gen_report_archive_push_*` 抽出「只建表」入口，或 `--excel-only` 开关） |
| **资产** | `assets/照明招标线索日报_格式样板_*.xlsx` → runtime `02_模板` |
| **文档** | `references/phase3-excel-contract.md` |
| **输入** | **必填** `--business-json`；建议 `--raw-export`、`--vip-json`、`--screening-json` 做回填与「全部标讯」 |
| **输出** | `runs/.../06_report/照明招标线索日报_*.xlsx` + 校验 JSON |
| **成功标准** | Excel 契约校验 ok；推荐区不含 needs_review 混入 |
| **单独跑？** | **能。** 改完复判结果重出表，不必再爬网 |
| **联动** | 吃 S2；xlsx 给 S4 |

---

### S4 · 存档 + 钉盘 + 钉钉（`qianlima-bid-archive-push`）

| 项 | 内容 |
|:---|:---|
| **何时用** | 已有通过校验的日报 xlsx（及复判 JSON）；要归档并发群 |
| **要不要浏览器** | **不要**（要 dws CLI + webhook） |
| **脚本** | `gen_report_archive_push_*` 的归档/上传/发送段；或独立 `archive_push_only` |
| **配置** | `local_archive_dir`、`share_archive_dir`、钉盘 space/folder、主备 webhook；DWS 已登录 |
| **文档** | `references/phase4-archive-dingtalk.md` |
| **输入** | **必填** 日报 xlsx + business-json；归档路径 |
| **输出** | 本地/共享盘文件夹、钉盘 doc_url、钉钉发送结果 JSON、最终 md 消息（含文档链接） |
| **成功标准** | `full_run_success=true`（归档 ok + 钉盘有 url + 主 webhook ok） |
| **单独跑？** | **能。** 表已人工改完，只发一版；或 dry-run 只归档不发 |
| **联动** | 吃 S3；定时任务最后一段 |

**门禁顺序（不可跳）：** 本地归档 → 共享盘 → 钉盘 doc_url → 钉钉。缺 doc_url 不发正常日报。

---

### O · 统筹（`qianlima-bid-daily-orchestrator`）

| 项 | 内容 |
|:---|:---|
| **何时用** | 每日定时「从 0 到钉钉」；或从断点续跑 |
| **本质** | 现有 `run_daily_pipeline_*.py` 升格为「只编排、少业务」 |
| **行为** | 1）建 run_id / 锁 CDP  2）按 `start-phase`～`end-phase` 调 S1～S4（或内嵌调脚本） 3）读写指针与 pipeline_manifest  4）失败告警 |
| **映射现网** | `--start-phase 1|2a|2b|2c|2d|34` 已接近 O 的能力；拆 Skill 后 phase 可改成 `export|screen|excel|push` |
| **单独跑？** | **能。** 这就是今天的「大工作流」 |
| **不单独做业务** | 不自己点网页、不自己写筛选规则 |

---

## 4. 联动契约（最重要）

子 Skill **不互相 import 对方 Skill**，只约定：

### 4.1 指针文件（推荐，UTF-8）

| 指针 | 谁写 | 谁读 |
|:---|:---|:---|
| `output/latest_qianlima_export_path.txt` | S1 | S2、O、S3 |
| `output/latest_screening_result_path.txt` | S2 | O、调试 |
| `output/latest_business_review_path.txt` | S2 | S3、S4、O |
| （可选）`output/latest_report_xlsx_path.txt` | S3 | S4、O |

### 4.2 显式参数（可单独跑时必填）

| 场景 | 你要传 |
|:---|:---|
| 只跑 S2 | `--raw-export "…\千里马信息导出_xx.xlsx"` |
| 只跑 S3 | `--business-json "…\业务复判结果_xx.json"` + 建议 raw/vip |
| 只跑 S4 | `--report-xlsx "…\照明招标线索日报_xx.xlsx"` + business-json |
| O 断点从筛选起 | 跳过 S1，要求 raw 指针或 `--raw-export` 已存在 |
| O 只发钉钉 | 跳过 S1～S3，要求 report + business |

### 4.3 run_id / 目录

- O 生成 `run_id`，传给各子 Skill 的 `--run-id` / `--run-dir`，保证一轮产物在同一 `runs\<run_id>\`。  
- 单独跑子 Skill 时自己生成 `run_id=manual_<阶段>_<时间戳>`。

### 4.4 软依赖 vs 硬依赖

| 从 → 到 | 依赖类型 | 说明 |
|:---|:---|:---|
| S1 → S2 | **硬** | 没有合法 raw xlsx 不能筛 |
| S2 → S3 | **硬** | 没有 business json 不能出正式表 |
| S3 → S4 | **硬** | 没有校验通过的 xlsx 不能正式发 |
| S2 → S4 | 软 | 可只发 md（不推荐作正式通道） |
| S1 → S3 | 软 | S3 用 raw 填「全部标讯」页，无 raw 可降级但仍要有 business |

---

## 5. 「能不能单独使用」一览

| Skill | 单独 | 典型场景 |
|:---|:---:|:---|
| S1 下载 | ✅ | 只要原始包，晚上再筛 |
| S2 筛选核对 | ✅ | 你已手工下载 Excel，只跑筛选+正文+md |
| S3 Excel | ✅ | 复判 JSON 改完，重出表 |
| S4 存档钉钉 | ✅ | 表 OK 了只归档/发群；或 dry-run |
| O 统筹 | ✅ | 定时任务一条龙 |

| 组合 | 场景 |
|:---|:---|
| S1+S2 | 下完立刻筛，不出表不发钉钉 |
| S2+S3 | 有 raw，出到 Excel 停 |
| S3+S4 | 表好了正式交付 |
| O 全开 | 生产定时任务（≈ 今天 12 分钟那条） |

---

## 6. 工具 / 文件放在哪（目录建议）

### 6.1 不拆物理仓库时（过渡，推荐先这样）

仍用一个 monorepo / 一个 runtime，**用入口脚本伪装多 Skill**：

```text
scripts/
  skill_export_main.py      → 只调 Phase1
  skill_screen_main.py      → 2a..2d + 写 md
  skill_excel_main.py       → 只 report+校验
  skill_push_main.py        → 只 archive+ding
  run_daily_pipeline_*.py   → O（已有，参数化即可）
```

每个 Skill 的 `SKILL.md` 只声明**自己能调的脚本子集**和输入输出，避免 Agent 乱调。

### 6.2 真拆成 4～5 个 Skill 包时

```text
skills/
  qianlima-bid-export/
    SKILL.md
    scripts/   # export + login + ensure + lock
    references/phase1-*.md
  qianlima-bid-screen-review/
    SKILL.md
    scripts/   # screening + cdp body + rejudge + rules + ocr
    assets/rules_current.yaml   # 或 runtime 共享
    references/phase2-*.md + 人话手册
  qianlima-bid-report-excel/
    SKILL.md
    scripts/report_builder + excel validate
    assets/模板.xlsx
  qianlima-bid-archive-push/
    SKILL.md
    scripts/archive_push 段
    references/phase4-*.md
  qianlima-bid-daily-orchestrator/
    SKILL.md
    scripts/run_daily_pipeline 或薄封装
    references/ 只写编排与契约
```

**共享且勿复制多份的：**

- 本机敏感配置（Skill 外一份）  
- runtime 的 `output/` 指针  
- （可选）`rules_current.yaml` 以 runtime 或 screen Skill 为唯一权威  

**必须复制/随包的：** 各 Skill 自己的入口脚本与本阶段 references。

---

## 7. 与现网 Phase 对照（迁移成本）

| 现网 | 新 Skill |
|:---|:---|
| pipeline `--start-phase 1 --end-phase 1` | S1 |
| `2a`～`2d` | S2 |
| `34` 里建表部分 | S3 |
| `34` 里归档发送 | S4 |
| 全默认 1→34 | O |

**最小改造路径（不必一次拆 5 个 zip）：**

1. 保持一个代码仓、一个 runtime。  
2. 给 `run_daily_pipeline` 增加别名 phase：`export | screen | excel | push`。  
3. 写 4 份薄 `SKILL.md` 只暴露对应 phase。  
4. O 的 SKILL 继续指向总入口。  
5. 稳定后再物理拆包。

---

## 8. 边界与禁止项（拆完也不能破）

1. 子 Skill **不得**写密钥进产物。  
2. S4 **不得**在无钉盘 doc_url 时发「假装成功」的日报。  
3. S2 **不得**在证据不足时 keep。  
4. S1 **不得**用历史「已生成」行冒充本次导出（除非显式 fallback 开关）。  
5. 单独跑 S2 时必须显式 raw 路径（防 PowerShell 编码丢参数——用 Python 传参）。  
6. 多 Skill 同机同时跑 **同一 CDP 9222** 必须抢锁；O 串行调用最安全。

---

## 9. 你怎么选「4 个」还是「5 个」

| 你的诉求 | 建议 |
|:---|:---|
| 要单独「只出 Excel 不发钉钉」经常用 | **方案 A（4 子 + O）** |
| 包越少越好，Excel 总是和筛选一起 | **方案 B（3 子 + O）** |
| 定时任务一条龙 | 只装 **O**，或 O 依赖其余 Skill |
| 自己下了 xlsx 只筛 | 只装/只调 **S2** |

---

## 10. 示例：三种调用方式（概念命令）

```text
# ① 只下载
[S1] bid_export --cdp-port 9222 --config <敏感配置>

# ② 已有 xlsx，只筛选核对
[S2] screen_review --raw-export "G:\...\千里马信息导出_07-16.xlsx" --cdp-port 9222 --config ...

# ③ 统筹全天（等同今日定时）
[O]  pipeline --start-phase export --end-phase push --config ... 
     （或现网 --start-phase 1 --end-phase 34）
```

---

## 11. 小结

| 问题 | 答案 |
|:---|:---|
| 怎么拆？ | **下载 / 筛选核对(+md) / Excel / 存档钉钉** + **统筹** |
| 工具怎么放？ | 按阶段进各 Skill 的 `scripts/`；**指针与 runs 永远在 runtime** |
| 联动靠什么？ | latest 指针 + `--raw-export` / `--business-json` / report 路径 |
| 能单独用吗？ | **四个子 Skill 都能单独**；统筹也能单独当大工作流 |
| 和现在关系？ | 现有 pipeline 的 start-phase 已是半套统筹；拆 Skill 主要是**边界与 SKILL 文档**，脚本可渐进 |

若你确认方案 A 或 B，下一步可以是：只改文档入口（4 份 SKILL 薄封装）而不动业务代码，或直接给 `run_daily_pipeline` 加 `export|screen|excel|push` 别名。
