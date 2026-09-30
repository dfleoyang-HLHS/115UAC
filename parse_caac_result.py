"""四技申請入學「各校系(組)、學程第一階段最低篩選標準」PDF → CSV。

學測成績最低篩選標準為「加權平均級分 ÷ 15 × 100」的百分制分數
（例：臺科大營建系 74.29 × 權重 7 × 15 ÷ 100 = 78 級分總和）。
用法：uv run --with pdfplumber --no-binary-package charset-normalizer python parse_caac_result.py <pdf> <學年度>
輸出：{學年度}四技申請_篩選標準.csv
"""
import csv
import re
import sys
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
PDF, YEAR = Path(sys.argv[1]), sys.argv[2]
OUT = HERE / f"{YEAR}四技申請_篩選標準.csv"


def c(v):
    return re.sub(r"\s+", "", v or "")


rows = []
with pdfplumber.open(PDF) as pdf:
    for page in pdf.pages:
        for t in page.extract_tables():
            for r in t:
                r = list(r) + [None] * 6
                if re.fullmatch(r"\d{6}", c(r[0])):
                    dash = lambda v: "" if c(v) in ("", "--") else c(v)
                    rows.append([YEAR, c(r[0]), c(r[1]), c(r[2]), dash(r[3]), dash(r[4]), dash(r[5])])
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["學年度", "志願代碼", "學校", "系組名稱", "學測成績最低篩選標準", "APCS超額篩選最低標準級分", "APCS超額篩選標準加權成績"])
    w.writerows(rows)
print(f"{YEAR}：{len({r[2] for r in rows})} 所學校、{len(rows)} 個系組，APCS {sum(1 for r in rows if r[5])} 個，"
      f"無篩選標準 {sum(1 for r in rows if not r[4])} 個 -> {OUT.name}")
