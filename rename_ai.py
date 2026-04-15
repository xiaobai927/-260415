#!/usr/bin/env python3
"""
AI batch file renamer (MVP)

Features:
- Windows-friendly
- Dry-run by default
- AI-generated rename plan (JSON)
- Conflict / illegal filename checks
- Apply + undo support with log file
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any


WINDOWS_ILLEGAL_CHARS = r'[<>:"/\\|?*]'
DEFAULT_MODEL = "gpt-4.1-mini"


class RenameError(Exception):
    pass


def load_openai_client() -> Any:
    """Lazily load OpenAI client so import errors are clearer for beginners."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RenameError(
            "找不到 openai 依赖。请先执行: pip install -r requirements.txt"
        ) from exc

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RenameError(
            "未检测到 OPENAI_API_KEY 环境变量。\n"
            "Windows PowerShell 示例: $env:OPENAI_API_KEY='你的key'"
        )
    return OpenAI(api_key=api_key)


def discover_files(folder: Path, pattern: str) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise RenameError(f"目录不存在: {folder}")
    files = sorted([p for p in folder.glob(pattern) if p.is_file()])
    if not files:
        raise RenameError(f"没有找到匹配文件: {pattern}")
    return files


def local_sort(files: list[Path], mode: str) -> list[Path]:
    if mode == "name":
        return sorted(files, key=lambda p: p.name.lower())
    if mode == "mtime":
        return sorted(files, key=lambda p: p.stat().st_mtime)
    raise RenameError(f"未知排序模式: {mode}")


def build_prompt(files: list[Path], rule: str) -> str:
    file_names = "\n".join(f"- {p.name}" for p in files)
    return (
        "你是文件重命名助手。\n"
        "请严格输出 JSON 数组，不要输出任何解释文字。\n"
        "JSON 格式: [{\"old\":\"旧文件名\",\"new\":\"新文件名\"}]\n"
        "要求:\n"
        "1) old 必须来自输入列表。\n"
        "2) new 必须保留原扩展名。\n"
        "3) new 不得重复。\n"
        "4) 只返回 JSON。\n\n"
        f"重命名规则:\n{rule}\n\n"
        f"输入文件列表:\n{file_names}\n"
    )


def request_plan_from_ai(files: list[Path], rule: str, model: str) -> list[dict[str, str]]:
    client = load_openai_client()
    prompt = build_prompt(files, rule)
    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0,
    )
    text = (response.output_text or "").strip()
    if not text:
        raise RenameError("AI 返回为空，无法解析重命名计划。")

    try:
        plan = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RenameError(
            "AI 返回不是合法 JSON。建议优化 --rule 并重试。\n"
            f"AI原始返回:\n{text}"
        ) from exc

    if not isinstance(plan, list):
        raise RenameError("AI 返回必须是 JSON 数组。")

    normalized: list[dict[str, str]] = []
    for item in plan:
        if not isinstance(item, dict) or "old" not in item or "new" not in item:
            raise RenameError("AI 返回项格式错误，必须包含 old/new。")
        old = str(item["old"]).strip()
        new = str(item["new"]).strip()
        normalized.append({"old": old, "new": new})
    return normalized


def validate_plan(files: list[Path], plan: list[dict[str, str]]) -> list[tuple[Path, Path]]:
    original_names = {p.name: p for p in files}
    used_new_names: set[str] = set()
    ops: list[tuple[Path, Path]] = []

    for row in plan:
        old = row["old"]
        new = row["new"]

        if old not in original_names:
            raise RenameError(f"计划中 old 不存在: {old}")

        src = original_names[old]
        if src.suffix.lower() != Path(new).suffix.lower():
            raise RenameError(f"扩展名不一致: {old} -> {new}")

        if re.search(WINDOWS_ILLEGAL_CHARS, new):
            raise RenameError(f"文件名含 Windows 非法字符: {new}")

        if new in used_new_names:
            raise RenameError(f"目标文件名重复: {new}")
        used_new_names.add(new)

        dst = src.with_name(new)
        ops.append((src, dst))

    if len(ops) != len(files):
        raise RenameError(
            f"计划数量与文件数量不一致。文件={len(files)}，计划={len(ops)}"
        )

    # destination collision check with existing unrelated files
    existing_names = {p.name for p in files[0].parent.iterdir() if p.is_file()}
    for src, dst in ops:
        if dst.name != src.name and dst.name in existing_names and dst.name not in original_names:
            raise RenameError(f"目标文件名已存在于目录中: {dst.name}")

    return ops


