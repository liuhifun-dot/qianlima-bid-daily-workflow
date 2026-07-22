# 问题记录库（issue-log）

## 为什么叫 issue-log，不叫 log / list？

| 名字 | 评价 |
|:---|:---|
| **log** | 易与运行日志 `日志/`、pipeline stdout 混淆；太泛 |
| **list** | 像待办清单，缺「时间/节点/解法」语义 |
| **lessons/** | 包内已有，偏「沉淀成通用规则」；适合结案后提炼 |
| **issue-log（推荐）** | 明确是**问题工单式记录**，服务「后面重点改」；英文目录名兼容工具与 manifest |

**约定（完整版见 `references/logging-and-records.md`）：**

- **A 会话档案** → Skill 包 `日志/`（E2E/排障结论与截图索引）
- **B 程序自动产物** → 运行目录 `runs/`、`output/`（不进发布包）
- **C 问题工单** → **`issue-log/`**（本目录）
- **D 长期规则** → `lessons/lessons_log.md`（resolved 后提炼）

---

## 目的

1. 把「哪个节点、什么问题、怎么解的」留下可检索记录。  
2. 方便后续按 **open / 高优先级** 集中改代码。  
3. Agent 排障时先搜本目录，避免重复踩坑。  
4. **禁止**写入账号、密码、完整 webhook token、Cookie。

---

## 规则（Agent / 人工必须遵守）

1. **何时写**  
   - 全流/单阶段失败且需要后续修代码或改 SOP  
   - 站点 UI/文案变化导致点击/导出失败  
   - 额度、CDP、钉盘、钉钉等环境问题有明确解法或待办  
   - 用户明确说「记一下这个问题」

2. **何时不写**  
   - 一次性笔误、未复现的偶发且无信息  
   - 纯聊天讨论未落地  
   - 敏感配置内容本身

3. **怎么写**  
   - 新问题：复制 `TEMPLATE.md` → `entries/ISSUE-YYYYMMDD-简短英文或拼音.md`  
   - 更新 `INDEX.md` 增加一行  
   - 字段至少包含：时间、节点(phase)、问题、解法/未解、状态、优先级  
   - 能关联则写：run_id、日志路径、截图路径（截图放 `日志/` 或本条附件目录，勿塞密钥）

4. **状态**  
   - `open`：待修  
   - `mitigated`：有绕过/软处理，根因未清  
   - `resolved`：代码或 SOP 已修，并至少验证一次  
   - `wontfix`：明确不做（写原因）

5. **与代码修改的关系**  
   - 改代码前：issue 里写清**目标**（见 `SITE_UI_CHANGE_PLAYBOOK.md`）  
   - 改完后：更新「解法」+ 验证证据 + 状态  
   - 需要作为发布主线时：走 release 流程，**不在 issue 里偷偷替换正式入口**

---

## 目录结构

```text
issue-log/
  README.md                 # 本说明 + 规则
  INDEX.md                  # 总表（优先维护）
  TEMPLATE.md               # 单条模板
  SITE_UI_CHANGE_PLAYBOOK.md # 网站改版时的应对方法（流程，非自动改码）
  entries/                  # 单条问题文件
    ISSUE-YYYYMMDD-slug.md
```

---

## 快速新建

1. 复制 `TEMPLATE.md` 为 `entries/ISSUE-20260714-quota-zero.md`  
2. 填字段  
3. 在 `INDEX.md` 顶部表格追加一行  
4. 若已修：状态改 `resolved`，并链到脚本/PR/报告路径  
