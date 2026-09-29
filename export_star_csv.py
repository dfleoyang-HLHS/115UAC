"""把 star115.db 依使用者指定的三個紅框整理成一列一校系的寬表 CSV。"""
import csv
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "star115.db"
OUT = sys.argv[2] if len(sys.argv) > 2 else "star115_校系分則.csv"

SUBJECTS = [("國文", "subj_chinese"), ("英文", "subj_english"), ("數學A", "subj_math_a"),
            ("數學B", "subj_math_b"), ("社會", "subj_social"), ("自然", "subj_science"),
            ("英聽", "subj_english_listening")]


def zero(v):
    v = (v or "").strip()
    return "0" if v in ("", "--", "－－", "—", "無") else v


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
depts = conn.execute("SELECT * FROM departments ORDER BY code").fetchall()

dist = {}
for r in conn.execute("SELECT * FROM distribution_items ORDER BY code, seq"):
    dist.setdefault(r["code"], []).append(r["item_text"])
max_dist = max((len(v) for v in dist.values()), default=0)

skill = {}
for r in conn.execute("SELECT * FROM skill_test_items"):
    skill.setdefault(r["code"], []).append(f"{r['item_name']}:{r['standard']}")

instr = {}
for r in conn.execute("SELECT * FROM major_instruments"):
    instr.setdefault(r["code"], []).append(f"{r['instrument']}(名額{r['quota']},外加{r['extra_quota']})")

header = ["校系代碼", "學校", "系組名稱", "學群類別", "招生名額", "招生名額可填志願數",
          "外加名額", "外加名額可填志願數"]
header += [f"{s}_標準" for s, _ in SUBJECTS]
header += [f"分發比序{i}" for i in range(1, max_dist + 1)]
header += ["分發比序項目(彙整)", "術科檢定", "依主修樂器招生名額",
           "醫牙_指定項目", "醫牙_指定項目佔比", "醫牙_預計甄試人數", "醫牙_甄試費", "備註"]

with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(header)
    for d in depts:
        c = d["code"]
        row = [c, d["school"], d["dept_name"], d["group_type"], d["admit_quota"],
               zero(d["admit_choices"]), zero(d["extra_quota"]), zero(d["extra_choices"])]
        row += [zero(d[col]) for _, col in SUBJECTS]
        items = dist.get(c, [])
        row += items + [""] * (max_dist - len(items))
        row.append(" ".join(f"{i}、{t}" for i, t in enumerate(items, 1)))
        row += ["；".join(skill.get(c, [])), "；".join(instr.get(c, [])),
                d["designated_item"] or "", d["designated_item_pct"] or "",
                d["expected_interview_quota"] or "", d["interview_fee"] or "", d["notes"] or ""]
        w.writerow(row)

print(f"寫出 {len(depts)} 列，{len(header)} 欄，分發比序最多 {max_dist} 項 -> {OUT}")
