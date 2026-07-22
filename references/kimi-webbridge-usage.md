# Kimi WebBridge 使用指南（标讯自动化专用）

## 环境要求

- **浏览器**：仅 Chrome（禁用 Edge 等其他浏览器的 Kimi WebBridge 扩展）
- **daemon 版本**：v1.11.1+
- **扩展版本**：v1.11.0+
- **端口**：10086

## 自动恢复流程

`ensure_browser_channel_20260622_v01.py` 已集成 Kimi WebBridge 自动恢复：

1. 检查 daemon 状态（`extension_connected`）
2. 如果 daemon 未运行：
   - 检测 Chrome 是否运行 → 未运行则自动启动
   - 清理残留 `daemon.pid`（仅在进程不存在时删除）
   - 启动 daemon
   - 等待扩展连接（最多 15 秒）
3. 验证千里马登录态
4. 如果登录态无效，尝试自动登录

## Windows 请求格式（必须用文件）

PowerShell 会破坏非 ASCII 字符（中文等），inline JSON 中的中文会变成 `?` 且不可恢复。

**正确方式**：
1. 用 Write 工具创建 JSON 文件（文件名带随机后缀避免并发冲突）
2. 用 `curl.exe`（不是 `curl`）发送请求：
   ```powershell
   curl.exe -s -X POST http://127.0.0.1:10086/command -H "Content-Type: application/json" --data-binary "@$env:TEMP\req-xxx.json"
   ```
3. 请求完成后删除临时文件

## 常用 Action

| Action | 用途 | 必填参数 |
|--------|------|----------|
| `navigate` | 打开网页 | `url` |
| `snapshot` | 读取页面内容（无障碍树） | 无 |
| `click` | 点击元素 | `selector`（@e 或 CSS） |
| `fill` | 填写输入框 | `selector`, `value` |
| `screenshot` | 截图 | 无（可选 `path`, `format`, `selector`） |
| `save_as_pdf` | 保存 PDF | 无（可选 `path`, `paper_format`） |
| `evaluate` | 执行 JS | `code` |
| `list_tabs` | 列出标签 | 无 |
| `find_tab` | 查找标签 | `url`（完整 URL） |
| `close_session` | 关闭会话 | 无 |

## Session 规则

- 一个任务 = 一个 session
- 用任务名命名（如 `bid-daily-20260709`），不用网站名
- 同一任务的所有请求用同一个 session
- `group_title` 在第一次 `navigate` 时设置（人类可读的标签组名称）

## 截图参数

```json
{
  "action": "screenshot",
  "args": {
    "format": "png",
    "path": "保存路径（可选）",
    "selector": "@e 或 CSS（可选，截取指定元素）"
  }
}
```

## PDF 参数

```json
{
  "action": "save_as_pdf",
  "args": {
    "paper_format": "a4",
    "landscape": false,
    "scale": 1.0,
    "print_background": true,
    "path": "保存路径（可选）"
  }
}
```

## 常见问题排查

| 问题 | 原因 | 解决方法 |
|------|------|----------|
| 连接失败 | daemon 未启动 | `kimi-webbridge start` |
| 扩展未连接 | Chrome 未打开或扩展被禁用 | 打开 Chrome，检查扩展 |
| PID 文件残留 | 上次退出未清理 | 自动清理（脚本已集成） |
| 端口占用 | 其他进程占用 10086 | 检查并终止占用进程 |
| 中文乱码 | Windows 用了 inline JSON | 改用文件方式发送请求 |
| 502 Bad Gateway | 多扩展冲突或 daemon 不稳定 | 只保留 Chrome 扩展，升级 daemon |
| No current window | Chrome 不在前台 | 将 Chrome 切到前台（v1.11.1 已修复） |
| group_title 乱码 | 扩展版本过低 | 升级到 v1.11.1（已修复） |

## 升级命令

```bash
kimi-webbridge upgrade
```

升级后需要重启 daemon：
```bash
# 停止旧 daemon
Get-Process | Where-Object {$_.ProcessName -like "*kimi*"} | Stop-Process -Force
# 清理 PID
Remove-Item "$env:USERPROFILE\.kimi-webbridge\daemon.pid" -Force
# 启动新 daemon
kimi-webbridge start
```

## 健康检查

```bash
kimi-webbridge status
```

正常输出：
```json
{
  "extension_connected": true,
  "extension_id": "fldmhceldgbpfpkbgopacenieobmligc",
  "extension_version": "1.11.0",
  "port": 10086,
  "running": true,
  "version": "v1.11.1"
}
```
