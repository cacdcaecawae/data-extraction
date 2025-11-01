#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将采购公告 HTML 转换为可读纯文本的工具函数集合。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup
from bs4.element import Comment
try:
    from markdownify import markdownify as to_markdown
except ImportError:  # pragma: no cover - lazy optional dependency
    to_markdown = None

LOGGER = logging.getLogger(__name__)

# 中国政府采购网站常见的编码顺序，按优先级排列。
DEFAULT_ENCODINGS: Sequence[str] = ("utf-8", "gb18030", "gbk", "gb2312")

# 常见的 HTML 文件后缀匹配模式。
DEFAULT_PATTERNS: Sequence[str] = ("*.html", "*.htm", "*.shtml", "*.xhtml")


def strip_bom(text: str) -> str:
    """Remove UTF BOM markers if present."""
    return text.lstrip("\ufeff\ufeff")


def read_html_text(
    path: Path,
    *,
    encodings: Sequence[str] = DEFAULT_ENCODINGS,
    errors: str = "ignore",
) -> str:
    """Read an HTML file from disk with best-effort decoding."""
    data = path.read_bytes()
    for encoding in encodings:
        try:
            text = data.decode(encoding)
            return strip_bom(text)
        except UnicodeDecodeError:
            continue
    LOGGER.debug(
        "Falling back to %s with errors=%s for %s",
        encodings[0],
        errors,
        path,
    )
    fallback = data.decode(encodings[0], errors=errors)
    return strip_bom(fallback)


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and replace non-breaking spaces."""
    if not text:
        return ""
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def html_to_text(
    html: str,
    *,
    separator: str = "\n",
    drop_empty_lines: bool = True,
    table_cell_sep: str = " | ",
) -> str:
    """Convert raw HTML markup into Markdown text suitable for LLM extraction."""
    if to_markdown is None:
        raise RuntimeError("未安装 markdownify，请先执行 `pip install markdownify`。")
    soup = BeautifulSoup(html, "lxml")

    # 移除脚本、样式、模板等非正文节点。
    for element in soup(["script", "style", "template", "noscript"]):
        element.decompose()
    for comment in soup.find_all(string=lambda item: isinstance(item, Comment)):
        comment.extract()

    # 将表格结构转换为 Markdown 风格，保留列之间的对应关系。
    for table in soup.find_all("table"):
        row_values: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            values: list[str] = [
                normalize_whitespace(cell.get_text(separator=" ", strip=True))
                for cell in cells
            ]
            if not any(values):
                continue
            row_values.append(values)

        if row_values:
            joiner = table_cell_sep if table_cell_sep else " | "

            def format_row(cells: list[str]) -> str:
                return "| " + joiner.join(cells) + " |"

            header = format_row(row_values[0])
            column_count = max(len(row_values[0]), 1)
            divider = "| " + " | ".join("---" for _ in range(column_count)) + " |"
            body_rows = [format_row(row) for row in row_values[1:]]
            table_lines = [header, divider, *body_rows]
            table_text = "\n".join(table_lines)
        else:
            table_text = ""
        replacement = soup.new_string(table_text) if table_text else soup.new_string("")
        table.replace_with(replacement)

    markdown = to_markdown(
        str(soup),
        heading_style="ATX",
        strip=["script", "style", "template", "noscript"],
        bullets="*",
    ).strip()

    def _clean_line(line: str) -> str:
        # 保留 Markdown 语法同时移除常见不可见字符。
        cleaned = line.replace("\u00a0", " ").replace("\u3000", " ")
        return cleaned.rstrip()

    lines = [_clean_line(line) for line in markdown.splitlines()]
    if drop_empty_lines:
        lines = [line for line in lines if line.strip()]
    text = separator.join(lines).strip()
    return _trim_markdown_sections(text, separator=separator)


def _trim_markdown_sections(
    text: str,
    *,
    heading_prefix: str = "##",
    end_marker: str = "请按以下方式联系",
    separator: str = "\n",
) -> str:
    """Keep useful body by trimming boilerplate before/after markers."""
    if not text:
        return text

    lines = text.split(separator)

    start_index: Optional[int] = None
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(f"{heading_prefix} "):
            start_index = idx
            break
    if start_index is not None:
        lines = lines[start_index:]

    end_index: Optional[int] = None
    for idx, line in enumerate(lines):
        if end_marker in line:
            end_index = idx
            break
    if end_index is not None:
        lines = lines[:end_index]

    return separator.join(lines).strip()


def convert_html_file(
    path: Path,
    *,
    encodings: Sequence[str] = DEFAULT_ENCODINGS,
    separator: str = "\n",
    drop_empty_lines: bool = True,
    table_cell_sep: str = " | ",
) -> str:
    """Read an HTML file and return normalized text."""
    html = read_html_text(path, encodings=encodings)
    return html_to_text(
        html,
        separator=separator,
        drop_empty_lines=drop_empty_lines,
        table_cell_sep=table_cell_sep,
    )


def collect_html_paths(
    root: Path,
    *,
    patterns: Sequence[str] = DEFAULT_PATTERNS,
) -> List[Path]:
    """Return a de-duplicated, sorted list of HTML-like files under ``root``."""
    files: List[Path] = []
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            files.append(path)
    return files


def iter_html_texts(
    root: Path,
    *,
    patterns: Sequence[str] = DEFAULT_PATTERNS,
    encodings: Sequence[str] = DEFAULT_ENCODINGS,
    separator: str = "\n",
    drop_empty_lines: bool = True,
    table_cell_sep: str = " | ",
    fail_silently: bool = False,
) -> Iterator[Tuple[Path, str]]:
    """Yield ``(path, text)`` pairs for every HTML file under ``root``."""
    for path in collect_html_paths(root, patterns=patterns):
        try:
            yield path, convert_html_file(
                path,
                encodings=encodings,
                separator=separator,
                drop_empty_lines=drop_empty_lines,
                table_cell_sep=table_cell_sep,
            )
        except Exception as exc:  # pylint: disable=broad-except
            if fail_silently:
                LOGGER.warning("Failed to convert %s: %s", path, exc)
                continue
            raise


__all__ = [
    "DEFAULT_ENCODINGS",
    "DEFAULT_PATTERNS",
    "collect_html_paths",
    "convert_html_file",
    "html_to_text",
    "iter_html_texts",
    "normalize_whitespace",
    "read_html_text",
    "strip_bom",
]
