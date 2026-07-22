# 经验教训日志（持续追加）

> 只写**可执行规则**。详情与背景见 `issue-log/entries/`。  
> 新条目加在文件**顶部**（最新在上）。

---

## 2026-07-20

### 合法全排除也必须能出 Excel / 过 Phase34

- **来源：** 生产 run `20260720_080800`；`changes/2026-07-20.md`  
- **规则：**  
  1. `report_builder` 清空模板示例时禁止对 `MergedCell` 赋值。  
  2. Excel 契约校验在 business 全为 reject 时允许无「项目N」sheet（warning 即可）。  
  3. 修复须回写 G 源码并重打包，避免 D 盘独修、重装回退。  

### Agent 工作区必须 runs / changes / issues 分流

- **来源：** 生产 Agent `AGENTS.md` 目录标准  
- **规则：**  
  1. 根目录只放配置身份文件；禁止堆 .py/.png/散落报告。  
  2. 定时运行摘要 → `runs/`；人工修复 → `changes/`；缺陷 → `issues/`；历史 → `archive/YYYY-MM/`。  
  3. 新 Skill / 新 workspace 照抄 `references/workspace-recording-standard.md`。  

---

## 2026-07-16

### 生产定时任务约 12 分钟全绿，确认 v08 主线可定型

- **来源：** 用户反馈 + 生产定时任务（另一 Agent 执行）；对照 `改动说明.md`「生产定时任务验收通过」  
- **现象：** 全链路顺利发出简报，无明显卡顿，总耗时约 12 分钟。  
- **规则：**  
  1. **生产验收优先于测试机插曲**：测试编排中的 CDP 10054、PowerShell 中文路径丢 `--raw-export` 等，不得单独否定「目标行锁 / 登录等待 / 附件看门狗」等主线修复。  
  2. **登录**：进站须过刷新稳定期与超时弹窗；密码表单未就绪禁止填账密；顶栏搜索不得填账号。  
  3. **导出记录**：操作列驱动；「刷新」= 目标行按钮，禁止 Page.reload 空转；目标行时间窗放宽（约 5 分钟）并允许 generation 后 re-lock。  
  4. **额度 0**：可继续导出/生成链路，禁止长时间空刷；默认禁止用历史已生成行冒充本次导出。  
  5. **附件**：必须有分段日志与下载/预览预算；STREAM 优先；不得静默卡死。  
  6. **Phase4**：本地归档 → 共享盘 → 钉盘 doc_url → 钉钉；DWS access token 过期须先 `dws auth login` 再上传。  
  7. **定型包**：以 `qianlima-bid-daily-workflow_20260716_v08-release01`（`release_status=released`）为当前正式基线；定时任务应对齐该包/对应 runtime，勿回退旧脚本。  

---

## 2026-07-14

### 附件 2B/2C 必须有分段日志与下载看门狗

- **来源：** ISSUE-20260714-attach-download-watchdog（标神）  
- **规则：**  
  1. Phase2 附件脚本必须写 `99_logs/phase2c_attach_*.log`，禁止子进程启动后整段静默。  
  2. 流式下载：读超时不宜超过 90s；字节无增长约 60s 应终止。  
  3. 预览/SPA 必须有 wall 预算，禁止无进展长循环。  
  4. 单附件/单项目须有总预算，防止多附件串行叠加拖死整管线。  

### 额度弹窗剩余 0 必须 fail-fast

- **来源：** ISSUE-20260714-quota-zero  
- **规则：**  
  1. 解析到「今日剩余额度 0 条」且继续导出后目标行仍无「下载」→ 明确失败，禁止长时间空刷。  
  2. 生产默认禁止用历史「已生成」行冒充本次新导出；联调才可开 `--allow-existing-export-download`。  

### 专用 CDP 同 port 只能单写

- **来源：** ISSUE-20260714-cdp-contention  
- **规则：**  
  1. 总入口对 CDP port 加文件锁，等待 5～10 分钟；勿并行双开同一调试口。  
  2. 单专用号不做多 port 多登录「真并行」（会互踢）。  

### 钉钉主备 webhook 要可观测

- **来源：** ISSUE-20260714-dingtalk-backup  
- **规则：**  
  1. 主：`dingtalk_webhook_url`；抄送：`dingtalk_webhook_url_backup`。  
  2. preflight 只报告 backup 是否配置的布尔；发送结果写 `backup_webhook.success`。  
  3. backup 失败默认不否掉 full_run。  

### Windows 附件 rename 必须幂等

- **来源：** ISSUE-20260714-attach-rename  
- **规则：** 重试下载时目标文件已存在则覆盖/复用，禁止裸 `rename` 导致 WinError 183。  

### 2B soft-continue 不得假绿

- **来源：** ISSUE-20260714-soft-continue  
- **规则：** 仅 body_empty 类 retry 且 body_ok 比例达标（默认 ≥50%，≤2 条要全 ok）才允许 soft-continue；含 login/captcha/error 必须失败。  

### 记录分工

- **来源：** 记录体系规范  
- **规则：**  
  - 会话结论 → `日志/`  
  - 程序产物 → runtime `runs/` `output/`  
  - 待修问题 → `issue-log/`  
  - 长期规则 → 本文件 `lessons_log.md`  
  - 禁止密钥写入以上任意位置  
