#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 html_preprocess 模块 - 随机选取一个文件进行处理"""

import random
from pathlib import Path
from html_preprocess import convert_html_file
from html_preprocess import collect_html_paths

input_dir = Path("./data")
files = [p for p in input_dir.rglob('*') if p.is_dir()]

for p in files:
    html_file = collect_html_paths(p)
    html_text = convert_html_file(html_file[0])
    print(f"处理文件: {html_file[0]}")
    with open(f"html2md/{html_file[0].stem}.txt", "w", encoding="utf-8") as f:
        f.write(html_text)