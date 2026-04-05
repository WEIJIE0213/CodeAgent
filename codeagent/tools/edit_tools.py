"""
edit_tools —— 精确文件编辑工具

提供比 write_file 更细粒度的文件修改能力：
- apply_diff: 应用 unified diff 格式的补丁
- search_and_replace: 在文件中搜索并替换文本
- insert_content: 在指定行号后插入内容
"""
import re
from pathlib import Path
from langchain_core.tools import tool

from codeagent.config import settings


def _safe_path(path: str) -> Path:
    workspace = Path(settings.WORKSPACE_DIR).resolve()
    target = (workspace / path).resolve()
    if not str(target).startswith(str(workspace)):
        raise PermissionError(f"路径 '{path}' 超出工作目录 '{workspace}'，拒绝访问")
    return target


# ── apply_diff ────────────────────────────────────────────────────────────────

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_hunks(diff_content: str) -> list[dict]:
    """将 unified diff 文本解析为 hunk 列表"""
    hunks = []
    current: dict | None = None

    for line in diff_content.splitlines():
        m = _HUNK_HEADER.match(line)
        if m:
            if current is not None:
                hunks.append(current)
            current = {
                "old_start": int(m.group(1)),
                "lines": [],
            }
            continue

        if current is None:
            # 跳过 --- / +++ 头部及其他无关行
            continue

        if line.startswith(" ") or line.startswith("-") or line.startswith("+"):
            current["lines"].append(line)
        # 忽略 '\ No newline at end of file' 等元信息行

    if current is not None:
        hunks.append(current)

    return hunks


def _apply_single_hunk(file_lines: list[str], hunk: dict) -> list[str] | str:
    """
    将单个 hunk 应用到 file_lines（1-indexed）。
    成功返回新行列表，失败返回错误字符串。
    """
    old_start = hunk["old_start"]
    hunk_lines = hunk["lines"]

    # 从 old_start - 1 开始扫描（0-indexed），允许上下偏移 ±5 行容错
    best_offset = None
    for offset in range(-5, 6):
        pos = old_start - 1 + offset
        if pos < 0:
            continue
        fi = pos  # file index
        match = True
        for hl in hunk_lines:
            if hl.startswith("+"):
                continue
            if fi >= len(file_lines):
                match = False
                break
            expected = hl[1:]  # 去掉首字符（' ' 或 '-'）
            if file_lines[fi].rstrip("\n") != expected.rstrip("\n"):
                match = False
                break
            fi += 1
        if match:
            best_offset = offset
            break

    if best_offset is None:
        return f"hunk @@ -{old_start} 上下文匹配失败（文件内容与 diff 不符）"

    apply_at = old_start - 1 + best_offset
    result = list(file_lines[:apply_at])
    fi = apply_at

    for hl in hunk_lines:
        if hl.startswith(" "):
            result.append(file_lines[fi])
            fi += 1
        elif hl.startswith("-"):
            fi += 1  # 跳过（删除）
        elif hl.startswith("+"):
            new_line = hl[1:]
            # 保留原行换行符风格
            if file_lines and "\n" in file_lines[0]:
                if not new_line.endswith("\n"):
                    new_line += "\n"
            result.append(new_line)

    result.extend(file_lines[fi:])
    return result


@tool
def apply_diff(path: str, diff_content: str) -> str:
    """
    将 unified diff 格式的补丁应用到文件。适合精确修改文件的局部内容，无需重写整个文件。
    path: 相对路径，如 'src/main.py'
    diff_content: unified diff 格式的补丁内容（支持多个 @@ hunk）
    """
    try:
        target = _safe_path(path)
        if not target.exists():
            return f"错误：文件不存在 '{path}'"
        if not target.is_file():
            return f"错误：'{path}' 不是文件"

        hunks = _parse_hunks(diff_content)
        if not hunks:
            return "错误：diff 内容中未找到有效的 @@ hunk，请检查格式"

        file_lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        # 逆序应用 hunk，避免行号偏移问题
        for hunk in reversed(hunks):
            result = _apply_single_hunk(file_lines, hunk)
            if isinstance(result, str):
                return f"应用失败：{result}"
            file_lines = result

        target.write_text("".join(file_lines), encoding="utf-8")
        return f"已成功应用 {len(hunks)} 个 hunk 到 '{path}'"

    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"apply_diff 失败：{e}"


# ── search_and_replace ────────────────────────────────────────────────────────

@tool
def search_and_replace(path: str, old_text: str, new_text: str, use_regex: bool = False) -> str:
    """
    在文件中搜索并替换文本。
    path: 相对路径，如 'src/main.py'
    old_text: 要搜索的文本（字面量或正则表达式）
    new_text: 替换为的文本
    use_regex: 是否将 old_text 视为正则表达式（默认 False）
    """
    try:
        target = _safe_path(path)
        if not target.exists():
            return f"错误：文件不存在 '{path}'"
        if not target.is_file():
            return f"错误：'{path}' 不是文件"

        content = target.read_text(encoding="utf-8", errors="replace")

        if use_regex:
            try:
                pattern = re.compile(old_text, re.MULTILINE)
            except re.error as e:
                return f"正则表达式错误：{e}"
            new_content, count = pattern.subn(new_text, content)
        else:
            count = content.count(old_text)
            new_content = content.replace(old_text, new_text)

        if count == 0:
            return f"未找到匹配内容，文件未修改（搜索：{repr(old_text[:80])}）"

        target.write_text(new_content, encoding="utf-8")
        return f"已在 '{path}' 中完成 {count} 处替换"

    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"search_and_replace 失败：{e}"


# ── insert_content ────────────────────────────────────────────────────────────

@tool
def insert_content(path: str, insert_after_line: int, content: str) -> str:
    """
    在文件指定行号后插入内容。
    path: 相对路径，如 'src/main.py'
    insert_after_line: 在此行号之后插入（从1开始计数）。0 表示插入到文件最开头
    content: 要插入的文本（若不以换行结尾，会自动补充）
    """
    try:
        target = _safe_path(path)
        if not target.exists():
            return f"错误：文件不存在 '{path}'"
        if not target.is_file():
            return f"错误：'{path}' 不是文件"

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        total = len(lines)

        if insert_after_line < 0:
            return f"错误：insert_after_line 不能为负数（当前值：{insert_after_line}）"
        if insert_after_line > total:
            return f"错误：insert_after_line={insert_after_line} 超过文件总行数 {total}"

        # 确保插入内容以换行结尾
        if content and not content.endswith("\n"):
            content += "\n"

        new_lines = lines[:insert_after_line] + [content] + lines[insert_after_line:]
        target.write_text("".join(new_lines), encoding="utf-8")

        pos_desc = "文件开头" if insert_after_line == 0 else f"第 {insert_after_line} 行之后"
        return f"已在 '{path}' {pos_desc} 插入内容（{len(content)} 字符）"

    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"insert_content 失败：{e}"
