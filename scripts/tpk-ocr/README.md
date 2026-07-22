# tpk-ocr

本地 OCR Skill，底层使用 PaddleOCR，适合中文 + 英文混合的截图、标讯、证书、网页截图、扫描 PDF 和表格图片识别。

## 1. 安装到 OpenClaw

### macOS / Linux

```bash
mkdir -p ~/.openclaw/skills
cp -R tpk-ocr ~/.openclaw/skills/tpk-ocr
```

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.openclaw\skills" | Out-Null
Copy-Item -Recurse -Force ".\tpk-ocr" "$env:USERPROFILE\.openclaw\skills\tpk-ocr"
```

安装后重启 OpenClaw，或开启一个新会话，让它重新加载本地 Skill。

## 2. 安装依赖

建议在 Skill 目录里创建虚拟环境：

### macOS / Linux

```bash
cd ~/.openclaw/skills/tpk-ocr
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
cd "$env:USERPROFILE\.openclaw\skills\tpk-ocr"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. 使用方法

识别单张图片：

```bash
python scripts/ocr_image.py "your-image.png" --lang ch --format md
```

保存识别结果：

```bash
python scripts/ocr_image.py "your-image.png" --lang ch --format md --output result.md
```

识别扫描 PDF：

```bash
python scripts/ocr_pdf.py "your-file.pdf" --pages all --dpi 220 --lang ch --format md --output result.md
```

识别指定页：

```bash
python scripts/ocr_pdf.py "your-file.pdf" --pages 1-3,5 --dpi 240 --lang ch --format md
```

## 4. 参数说明

- `--lang ch`：中文 + 英文混合，默认推荐。
- `--lang en`：纯英文。
- `--format md`：输出 Markdown。
- `--format text`：输出纯文本。
- `--format json`：输出结构化 JSON，包含文本、置信度和坐标。
- `--dpi 220`：PDF 渲染清晰度。文字小或扫描模糊时可改为 240 / 260。

## 5. 常见问题

第一次运行会下载 PaddleOCR 模型，速度取决于网络。后续运行会使用本地缓存。

如果识别结果差，优先检查图片清晰度。网页截图建议放大到 125% 或 150% 后再截图。

如果 PDF 很大，不要一次 OCR 全部页面。先用 `--pages 1-3` 这种范围测试。
