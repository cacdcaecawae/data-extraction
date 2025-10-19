#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch extract 8 core procurement indicators from HTML announcements,
and export the results to CSV / JSONL files.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from dateutil import parser as date_parser

LOGGER = logging.getLogger("extract_html_procurement")

ENCODINGS = ("utf-8", "gbk", "gb18030")

# ----------------------------------------------------------------------
# Field configuration: adjust aliases / stopwords / regex as needed.
# ----------------------------------------------------------------------
FIELD_DEFINITIONS: Sequence[Dict] = (
    dict(
        name="公告时间",
        aliases=("公告时间", "发布日期", "发布时间", "发布公告时间", "信息时间"),
        multi=False,
        stopwords=(),
        fallback=(r"(公告时间|发布日期|发布时间|信息时间)[:：]?\s*(\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2})",),
    ),
    dict(
        name="项目名称",
        aliases=("项目名称", "采购项目名称", "项目名称"),
        multi=False,
        stopwords=("采购单位", "采购人名称", "公告时间", "供应商名称", "中标金额"),
        fallback=(r"(项目名称|采购项目名称)[:：]?\s*([^\n\r]{2,120})",),
    ),
    dict(
        name="采购单位名称",
        aliases=("采购人名称", "采购单位"),
        multi=False,
        stopwords=(
            "采购单位地址",
            "采购人地址",
            "供应商名称",
            "中标金额",
            "成交金额",
            "采购人联系人",
            "采购人联系电话",
            "遴选专家名单",
            "行政区域",
        ),
        fallback=(r"(采购人名称|采购单位)[:：]?\s*([^\n\r]{2,120})",),
    ),
    dict(
        name="采购单位地址",
        aliases=("采购人地址", "采购单位地址"),
        multi=False,
        stopwords=(
            "采购单位名称",
            "供应商名称",
            "中标金额",
            "成交金额",
            "采购单位联系方式",
            "采购人联系方式",
            "代理机构名称",
            "代理机构地址",
            "附件",
        ),
        fallback=(r"(采购人地址|采购单位地址)[:：]?\s*([^\n\r]{2,160})",),
    ),
    dict(
        name="供应商名称",
        aliases=("供应商名称", "中标供应商", "成交供应商", "供应商", "中标人", "成交人"),
        multi=False,
        stopwords=(
            "供应商地址",
            "中标金额",
            "成交金额",
            "采购类别",
            "采购方式",
            "综合评分",
            "最终得分",
        ),
        fallback=(r"(供应商名称|中标供应商|成交供应商|中标人|成交人)[:：]?\s*([^\n\r]{2,160})",),
    ),
    dict(
        name="供应商地址",
        aliases=("供应商地址", "中标供应商地址", "成交供应商地址"),
        multi=False,
        stopwords=("供应商名称", "中标金额", "成交金额", "采购类别"),
        fallback=(r"(供应商地址|中标供应商地址|成交供应商地址)[:：]?\s*([^\n\r]{2,200})",),
    ),
    dict(
        name="中标金额",
        aliases=("中标金额", "中标（成交）金额", "成交金额", "合同金额"),
        multi=False,
        stopwords=(),
        fallback=(r"(中标金额|成交金额|合同金额)[:：]?\s*([^\n\r]{1,80})",),
    ),
    dict(
        name="采购类别",
        aliases=("采购类别", "采购类型", "采购方式", "项目类别", "品目"),
        multi=True,
        stopwords=(),
        fallback=(r"(采购类别|采购方式|项目类别|品目)[:：]?\s*([^\n\r]{1,80})",),
    ),
)

FIELD_ORDER: Sequence[str] = tuple(item["name"] for item in FIELD_DEFINITIONS)
MULTI_VALUE_FIELDS = {item["name"] for item in FIELD_DEFINITIONS if item["multi"]}
FIELD_KEYWORDS: Dict[str, Sequence[str]] = {item["name"]: item["aliases"] for item in FIELD_DEFINITIONS}
FIELD_STOPWORDS: Dict[str, Sequence[str]] = {item["name"]: item["stopwords"] for item in FIELD_DEFINITIONS}
FULL_TEXT_PATTERNS: Dict[str, Sequence[re.Pattern]] = {
    item["name"]: tuple(re.compile(pattern) for pattern in item["fallback"]) if item["fallback"] else ()
    for item in FIELD_DEFINITIONS
}

