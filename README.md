# AI 批量重命名工具（Windows 新手版 MVP）

这是一个适合 0 基础用户的最小可运行版本：
- 支持 `.srt`（也可改为其他后缀）
- 默认 `dry-run` 只预览不执行
- 使用 AI 根据自然语言规则生成“旧名 -> 新名”计划
- 支持回滚（undo）

---

## 1. 先决条件

1) 安装 Python 3.11+（安装时勾选 **Add Python to PATH**）。

2) 准备 OpenAI API Key（或兼容 OpenAI API 的 Key）。

---

## 2. 安装步骤（Windows PowerShell）

在本项目目录打开 PowerShell，依次执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

设置 API Key（仅当前窗口生效）：

```powershell
$env:OPENAI_API_KEY="你的API_KEY"
```

---

## 3. 先做预览（强烈推荐）

```powershell
python .\rename_ai.py --folder "D:\你的字幕目录" --pattern "*.srt" --sort name --rule "按文件名顺序，从2026年4月12日开始每天一集，命名为{M}月{D}日播出-第{ep}集.srt"
```

说明：
- 不加 `--apply` 时，默认只预览，不真正改名。
- `--sort` 可选 `name` 或 `mtime`（按修改时间）。

---

## 4. 确认后执行改名

```powershell
python .\rename_ai.py --folder "D:\你的字幕目录" --pattern "*.srt" --sort name --rule "按文件名顺序，从2026年4月12日开始每天一集，命名为{M}月{D}日播出-第{ep}集.srt" --apply
```

执行成功后，会在目标目录生成日志文件（默认：`rename_log.json`）。

---

## 5. 需要时回滚

先预览回滚：

```powershell
python .\rename_ai.py --folder "D:\你的字幕目录" --undo "D:\你的字幕目录\rename_log.json"
```

确认后执行回滚：

```powershell
python .\rename_ai.py --folder "D:\你的字幕目录" --undo "D:\你的字幕目录\rename_log.json" --apply
```

---

## 6. 常见问题

### Q1: 报错“未检测到 OPENAI_API_KEY”
请先执行：

```powershell
$env:OPENAI_API_KEY="你的API_KEY"
```

### Q2: AI 返回不是 JSON
你给的 `--rule` 可能太复杂或含糊。建议更明确：
- 排序依据（name / mtime）
- 起始日期
- 集数规则
- 目标格式

### Q3: 为什么我看到“dry-run”
这是安全设计，防止误改名。确认预览正确后再加 `--apply`。

---

## 7. 安全建议（务必先看）

- 先备份文件夹再操作。
- 先在测试目录练习 5~10 个文件。
- 每次先 dry-run，确认后再 apply。

---

## 8. 说明

本 MVP 目标是“先可用、再迭代”。后续可以继续扩展：
- 图形界面（GUI）
- 自定义模板变量
- 分批处理大目录
- 本地规则优先 + AI 兜底
