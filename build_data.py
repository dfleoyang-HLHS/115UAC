"""把 star115.db / apply115.db 整理成網頁用的 data.js（index.html 會載入）。"""
import csv
import json
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
SUBJ = ["國文", "英文", "數學A", "數學B", "社會", "自然", "英聽"]
STAR_COLS = ["subj_chinese", "subj_english", "subj_math_a", "subj_math_b",
             "subj_social", "subj_science", "subj_english_listening"]


def std(v):
    v = (v or "").strip()
    return "" if v in ("", "--") else v


def pct_num(v):
    m = re.search(r"(\d+(?:\.\d+)?)", v or "")
    return float(m.group(1)) if m else None


# ---------- 繁星推薦 ----------
school_pct = json.loads((HERE / "star_school_pct.json").read_text(encoding="utf-8"))
c = sqlite3.connect(HERE / "star115.db")
c.row_factory = sqlite3.Row
dist = {}
for r in c.execute("SELECT code, item_text FROM distribution_items ORDER BY code, seq"):
    dist.setdefault(r["code"], []).append(r["item_text"])
skill = {}
for r in c.execute("SELECT code, item_name, standard FROM skill_test_items"):
    skill.setdefault(r["code"], []).append(f"{r['item_name']}:{r['standard']}")
star = []
for d in c.execute("SELECT * FROM departments ORDER BY code"):
    colno = d["source_group_pages"]
    star.append({
        "c": d["code"], "s": d["school"], "d": d["dept_name"], "g": d["group_type"],
        "q": d["admit_quota"], "ch": d["admit_choices"],
        "eq": d["extra_quota"], "ech": d["extra_choices"],
        "std": {s: std(d[col]) for s, col in zip(SUBJ, STAR_COLS) if std(d[col])},
        "rk": pct_num(school_pct.get(colno, "")),
        "dist": dist.get(d["code"], []),
        "sk": "；".join(skill.get(d["code"], [])),
        "iv": (f"{d['designated_item']} {d['designated_item_pct']}".strip()
               if d["designated_item"] else ""),
    })

# ---------- 個人申請 ----------
a = sqlite3.connect(HERE / "apply115.db")
a.row_factory = sqlite3.Row
subs = {}
for r in a.execute("SELECT * FROM subject_screening"):
    if r["subject_name"] == "--":
        continue
    subs.setdefault(r["code"], []).append(
        [r["subject_name"], std(r["standard"]), std(r["multiplier"]), std(r["stage2_weight"]).replace("*", "")])
items = {}
for r in a.execute("SELECT * FROM designated_items ORDER BY code, seq"):
    items.setdefault(r["code"], []).append(f"{r['item_name']} {r['pct']}".strip())
apcs = {}
for r in a.execute("SELECT * FROM extra_screening ORDER BY code, seq"):
    apcs.setdefault(r["code"], []).append(f"{r['item_name']}:{r['standard']}")
tie = {}
for r in a.execute("SELECT * FROM stage1_tiebreak_items ORDER BY code, seq"):
    tie.setdefault(r["code"], []).append(r["item_text"])
apply = []
for d in a.execute("SELECT * FROM departments ORDER BY code"):
    apply.append({
        "c": d["code"], "s": d["school"], "d": d["dept_name"], "cat": d["category"],
        "q": d["admit_quota"], "ex": d["expected_interview_quota"],
        "sub": subs.get(d["code"], []),
        "p1": d["stage1_overall_pct"], "it": items.get(d["code"], []),
        "sk": d["skill_test_required"] == "是", "apcs": "；".join(apcs.get(d["code"], [])),
        "date": (d["exam_date"] or "").replace("; ", ""), "fee": d["interview_fee"],
        "tie": tie.get(d["code"], []), "ind": d["indigenous_extra_quota"],
    })

# ---------- 分發入學（115 學年度簡章 CSV） ----------
def parse_cond(text):
    """「數學A(均標) 或 數學B(均標)」→ [["數學A","均標"],["數學B","均標"]]（任一符合即可）"""
    alts = []
    for part in text.split(" 或 "):
        m = re.match(r"^(.+?)\((.+?)\)$", part.strip())
        if m:
            alts.append([m.group(1), m.group(2)])
    return alts


dist_rows = list(csv.reader(open(HERE / "115分發入學_校系分則.csv", encoding="utf-8-sig")))
h = dist_rows[0]
dist_out = []
for x in dist_rows[1:]:
    rec = dict(zip(h, x))
    conds = [parse_cond(rec[k]) for k in h if k.startswith("檢定標準") and rec[k]]
    subs = []
    for i in range(1, 6):
        if rec.get(f"採計科目{i}"):
            subs.append([rec[f"採計科目{i}"], rec[f"加權倍率{i}"], rec[f"同分參酌順序{i}"]])
    dist_out.append({
        "c": rec["系組代碼"], "s": rec["校名"], "d": rec["學系"], "q": rec["核定名額"],
        "ind": rec["原民外加"], "oth": rec["其他各類外加"],
        "std": [c for c in conds if c], "sub": subs, "note": rec["選系說明"],
    })

