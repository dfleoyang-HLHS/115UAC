"""衛生福利部「原住民族及離島地區醫事人員養成計畫」公費生學士班甄試簡章的「招生系別、修業年限及名額」表 → CSV。

校系代碼：第 1 碼學校、第 2～3 碼學系、第 4 碼籍屬（1 原住民、2 澎湖縣、3 金門縣、4 連江縣、5 琉球鄉、6 綠島鄉、7 蘭嶼鄉、8 偏鄉），
自成一套，與其他管道的校系代碼不同。
用法：uv run --with pdfplumber --no-binary-package charset-normalizer python parse_med_quota.py <簡章.pdf> <學年度>
輸出：{學年度}醫事人員養成計畫_校系名額.csv
"""
import csv
import re
import sys
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
PDF, YEAR = Path(sys.argv[1]), sys.argv[2]
OUT = HERE / f"{YEAR}醫事人員養成計畫_校系名額.csv"


def c(v):
    return re.sub(r"\s+", "", v or "")


rows, school, dept, years = [], "", "", ""
with pdfplumber.open(PDF) as pdf:
    for page in pdf.pages[:10]:
        for t in page.extract_tables():
            if not t or c(t[0][0]) != "校名":
                continue
            for r in t[2:]:
                r = list(r) + [None] * 9
                if c(r[0]):
                    school = c(r[0])
                if c(r[1]):
                    dept, years = c(r[1]), c(r[2])
                code = c(r[6])
                if re.fullmatch(r"[A-Z]\d{3}", code):
                    rows.append([YEAR, school, dept, years, c(r[5]), code, c(r[7])])
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["學年度", "學校", "學系", "修業年限", "籍屬身分", "校系代碼", "招生名額"])
    w.writerows(rows)
print(f"{len({r[1] for r in rows})} 所學校、{len(rows)} 個校系名額列，名額合計 {sum(int(r[6]) for r in rows)} -> {OUT.name}")
