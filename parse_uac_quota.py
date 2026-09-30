"""大學分發入學「校系條件與招生名額錄取人數一覽表」PDF（例如 114_05.pdf）→ 合併進 {學年度}分發入學_錄取結果.csv。

這份報表有檢定科目及標準、英聽、採計科目及加權、同分參酌順序、核定／回流／招生名額、錄取與外加錄取的男女人數，
但沒有錄取分數；錄取分數仍來自「各系組最低錄取標準及錄取人數一覽表」（例如 114_04.pdf）。
兩份以同一學年度的系組代碼合併。

用法：uv run --with pdfplumber --no-binary-package charset-normalizer python parse_uac_quota.py <pdf> <學年度>
"""
import csv
import re
import sys
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
PDF = Path(sys.argv[1])
YEAR = sys.argv[2]
TARGET = HERE / f"{YEAR}分發入學_錄取結果.csv"
NEW = ["檢定標準1", "檢定標準2", "檢定標準3", "英聽檢定", "同分參酌順序", "核定名額", "回流名額", "招生名額",
       "錄取人數_男", "錄取人數_女", "外加錄取_男", "外加錄取_女", "錄取總人數"]


def clean(v):
    return re.sub(r"\s+", " ", (v or "")).strip()


info = {}
with pdfplumber.open(PDF) as pdf:
    for page in pdf.pages:
        for table in page.extract_tables():
            for r in table:
                if not r or not re.fullmatch(r"\d{4}", clean(r[0])):
                    continue
                r = [clean(c) for c in r] + [""] * (15 - len(r))
                # 檢定：「1.英文(前標) 2.數學A(前標) 或數學B(前標)」→ 依編號拆開，「或」連接的算同一項
                std = [re.sub(r"\s*或\s*", " 或 ", p.strip()) for p in re.split(r"(?:^|\s)\d+\.\s*", r[2]) if p.strip()]
                info[r[0]] = {"name": r[1].replace(" ", ""), "std": std, "listen": r[4], "tie": r[6].replace(" ", "→"),
                              "nums": r[7:15]}

rows = list(csv.reader(open(TARGET, encoding="utf-8-sig")))
head = [h for h in rows[0] if h not in NEW]
keep = [i for i, h in enumerate(rows[0]) if h in head]
out, miss, name_diff = [], [], []
for r in rows[1:]:
    base = [r[i] for i in keep]
    x = info.pop(base[0], None)
    if not x:
        miss.append(base[0])
        out.append(base + [""] * len(NEW))
        continue
    if x["name"] != base[2].replace(" ", ""):
        name_diff.append((base[0], base[2], x["name"]))
    std = x["std"] + [""] * (3 - len(x["std"]))
    out.append(base + std[:3] + [x["listen"], x["tie"]] + x["nums"])
with open(TARGET, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(head + NEW)
    w.writerows(out)
print(f"{TARGET.name}：合併 {len(out) - len(miss)} 列；錄取分數表有但條件表沒有 {len(miss)} 列 {miss[:8]}；"
      f"條件表有但錄取分數表沒有 {len(info)} 列 {list(info)[:8]}；同代碼但系名不同 {len(name_diff)} 列 {name_diff[:5]}")
