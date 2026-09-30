"""115 學年度大學分發入學「各系組最低錄取標準及錄取人數一覽表」PDF → CSV。

用法：uv run --with pdfplumber --no-binary-package charset-normalizer python parse_uac_result.py [pdf] [輸出csv]
（charset-normalizer 用純 Python 版本，避免 Windows 應用程式控制原則封鎖其 DLL）
"""
import csv
import re
import sys
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "115_result_school_data.pdf"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "115分發入學_錄取結果.csv"
# 採計科目縮寫 → 全名（與 115 分發入學校系分則一致）
ABBR = {"國": "國文(學測)", "英": "英文(學測)", "數A": "數學A(學測)", "數B": "數學B(學測)", "社": "社會(學測)",
        "自": "自然(學測)", "數甲": "數學甲(分科)", "數乙": "數學乙(分科)", "物": "物理(分科)", "化": "化學(分科)",
        "生": "生物(分科)", "歷": "歷史(分科)", "地": "地理(分科)", "公": "公民與社會(分科)",
        "音": "音樂(術科)", "美": "美術(術科)", "體": "體育(術科)"}
SPECIAL = ["原住民", "退伍軍人", "僑生", "蒙藏生", "派外子女"]
# PDF 把術科一律寫成「術」，依序以下列方式補全為 音樂／美術／體育(術科)：
#   1. 同學年度分發校系分則（115 年以系組代碼、114 年以「校名|學系」對應）
#   2. 其他學年度分則中同校同系名的術科（例如 113 年沒有分則，借用 114、115 年）
#   3. 依系名關鍵字判斷
SKILL, OTHER = {}, {}
YEAR_OF_OUT = OUT.name[:3]
for rule in sorted(HERE.glob("*分發入學_校系分則.csv")):
    same = rule.name.startswith(YEAR_OF_OUT)
    for x in csv.DictReader(open(rule, encoding="utf-8-sig")):
        for i in range(1, 6):
            if "(術科)" in x.get(f"採計科目{i}", ""):
                if same:
                    SKILL[x.get("系組代碼") or f"{x['校名']}|{x['學系']}"] = x[f"採計科目{i}"]
                OTHER[f"{x['校名']}|{x['學系']}"] = x[f"採計科目{i}"]


def guess_skill(dept):
    if "音樂" in dept:
        return "音樂(術科)"
    if re.search(r"體育|運動|競技", dept):
        return "體育(術科)"
    if re.search(r"美術|設計|雕塑|書畫|工藝|視覺|藝術", dept):
        return "美術(術科)"
    return "術科"


def clean(v):
    v = re.sub(r"\s+", " ", (v or "")).strip()
    return "" if re.fullmatch(r"-+", v) else v


rows = []
with pdfplumber.open(PDF) as pdf:
    for pno, page in enumerate(pdf.pages, 1):
        for table in page.extract_tables():
            for r in table:
                if not r or not re.fullmatch(r"\d{4}", (r[0] or "").strip()):
                    continue
                r = [clean(c) for c in r] + [""] * (12 - len(r))
                weights = re.findall(r"(\S+?)x([\d.]+)", r[3])
                tie = r[6].split(" ") if r[6] else []
                rows.append({"code": r[0], "school": r[1], "dept": r[2].replace(" ", ""), "weights": weights,
                             "n": r[4], "score": r[5], "tie_s": tie[0] if tie else "", "tie_v": tie[1] if len(tie) > 1 else "",
                             "special": r[7:12], "page": pno})

maxw = max(len(x["weights"]) for x in rows)
head = ["系組代碼", "校名", "系組名"]
for i in range(1, maxw + 1):
    head += [f"採計科目{i}", f"加權{i}"]
head += ["錄取人數(含外加)", "普通生錄取分數", "普通生同分參酌科目", "普通生同分參酌分數"]
head += [f"{s}錄取分數" for s in SPECIAL] + ["頁碼"]
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(head)
    for x in rows:
        row = [x["code"], x["school"], x["dept"]]
        # 錄取結果的系名可能多了「(男)」「(女)」或「-鋼琴.聲樂…」等分組字樣，去掉後再對應分則
        base = re.sub(r"\((男|女)\)$", "", x["dept"].split("-")[0])
        sk = (SKILL.get(x["code"]) or SKILL.get(f"{x['school']}|{x['dept']}") or SKILL.get(f"{x['school']}|{base}")
              or OTHER.get(f"{x['school']}|{x['dept']}") or OTHER.get(f"{x['school']}|{base}") or guess_skill(x["dept"]))
        for i in range(maxw):
            if i < len(x["weights"]):
                s, m = x["weights"][i]
                row += [sk if s == "術" else ABBR.get(s, s), m]
            else:
                row += ["", ""]
        tie = sk if x["tie_s"] == "術" else ABBR.get(x["tie_s"], x["tie_s"])
        row += [x["n"], x["score"], tie, x["tie_v"]] + x["special"] + [x["page"]]
        w.writerow(row)
print(f"{len({x['school'] for x in rows})} 所學校，{len(rows)} 個系組，採計科目最多 {maxw} 科 -> {OUT.name}")