def print_plan(ops: list[tuple[Path, Path]]) -> None:
    print("\n重命名预览:")
    for src, dst in ops:
        marker = "(保持不变)" if src.name == dst.name else ""
        print(f"- {src.name}  ->  {dst.name} {marker}")


def apply_plan(ops: list[tuple[Path, Path]], log_file: Path) -> None:
    # Two-phase rename to avoid A->B and B->A collision
    temp_ops: list[tuple[Path, Path]] = []
    for i, (src, _) in enumerate(ops):
        temp = src.with_name(f".__tmp_rename_{i}__{src.suffix}")
        src.rename(temp)
        temp_ops.append((temp, src))

    # map tmp -> final
    for i, (tmp, original_src) in enumerate(temp_ops):
        final_dst = ops[i][1]
        tmp.rename(final_dst)

    payload = {
        "created_at": dt.datetime.now().isoformat(),
        "operations": [{"old": str(src.name), "new": str(dst.name)} for src, dst in ops],
    }
    log_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已执行重命名。日志已保存: {log_file}")


def undo_from_log(folder: Path, log_file: Path, dry_run: bool) -> None:
    if not log_file.exists():
        raise RenameError(f"日志文件不存在: {log_file}")
    data = json.loads(log_file.read_text(encoding="utf-8"))
    ops = data.get("operations", [])
    if not isinstance(ops, list):
        raise RenameError("日志格式错误: operations 必须是数组")

    undo_ops: list[tuple[Path, Path]] = []
    for row in ops:
        new_name = row["new"]
        old_name = row["old"]
        src = folder / new_name
        dst = folder / old_name
        undo_ops.append((src, dst))

    print("\n回滚预览:")
    for src, dst in undo_ops:
        print(f"- {src.name}  ->  {dst.name}")

    if dry_run:
        print("\n当前是 dry-run，未执行回滚。")
        return

    # Two-phase undo
    temp_ops: list[tuple[Path, Path]] = []
    for i, (src, _) in enumerate(undo_ops):
        if not src.exists():
            raise RenameError(f"回滚失败，文件不存在: {src}")
        temp = src.with_name(f".__tmp_undo_{i}__{src.suffix}")
        src.rename(temp)
        temp_ops.append((temp, src))

    for i, (tmp, _) in enumerate(temp_ops):
        tmp.rename(undo_ops[i][1])

    print("\n回滚完成。")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 批量重命名工具（MVP）")
    parser.add_argument("--folder", required=True, help="目标目录，例如 D:/subs")
    parser.add_argument("--pattern", default="*.srt", help="文件匹配模式，默认 *.srt")
    parser.add_argument(
        "--sort",
        default="name",
        choices=["name", "mtime"],
        help="本地排序方式: name 或 mtime",
    )
    parser.add_argument("--rule", help="重命名规则（自然语言）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名，默认 {DEFAULT_MODEL}")
    parser.add_argument("--apply", action="store_true", help="确认执行重命名")
    parser.add_argument("--log-file", default="rename_log.json", help="日志文件名")
    parser.add_argument("--undo", help="根据日志回滚，例如 --undo rename_log.json")

    args = parser.parse_args()
    folder = Path(args.folder).expanduser().resolve()

    if args.undo:
        undo_from_log(folder=folder, log_file=Path(args.undo).resolve(), dry_run=not args.apply)
        return

    if not args.rule:
        raise RenameError("请提供 --rule，例如: '按文件名排序，命名为4月12日播出-第x集.srt'")

    files = discover_files(folder, args.pattern)
    files = local_sort(files, args.sort)
    plan = request_plan_from_ai(files=files, rule=args.rule, model=args.model)
    ops = validate_plan(files=files, plan=plan)

    print_plan(ops)
    if not args.apply:
        print("\n当前是 dry-run（默认），未执行重命名。确认无误后加 --apply。")
        return

    log_file = (folder / args.log_file).resolve()
    apply_plan(ops, log_file)


if __name__ == "__main__":
    try:
        main()
    except RenameError as exc:
        print(f"\n[错误] {exc}")
        raise SystemExit(1)
