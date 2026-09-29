"""解析「114 學年度大學分發入學招生簡章」校系分則（簡章第 19~224 頁）成 CSV。

用法: uv run --with pdfplumber python parse_recruit_pdf.py <pdf路徑> [輸出csv] [起始頁] [結束頁] [頁碼偏移]
簡章頁碼 N 對應 PDF 第 N+偏移 頁（0 起算的 index）。
  114 學年度：第 19~224 頁，偏移 6（預設值）
  115 學年度：第 19~261 頁，偏移 4
"""
import csv
import re
import sys
import unicodedata

import pdfplumber

PDF = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\user\Downloads\114recruit_s.pdf"
OUT = sys.argv[2] if len(sys.argv) > 2 else "114分發入學_校系分則.csv"
FIRST = int(sys.argv[3]) if len(sys.argv) > 3 else 19
LAST = int(sys.argv[4]) if len(sys.argv) > 4 else 224
OFFSET = int(sys.argv[5]) if len(sys.argv) > 5 else 6

EMPTY = {"", "-", "--", "---", "----"}


def norm(s):
    """全形轉半形、去掉中文字間多餘空白（「國 文」→「國文」，「數學 A」→「數學A」）。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[^\x00-\x7f]) (?=[^\x00-\x7f])", "", s)
    s = re.sub(r"(?<=[^\x00-\x7f]) (?=[A-Za-z(])", "", s)
    s = re.sub(r"(?<=[A-Za-z]) (?=\()", "", s)
    return s


def split_standards(cell):
    """把檢定標準 cell 拆成多個條件：依「1.」「2.」編號切開；「或」連接的算同一條件。"""
    txt = norm(cell)
    if txt in EMPTY:
        return []
    parts = re.split(r"(?:^|\s)\d+\.\s*", txt)
    out = [re.sub(r"\s*或\s*", " 或 ", p.strip()) for p in parts if p.strip() and p.strip() not in EMPTY]
    return out


def parse_subject(cell):
    """「國 文(學測) x 1.50」→ ("國文(學測)", "1.50")"""
    txt = norm(cell)
    if txt in EMPTY:
        return None
    m = re.match(r"^(.*?)\s*[x×X]\s*([\d.]+)\s*$", txt)
    if m:
        return m.group(1).strip(), m.group(2)
    return txt, ""


# 表頭關鍵字 → 欄位名稱；114 年只有 5 欄，115 年多了系組代碼、核定名額、原民外加、其他各類外加
HEAD_KEYS = [("學系", "dept"), ("代碼", "code"), ("核定", "quota"), ("原民", "indig"),
             ("其他", "other"), ("檢定", "std"), ("採計", "sub"), ("同分", "tie"), ("選系", "note")]
DEFAULT_COLS = {"dept": 0, "std": 1, "sub": 2, "tie": 3, "note": 4}
EXTRA_FIELDS = [("code", "系組代碼"), ("quota", "核定名額"), ("indig", "原民外加"), ("other", "其他各類外加")]


def header_map(row):
    cols = {}
    for i, c in enumerate(row):
        t = norm(c).replace(" ", "")
        for key, name in HEAD_KEYS:
            if key in t and name not in cols:
                cols[name] = i
                break
    return cols


def main():
    pdf = pdfplumber.open(PDF)
    depts = []
    school = school_code = ""
    cur = None
    cols = dict(DEFAULT_COLS)
    for pno in range(FIRST, LAST + 1):
        page = pdf.pages[pno + OFFSET]
        for table in page.extract_tables():
            for row in table:
                row = list(row) + [None] * 12
                c0 = row[0] or ""
                m = re.search(r"校名[:：]\s*(.+?)\s*\((\d+)\)", norm(c0))
                if m:
                    school, school_code = m.group(1), m.group(2)
                    continue
                if norm(c0).replace(" ", "").startswith("學系"):
                    cols = header_map(row)
                    continue
                if re.fullmatch(r"\d+|本頁以下空白.*|其他各類外加分別.*|註.*", norm(c0)):
                    continue
                get = lambda k: row[cols[k]] if k in cols else None
                if c0 and norm(c0):
                    cur = {"school": school, "school_code": school_code, "dept": norm(c0).replace(" ", ""),
                           "extra": {k: norm(get(k)) for k, _ in EXTRA_FIELDS if k in cols},
                           "standards": [], "subjects": [], "note": [], "page": pno}
                    depts.append(cur)
                if cur is None:
                    continue
                if get("std"):
                    cur["standards"] += split_standards(get("std"))
                tie = norm(get("tie"))
                if get("sub"):
                    sub = parse_subject(get("sub"))
                    if sub:
                        cur["subjects"].append([sub[0], sub[1], tie if tie not in EMPTY else ""])
                elif tie and tie not in EMPTY and cur["subjects"]:
                    cur["subjects"][-1][2] = tie
                if get("note"):
                    cur["note"].append(get("note").replace("\n", ""))

    extra_keys = [(k, n) for k, n in EXTRA_FIELDS if any(k in d["extra"] for d in depts)]
    max_std = max(len(d["standards"]) for d in depts)
    max_sub = max(len(d["subjects"]) for d in depts)
    header = ["校名", "學校代碼", "學系"] + [n for _, n in extra_keys]
    header += [f"檢定標準{i}" for i in range(1, max_std + 1)]
    for i in range(1, max_sub + 1):
        header += [f"採計科目{i}", f"加權倍率{i}", f"同分參酌順序{i}"]
    header += ["選系說明", "簡章頁碼"]

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for d in depts:
            row = [d["school"], d["school_code"], d["dept"]] + [d["extra"].get(k, "") for k, _ in extra_keys]
            row += d["standards"] + [""] * (max_std - len(d["standards"]))
            for s in d["subjects"]:
                row += s
            row += ["", "", ""] * (max_sub - len(d["subjects"]))
            row += ["".join(d["note"]), d["page"]]
            w.writerow(row)
    schools = {d["school_code"] for d in depts}
    print(f"{len(schools)} 所學校，{len(depts)} 個學系，檢定標準最多 {max_std} 項，採計科目最多 {max_sub} 科 -> {OUT}")


if __name__ == "__main__":
    main()