# ---------- 四技申請（115 學年度，build_caac.py 產生的 CSV） ----------
tech_out = []
for rec in csv.DictReader(open(HERE / "115四技申請_校系分則.csv", encoding="utf-8-sig")):
    ties = [[rec[f"同分參酌{i}"], rec[f"同分參酌{i}佔總成績比例"]] for i in range(1, 8) if rec[f"同分參酌{i}"]]
    tech_out.append({
        "c": rec["志願代碼"], "s": rec["學校"], "d": rec["系組名稱"], "reg": rec["區位"],
        "lim": rec["該校可選填系組數"], "q": rec["招生名額"], "ex": rec["預計複試人數"], "fee": rec["第二階段複試費"],
        "w": {s: rec[f"{s}權重"] for s in SUBJ[:6] if rec[f"{s}權重"]},
        "s2": [x for x in (rec["書面資料審查"], rec["到校評分項目"]) if x],
        "tie": ties,
        "apcs": f"{rec['APCS超額篩選人數']} 名，資格 {rec['APCS資格標準級分']} 級分" if rec["APCS超額篩選人數"] else "",
        "date": rec["第二階段複試日期"], "ann": rec["公告錄取名單日期"], "url": rec["網址"],
    })

# ---------- 歷年錄取結果（依檔名開頭的學年度自動讀取，例如 114繁星推薦_錄取標準.csv） ----------
def years_of(suffix):
    return sorted({int(m.group(1)) for p in HERE.glob(f"*{suffix}") if (m := re.match(r"(\d{3})", p.name))}, reverse=True)


def dash(v):
    return "" if v in ("", "--") else v


HIST = {"star": {}, "apply": {}, "dist": {}}
for y in years_of("繁星推薦_錄取標準.csv"):
    for x in csv.DictReader(open(HERE / f"{y}繁星推薦_錄取標準.csv", encoding="utf-8-sig")):
        items = []
        for i in range(1, 12):
            it = x.get(f"比序{i}_項目", "")
            if not it:
                break
            items.append([it, dash(x[f"比序{i}_第一輪標準"]), dash(x[f"比序{i}_第二輪標準"])])
        HIST["star"].setdefault(x["校系代碼"], {}).setdefault(str(y), []).append({
            "k": x["名額類別"], "ins": x["主修樂器"], "q": x["招生名額"], "n": x["總錄取人數(第八類為通過篩選人數)"],
            "g8": x["學群類別"] == "第八類學群", "n1": dash(x["第一輪人數"]), "n2": dash(x["第二輪人數"]), "it": items})
for y in years_of("申請入學_篩選標準.csv"):
    for x in csv.DictReader(open(HERE / f"{y}申請入學_篩選標準.csv", encoding="utf-8-sig")):
        seq = [x[f"篩選順序{i}"] for i in range(1, 12) if dash(x.get(f"篩選順序{i}", ""))]
        h = HIST["apply"].setdefault(x["校系代碼"], {}).setdefault(str(y), {"sv": [], "en": []})
        h["sv"].append({"sex": x["性別要求"], "maj": x["主修"], "q": x["招生名額"], "seq": seq, "same": x["同級分超額篩選"] == "*"})
for y in years_of("申請入學_分發標準.csv"):
    for x in csv.DictReader(open(HERE / f"{y}申請入學_分發標準.csv", encoding="utf-8-sig")):
        h = HIST["apply"].setdefault(x["校系代碼"], {}).setdefault(str(y), {"sv": [], "en": []})
        h["en"].append({"t": x["名額類別"], "sk": dash(x["術科項目別"]), "sex": x["性別限制"], "s": x["分發最低標準"]})
for y in years_of("分發入學_錄取結果.csv"):
    for x in csv.DictReader(open(HERE / f"{y}分發入學_錄取結果.csv", encoding="utf-8-sig")):
        HIST["dist"].setdefault(x["系組代碼"], {})[str(y)] = {
            "n": x["錄取人數(含外加)"], "s": x["普通生錄取分數"], "ts": x["普通生同分參酌科目"], "tv": x["普通生同分參酌分數"],
            "sp": {k: x[f"{k}錄取分數"] for k in ["原住民", "退伍軍人", "僑生", "蒙藏生", "派外子女"] if x[f"{k}錄取分數"]}}

js = "window.HIST=" + json.dumps(HIST, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.TECH=" + json.dumps(tech_out, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.DIST=" + json.dumps(dist_out, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.STAR=" + json.dumps(star, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.APPLY=" + json.dumps(apply, ensure_ascii=False, separators=(",", ":")) + ";\n"
(HERE / "data.js").write_text(js, encoding="utf-8")
print(f"star {len(star)} / apply {len(apply)} / dist {len(dist_out)} / tech {len(tech_out)} -> data.js ({len(js.encode())//1024} KB)")
