"""離島地區及原住民高級中等學校應屆畢業生升學國(市)立師範及教育大學聯合保送甄試（離原聯保）
簡章的校系分則 → CSV。

這個管道的校系代碼是保送專用代碼（如 ZTZ01、AAC01），與繁星推薦、申請入學、分發入學的校系代碼不同，
不與其他管道的資料合併，另存一份。每一個「保送名額」（學校＋學系＋族語別＋保送縣市＋身分別）一列。
一般校系表格 6 欄；術科類（音樂、體育）多了學測佔比與術科項目、採計、佔比，共 10 欄。

用法：uv run --with pdfplumber --no-binary-package charset-normalizer python parse_jracoia.py <簡章.pdf> <學年度>
輸出：{學年度}離原聯保_校系分則.csv
"""
import csv
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

HERE = Path(__file__).parent
PDF, YEAR = Path(sys.argv[1]), sys.argv[2]
OUT = HERE / f"{YEAR}離原聯保_校系分則.csv"
SUBJ = ["國文", "英文", "數學A", "數學B", "社會", "自然"]
LABELS = {"族語別", "保送縣市", "身分別", "招生名額", "校系代碼"}


def clean(v):
    # 只把 CJK 相容表意字（外觀相同、編碼不同）轉成標準字，全形標點保持原樣
    v = "".join(unicodedata.normalize("NFKC", c) if 0xF900 <= ord(c) <= 0xFAFF or 0x2F00 <= ord(c) <= 0x2FDF else c
                for c in (v or ""))
    return re.sub(r"\s+", " ", v).strip()


def split_list(text):
    return [re.sub(r"^\d+\.\s*", "", x.strip()).replace(" ", "") for x in re.split(r"(?=(?:^|\s)\d+\.\s)", text) if x.strip()]


rows = []
with pdfplumber.open(PDF) as pdf:
    for page in pdf.pages:
        for t in page.extract_tables():
            if not t or len(t[0]) < 6 or "學測檢定方式" not in (t[0][2] or ""):
                continue
            skill = len(t[0]) >= 10                       # 術科類表格
            tie_col = 9 if skill else 5
            rec = {"學校": clean(t[0][0]), "學系": "", "std": {}, "w": {}, "tie": [], "note": "",
                   "pct": "", "sk": [], "skpct": ""}
            for r in t[1:]:
                r = [clean(c) for c in r] + [""] * 10
                if r[0] in LABELS:
                    rec[r[0]] = r[1].replace(" ", "")
                elif r[0] == "備註":
                    rec["note"] = r[2]
                elif not rec["std"] and r[0]:
                    rec["學系"] += r[0].replace(" ", "")          # 系名可能跨兩列（如「公民教育與活動領導」「學系」）
                subj = r[2].replace(" ", "")
                if subj in SUBJ:
                    rec["std"][subj] = r[3]
                    rec["w"][subj] = re.sub(r"^[xX]", "", r[4]) if r[4] not in ("", "--") else "--"
                    if skill:
                        rec["pct"] = rec["pct"] or r[5]
                        if r[6]:
                            rec["sk"].append(f"{r[6].replace(' ', '')}×{re.sub(r'^[xX]', '', r[7])}")
                        rec["skpct"] = rec["skpct"] or r[8]
                if r[tie_col] and re.match(r"1\.", r[tie_col]):
                    rec["tie"] = split_list(r[tie_col])
            rows.append(rec)

head = ["學年度", "類別", "校系代碼", "學校", "學系", "族語別", "保送縣市", "身分別", "招生名額"]
head += [f"檢定_{s}" for s in SUBJ] + [f"採計_{s}" for s in SUBJ] + ["學測佔總成績比例", "術科採計", "術科佔總成績比例"]
head += [f"同分參酌{i}" for i in range(1, 7)] + ["需求專長與分發", "備註"]
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(head)
    for r in rows:
        note = r["note"]
        m = re.search(r"1\.\s*需求專長[:：]\s*(.+?)(?=\s2\.|$)", note)
        need = m.group(1).strip() if m else ""
        # PDF 換行在中文字之間留下的空格
        cjk = r"[一-鿿，；。、：（）()\-]"
        need = re.sub(rf"(?<={cjk})\s+(?={cjk})", "", need)
        note = re.sub(rf"(?<={cjk})\s+(?={cjk})", "", note)
        kind = "離島" if r.get("身分別") == "離島" else "原住民"
        tie = r["tie"] + [""] * (6 - len(r["tie"]))
        w.writerow([YEAR, kind, r.get("校系代碼", ""), r["學校"], r["學系"], r.get("族語別", ""), r.get("保送縣市", ""),
                    r.get("身分別", ""), r.get("招生名額", "")]
                   + [r["std"].get(s, "--") or "--" for s in SUBJ] + [r["w"].get(s, "--") or "--" for s in SUBJ]
                   + [r["pct"], "、".join(r["sk"]), r["skpct"]] + tie[:6] + [need, note])
print(f"{len(rows)} 個保送名額（離島 {sum(1 for r in rows if r.get('身分別') == '離島')}、"
      f"原住民 {sum(1 for r in rows if r.get('身分別') != '離島')}），"
      f"名額合計 {sum(int(r.get('招生名額') or 0) for r in rows)} -> {OUT.name}")