CATEGORY_KEYWORDS = {
    "货物": ("货物", "设备", "物资", "用品", "耗材"),
    "服务": ("服务", "咨询", "保障", "培训", "运营", "维护"),
    "工程": ("工程", "施工", "改造", "维修", "建设"),
}

BLOCK_TAGS = {
    "p",
    "li",
    "span",
    "strong",
    "em",
    "b",
    "div",
    "td",
    "th",
    "dd",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}

TABLE_RANK_HEADERS = {
    "得分排名",
    "得分排位",
    "得分排名情况",
    "排名",
    "综合排名",
}
TABLE_RANK_ACCEPT = {"1", "第一名", "第一", "冠军"}


@dataclass
class FieldValue:
    multi: bool
    entries: List[Tuple[int, str]] = field(default_factory=list)

    def add(self, value: str, order: int) -> None:
        if not value:
            return
        cleaned = value.strip()
        if not cleaned:
            return
        if self.entries and not self.multi:
            return
        if self.multi and cleaned in {item[1] for item in self.entries}:
            return
        self.entries.append((order, cleaned))

    def get(self) -> str:
        if not self.entries:
            return ""
        if self.multi:
            ordered = [value for _, value in sorted(self.entries, key=lambda item: item[0])]
            unique: List[str] = []
            for value in ordered:
                if value not in unique:
                    unique.append(value)
            return "|".join(unique)
        return self.entries[0][1]


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def read_html_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\u3000", " ").replace("\xa0", " ")).strip()


def normalize_label_text(text: str) -> str:
    if not text:
        return ""
    cleaned = normalize_whitespace(text)
    cleaned = cleaned.replace("：", "").replace(":", "")
    cleaned = cleaned.replace("（", "").replace("）", "")
    cleaned = re.sub(r"^[一二三四五六七八九十\d]{1,3}[、.\-]", "", cleaned)
    return re.sub(r"\s+", "", cleaned).lower()


