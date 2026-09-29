"""把 apply115.db 依使用者指定的六個紅框整理成一列一校系的寬表 CSV。"""
import csv
import re
import sqlite3
import sys
from collections import OrderedDict

DB = sys.argv[1] if len(sys.argv) > 1 else "apply115.db"
OUT = sys.argv[2] if len(sys.argv) > 2 else "apply115_校系分則.csv"

SUBJECTS = ["國文", "英文", "數學A", "數學B", "社會", "自然", "英聽"]
NUMS = "一二三四五六七八九十"


def zero(v):
    v = (v or "").strip()
    return "0" if v in ("", "--", "－－", "—", "無") else v


def num(v):
    """倍率/採計/比例：--或空白寫 0，去掉 * 與 % 以方便計算。"""
    v = zero(v)
    return v.replace("*", "").replace("%", "").strip() or "0"


def ordinal_join(items):
    return " ".join(f"{NUMS[i] if i < 10 else i + 1}、{t}" for i, t in enumerate(items))


def norm_item(name):
    return re.sub(r"\s+", "", name)


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
depts = conn.execute("SELECT * FROM departments ORDER BY code").fetchall()

subj = {}
for r in conn.execute("SELECT * FROM subject_screening"):
    name = r["subject_name"].replace("Ａ", "A").replace("Ｂ", "B")
    subj.setdefault(r["code"], {})[name] = r

items = {}
item_order = OrderedDict()
for r in conn.execute("SELECT * FROM designated_items ORDER BY code, seq"):
    n = norm_item(r["item_name"])
    items.setdefault(r["code"], {})[n] = r
    item_order[n] = item_order.get(n, 0) + 1
# 審查資料、語文測驗筆試、寫作筆試優先，其餘依出現次數排序
preferred = ["審查資料", "語文測驗筆試", "寫作筆試"]
item_cols = [p for p in preferred if p in item_order] + sorted(
    (k for k in item_order if k not in preferred), key=lambda k: -item_order[k]
)

skill = {}
for r in conn.execute("SELECT * FROM skill_test_screening ORDER BY code, seq"):
    skill.setdefault(r["code"], []).append(r)

overall = {}
for r in conn.execute("SELECT * FROM overall_tiebreak_items ORDER BY code, seq"):
    overall.setdefault(r["code"], []).append(r["item_text"])

stage1 = {}
for r in conn.execute("SELECT * FROM stage1_tiebreak_items ORDER BY code, seq"):
    stage1.setdefault(r["code"], []).append(r["item_text"])

apcs = {}
for r in conn.execute("SELECT * FROM extra_screening"):
    apcs.setdefault(r["code"], {})[r["item_name"]] = r

review = {}
for r in conn.execute("SELECT * FROM designated_item_details"):
    if "審查" in r["item_name"]:
        review.setdefault(r["code"], []).append(r["description"])

header = [
    "校系代碼", "學校", "系組名稱", "類別", "招生名額", "性別要求", "預計甄試人數",
    "原住民外加名額", "離島外加名額", "離島外加名額縣市限制", "願景計畫外加名額",
    "指定項目甄試費", "指定項目甄試日期", "是否要參加術科考試", "是否有扶弱措施",
]
for s in SUBJECTS:
    header += [f"{s}_檢定", f"{s}_篩選倍率"]
for s in SUBJECTS:
    header.append(f"{s}_學測採計方式")
header.append("學測成績佔甄選總成績比例")
for it in item_cols:
    header += [f"{it}_檢定", f"{it}_佔甄選總成績比例"]
header += ["APCS程式識讀_檢定", "APCS程式識讀_篩選倍率", "APCS程式實作_檢定", "APCS程式實作_篩選倍率"]
header += ["術科項目", "甄選總成績同分參酌之順序", "審查資料內容", "同級分(分數)超額篩選方式", "組合科目篩選(級分總和)"]

with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(header)
    for d in depts:
        c = d["code"]
        row = [
            c, d["school"], d["dept_name"], d["category"], d["admit_quota"],
            d["gender_requirement"], d["expected_interview_quota"],
            zero(d["indigenous_extra_quota"]), zero(d["offshore_extra_quota"]),
            d["offshore_extra_note"], zero(d["vision_extra_quota"]),
            d["interview_fee"], (d["exam_date"] or "").replace("; ", ""), d["skill_test_required"], d["disadvantaged_support"],
        ]
        ss = subj.get(c, {})
        for s in SUBJECTS:
            r = ss.get(s)
            row += [zero(r["standard"]) if r else "0", num(r["multiplier"]) if r else "0"]
        for s in SUBJECTS:
            r = ss.get(s)
            row.append(num(r["stage2_weight"]) if r else "0")
        row.append(num(d["stage1_overall_pct"]))
        ii = items.get(c, {})
        for it in item_cols:
            r = ii.get(it)
            row += [zero(r["standard"]) if r else "0", num(r["pct"]) if r else "0"]
        ap = apcs.get(c, {})
        for k in ("程式識讀", "程式實作"):
            r = ap.get(k)
            row += [zero(r["standard"]) if r else "0", num(r["multiplier"]) if r else "0"]
        sk = [r for r in skill.get(c, []) if r["item_name"] not in ("--", "")]
        row.append("；".join(
            f"{r['item_name']}(檢定:{zero(r['standard'])},倍率:{num(r['multiplier'])},採計:{num(r['stage2_weight'])})"
            for r in sk) + (f"；佔總成績{sk[0]['pct']}" if sk and sk[0]["pct"] else ""))
        row.append(ordinal_join(overall.get(c, [])))
        row.append("\n".join(review.get(c, [])))
        row.append(ordinal_join(stage1.get(c, [])))
        extra = [k for k in ss if k not in SUBJECTS and k != "--"]
        row.append("；".join(f"{k}(檢定:{zero(ss[k]['standard'])},倍率:{num(ss[k]['multiplier'])})" for k in extra))
        w.writerow(row)

print(f"寫出 {len(depts)} 列，{len(header)} 欄，指定項目種類 {len(item_cols)} 種 -> {OUT}")
