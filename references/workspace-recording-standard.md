# 工作区记录标准（通用 · 何时写 / 模板）

> **权威副本：** `C:\Users\user\.agents\standards\skill-recording-standard.md`  
> **配套目录标准：** `skill-workspace-directory-standard.md`（三层模型、命名消歧）  
> **模板目录：** `templates/`

---

## 1. 何时写

| 目录/文件 | 何时 | 写什么 | 谁写 |
|:---|:---|:---|:---|
| workspace `runs/YYYY-MM-DD.md` | 定时任务或完整链路**跑完** | run_id、成败、阶段、产物**路径指针** | 编排 Agent |
| workspace `changes/YYYY-MM-DD.md` | 修问题、改脚本、改配置、改 cron | 问题→根因→文件→同步勾选→验证 | 维护 Agent |
| workspace `issues/ISSUE-…` | 需跟进、能复现、可能改代码 | 现象/复现/影响/状态 | 任意 |
| Skill `改动说明.md` | 版本级变更、准备打包/发人 | 给人看的总账 | 维护 |
| Skill `lessons/` | 可复用业务规则（用户纠正） | 正确规则 + 适用范围 | 维护 |
| Skill `issue-log/` | 正式缺陷库（随包） | 与 workspace issues 可互链 | 维护 |
| Runtime `runs/<run_id>/` | pipeline 执行中 | 机器产物（非散文日志） | 程序 |
| `memory/YYYY-MM-DD.md` | 有值得记的决策/上下文 | 短记；非密钥 | 主会话 |
| `tmp/` | 调试中 | 探针/截图 | 用完删 |

**运行日志 ≠ 维护日志。** 跑批成功只写 `runs/` 不够时，修代码必须另写 `changes/`。

---

## 2. 文件名

| 类型 | 命名 |
|:---|:---|
| 运行摘要 | `runs/YYYY-MM-DD.md` 或 `runs/YYYY-MM-DD_HHMM.md` |
| 维护日志 | `changes/YYYY-MM-DD.md`（同日追加章节） |
| 工单 | `issues/ISSUE-YYYYMMDD-短标题.md` |
| 归档 | `archive/YYYY-MM/原文件名` |

---

## 3. 模板

直接复制 `templates/TEMPLATE_runs.md` / `TEMPLATE_changes.md` / `TEMPLATE_issues.md`。

### 3.1 运行摘要（通用字段，业务可增删）

```markdown
# 运行日志 YYYY-MM-DD

| 项 | 内容 |
|:---|:---|
| skill / 工作流 | |
| run_id | |
| 开始～结束 | |
| 总结果 | ok / failed |
| 失败点 | （若有） |
| Runtime 产物根 | `…/runs/<run_id>/` |

## 摘要
- （业务自定义阶段结果）

## 路径指针
- 主产物：
- 日志/配置：（勿写密钥）

## 异常与处理
- （无则写「无」）
```

### 3.2 维护日志（含同步勾选）

```markdown
# 维护日志 YYYY-MM-DD

## HH:MM 标题

### 问题
- run_id / 环境：
- 现象：

### 根因
-

### 修复
| 文件 | 修改 |
|------|------|
| | |

### 同步
- [ ] 权威源
- [ ] 本机 Runtime 副本
- [ ] workspace skills 安装副本
- [ ] 其他环境 / 生产
- [ ] 是否重打包

### 验证
- 命令或 run_id：
- 结果：
```

### 3.3 工单

```markdown
# ISSUE-YYYYMMDD-短标题

| 字段 | 内容 |
|:---|:---|
| 状态 | open / mitigated / closed |
| 发现于 | run_id / 环境 |
| 影响 | 哪一步 |

## 现象
## 复现
## 根因（已知则填）
## 修复与验证
## 关联 changes/
```

---

## 4. 新 Skill 时

1. 把 `templates/` 拷进 Agent workspace 或 Skill `references/templates/`  
2. 首跑写 `runs/`；首修写 `changes/`  
3. 业务专有字段（如标讯 keep/NR/reject）**只加在该 Skill 的模板附录**，不改通用三件套的骨架  

---

*版本：2026-07-20*