def normalize_text_for_regex(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = text.replace("：", ":")
    return re.sub(r"\s+", " ", text).strip()


def cleanup_field_value(field: str, value: str) -> str:
    cleaned = value.strip(" ：；，。")
    for stopword in FIELD_STOPWORDS.get(field, ()):
        idx = cleaned.find(stopword)
        if idx != -1:
            cleaned = cleaned[:idx]
    for sep in ("：", ":"):
        if sep in cleaned:
            left, right = cleaned.split(sep, 1)
            if left.strip() and right.strip():
                cleaned = left
                break
    if field == "采购单位名称":
        idx = cleaned.find("行政区域")
        if idx != -1:
            cleaned = cleaned[:idx]
    return cleaned.strip(" ：；，。")


def normalize_date_text(value: str) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    text = re.sub(r"-+", "-", text)
    match = re.search(r"\d{4}-\d{1,2}-\d{1,2}", text)
    candidate = match.group(0) if match else text
    try:
        dt = date_parser.parse(candidate, dayfirst=False, yearfirst=True, fuzzy=True)
        return f"{dt.year:04d}年{dt.month:02d}月{dt.day:02d}日"
    except (ValueError, OverflowError):
        return None


def normalize_amounts(raw: str) -> List[str]:
    if not raw:
        return []
    text = raw.replace(",", "").replace(" ", "")
    text = text.replace("人民币", "").replace("万元整", "万元")
    patterns = re.finditer(r"([\d,.]+)(万元|元)?", text)
    results: List[str] = []
    for match in patterns:
        number, unit = match.groups()
        if not number:
            continue
        number = number.replace(",", "")
        try:
            amount = Decimal(number)
        except InvalidOperation:
            continue
        if unit == "万元":
            amount *= Decimal("10000")
        normalized = f"{amount:.2f}"
        if normalized not in results:
            results.append(normalized)
    return results


def extract_categories(raw: str) -> List[str]:
    if not raw:
        return []
    text = normalize_whitespace(raw).lower()
    detected: List[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            detected.append(category)
    return detected


def label_to_field(label: str) -> Optional[str]:
    normalized = normalize_label_text(label)
    if not normalized:
        return None
    for field, aliases in FIELD_KEYWORDS.items():
        for alias in aliases:
            if normalize_label_text(alias) in normalized:
                return field
    return None


class ProcurementExtractor:
    def __init__(self, soup: BeautifulSoup):
        self.soup = soup
        self.fields = {name: FieldValue(multi=name in MULTI_VALUE_FIELDS) for name in FIELD_ORDER}
        self.counter = 0
        self.full_text = normalize_text_for_regex(soup.get_text("\n"))
        self._processed_tables: Set[int] = set()

    def _next_order(self) -> int:
        self.counter += 1
        return self.counter

    def add_field(self, field: str, raw_value: str) -> None:
        if field not in self.fields or not raw_value:
            return
        if field == "公告时间":
            normalized = normalize_date_text(raw_value)
            values = [normalized] if normalized else []
        elif field == "中标金额":
            values = normalize_amounts(raw_value)
        elif field == "采购类别":
            values = extract_categories(raw_value)
        else:
            cleaned = cleanup_field_value(field, normalize_whitespace(raw_value))
            values = [cleaned] if cleaned else []
        for value in values:
            self.fields[field].add(value, self._next_order())

    def _extract_meta_nodes(self) -> None:
        meta_title = self.soup.find("meta", attrs={"name": re.compile(r"^ArticleTitle$", re.I)})
        if meta_title:
            value = meta_title.get("content") or meta_title.get("value")
            if value:
                self.add_field("项目名称", value)
        meta_date = self.soup.find("meta", attrs={"name": re.compile(r"^PubDate$", re.I)})
        if meta_date:
            value = meta_date.get("content") or meta_date.get("value")
            if value:
                self.add_field("公告时间", value)

    def extract(self) -> Dict[str, str]:
        self._extract_meta_nodes()
        body = self.soup.body or self.soup
        if body:
            self._walk_dom(body)
        self._apply_full_text_patterns()
        result = {field: value.get() for field, value in self.fields.items()}
        if not result["采购类别"]:
            result["采购类别"] = "其他"
        return result

    def _walk_dom(self, node: Tag) -> None:
        for element in node.children:
            if isinstance(element, NavigableString):
                continue
            if not isinstance(element, Tag):
                continue
            if element.name == "table":
                table_id = id(element)
                if table_id not in self._processed_tables:
                    self._processed_tables.add(table_id)
                    self._extract_table(element)
                continue
            if element.find_parent("table") is not None:
                continue
            if element.name in BLOCK_TAGS:
                text = element.get_text(separator="\n", strip=True)
                if text:
                    self._process_text_block(text)
            self._walk_dom(element)

    def _process_text_block(self, text: str) -> None:
        lines = [line.strip() for line in text.replace("\r", "\n").split("\n") if line.strip()]
        if not lines:
            return
        merged: List[str] = []
        skip_next = False
        for idx, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue
            if re.search(r"[；;]$", line) and idx + 1 < len(lines):
                merged.append(f"{line} {lines[idx + 1]}")
                skip_next = True
            else:
                merged.append(line)
        for segment in merged:
            for candidate in re.split(r"[；;]", segment):
                candidate = candidate.strip()
                if not candidate:
                    continue
                match = re.match(r"(.{1,40}?)[：:]\s*(.+)", candidate)
                label = None
                value = None
                if match:
                    label, value = match.group(1), match.group(2)
                else:
                    alt = re.match(r"(.{1,40}?)(供应商名称|供应商地址|采购单位名称|采购单位地址)[：:\s]+(.+)", candidate)
                    if alt:
                        prefix, label, value = alt.groups()
                        if prefix.strip().isdigit():
                            # keep label and value
                            pass
                        else:
                            label = None
                if label and value:
                    field = label_to_field(label)
                    if not field:
                        extra = re.match(r"(.{1,40}?)[：:\s]+(.+)", value)
                        if extra:
                            alt_label, alt_value = extra.groups()
                            field = label_to_field(alt_label)
                            if field:
                                value = alt_value
                    if field:
                        self.add_field(field, value)

    def _extract_table(self, table: Tag) -> None:
        rows = [
            [normalize_whitespace(cell.get_text(separator=" ", strip=True)) for cell in tr.find_all(["th", "td"])]
            for tr in table.find_all("tr")
        ]
        header_map: Dict[int, str] = {}
        ranking_idx: Optional[int] = None
        for row in rows:
            candidate_map = {idx: label_to_field(cell) for idx, cell in enumerate(row)}
            candidate_map = {idx: field for idx, field in candidate_map.items() if field}
            if not header_map and candidate_map:
                if len(candidate_map) >= 2 or len(row) > 2:
                    header_map = candidate_map
                    for idx, cell in enumerate(row):
                        if normalize_label_text(cell) in {normalize_label_text(x) for x in TABLE_RANK_HEADERS}:
                            ranking_idx = idx
                            break
                    continue
            if header_map:
                if ranking_idx is not None and ranking_idx < len(row):
                    rank_norm = normalize_label_text(row[ranking_idx])
                    if rank_norm not in {normalize_label_text(x) for x in TABLE_RANK_ACCEPT}:
                        continue
                for idx, field in header_map.items():
                    if idx < len(row):
                        value = row[idx]
                        if label_to_field(value):
                            continue
                        self.add_field(field, value)
            if len(row) >= 2:
                if ranking_idx is not None and ranking_idx < len(row):
                    rank_norm = normalize_label_text(row[ranking_idx])
                    if rank_norm not in {normalize_label_text(x) for x in TABLE_RANK_ACCEPT}:
                        continue
                for idx in range(0, len(row) - 1, 2):
                    field = label_to_field(row[idx])
                    if field:
                        self.add_field(field, row[idx + 1])

    def _apply_full_text_patterns(self) -> None:
        for field, patterns in FULL_TEXT_PATTERNS.items():
            if self.fields[field].entries:
                continue
            for pattern in patterns:
                for match in pattern.finditer(self.full_text):
                    value = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
                    self.add_field(field, value)
                    if self.fields[field].entries and not self.fields[field].multi:
                        break
                if self.fields[field].entries and not self.fields[field].multi:
                    break


def build_record(path: Path) -> Dict[str, str]:
    soup = BeautifulSoup(read_html_text(path), "lxml")
    extractor = ProcurementExtractor(soup)
    return extractor.extract()


def extract_directory(input_dir: Path) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    records: List[Dict[str, str]] = []
    stats = {"total": 0, "success": 0, "failed": 0}
    for html_file in sorted(input_dir.rglob("*.htm*")):
        stats["total"] += 1
        try:
            record = build_record(html_file)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to process %s: %s", html_file, exc)
            stats["failed"] += 1
            continue
        records.append(record)
        stats["success"] += 1
    return records, stats


def write_outputs(records: Sequence[Dict[str, str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "extracted.csv"
    jsonl_path = output_dir / "extracted.jsonl"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(FIELD_ORDER))
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in FIELD_ORDER})

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        for record in records:
            jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量提取 HTML 公告中的采购信息")
    parser.add_argument("--input", type=Path, default=Path("./data"), help="输入目录 (默认: ./data)")
    parser.add_argument("--output", type=Path, default=Path("./result"), help="输出目录 (默认: ./result)")
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    records, stats = extract_directory(args.input)
    LOGGER.info("Processed %d files: %d succeeded, %d failed", stats["total"], stats["success"], stats["failed"])

    if records:
        write_outputs(records, args.output)
        LOGGER.info("Results written to %s", args.output)
    else:
        LOGGER.warning("No records extracted; outputs not written.")


if __name__ == "__main__":
    main()

