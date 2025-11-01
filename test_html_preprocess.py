#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 html_preprocess 模块 - 随机选取一个文件进行处理"""

import random
from pathlib import Path
from html_preprocess import convert_html_file
from html_preprocess import collect_html_paths
from typing import List
input_dir = Path("./data")
files = [p for p in input_dir.rglob('*') if p.is_dir()]
print(f"检测到 {len(files)} 个文件夹，随机选取其中一个进行处理")
print("文件夹列表示例：", files[:5])

def process_folder(folder: Path) -> List[Path]:
    html_files = collect_html_paths(folder)
    return html_files

for p in files:
    html_files = process_folder(p)
    for html_file in html_files:
        html_text = convert_html_file(html_file)
        print(f"处理文件: {html_file}")
        with open(f"html2md/{html_file.stem}.txt", "w", encoding="utf-8") as f:
            f.write(html_text)