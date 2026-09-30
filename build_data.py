"""把 star115.db / apply115.db 整理成網頁用的 data.js（index.html 會載入）。"""
import csv
import difflib
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


# 各年度的校系代碼可能被重新分配給別的系（例如東吳 00520：114 化學系、115 物理學系），
# 所以歷年資料一律以「學校＋系名」對應到目前網頁（115）的校系；系名只有細微差異
# （如「資訊管理學系資訊管理組」vs「資訊管理學系(資訊管理組)」）時，才以相同代碼且名稱相似度 ≥ 0.75 補對應。
def norm(t):
    t = re.sub(r"\s+", "", t or "")
    for a_, b_ in (("（", "("), ("）", ")"), ("台", "臺"), ("．", "."), ("‧", "."), ("・", ".")):
        t = t.replace(a_, b_)
    return t


class Matcher:
    def __init__(self, records):
        self.by_name = {norm(r["s"]) + "|" + norm(r["d"]): r["c"] for r in records}
        self.by_code = {r["c"]: (norm(r["s"]), norm(r["d"])) for r in records}
        self.hit = self.miss = 0

    def __call__(self, school, name, code):
        k = norm(school) + "|" + norm(name)
        if k in self.by_name:
            self.hit += 1
            return self.by_name[k]
        w = self.by_code.get(code)
        if w and w[0] == norm(school) and difflib.SequenceMatcher(None, w[1], norm(name)).ratio() >= 0.75:
            self.hit += 1
            return code
        self.miss += 1
        return None


HIST = {"star": {}, "apply": {}, "dist": {}}
M = {"star": Matcher(star), "apply": Matcher(apply), "dist": Matcher(dist_out)}
report = []
for y in years_of("繁星推薦_錄取標準.csv"):
    m = M["star"]; m.hit = m.miss = 0
    for x in csv.DictReader(open(HERE / f"{y}繁星推薦_錄取標準.csv", encoding="utf-8-sig")):
        code = m(x["學校"], x["校系名稱"], x["校系代碼"])
        if not code:
            continue
        items = []
        for i in range(1, 12):
            it = x.get(f"比序{i}_項目", "")
            if not it:
                break
            items.append([it, dash(x[f"比序{i}_第一輪標準"]), dash(x[f"比序{i}_第二輪標準"])])
        HIST["star"].setdefault(code, {}).setdefault(str(y), []).append({
            "k": x["名額類別"], "ins": x["主修樂器"], "q": x["招生名額"], "n": x["總錄取人數(第八類為通過篩選人數)"],
            "g8": x["學群類別"] == "第八類學群", "n1": dash(x["第一輪人數"]), "n2": dash(x["第二輪人數"]), "it": items})
    report.append(f"{y} 繁星：對應 {m.hit} 列、未對應 {m.miss} 列")
for y in years_of("申請入學_篩選標準.csv"):
    m = M["apply"]; m.hit = m.miss = 0
    for x in csv.DictReader(open(HERE / f"{y}申請入學_篩選標準.csv", encoding="utf-8-sig")):
        code = m(x["學校"], x["校系名稱"], x["校系代碼"])
        if not code:
            continue
        seq = [x[f"篩選順序{i}"] for i in range(1, 12) if dash(x.get(f"篩選順序{i}", ""))]
        h = HIST["apply"].setdefault(code, {}).setdefault(str(y), {"sv": [], "en": []})
        h["sv"].append({"sex": x["性別要求"], "maj": x["主修"], "q": x["招生名額"], "seq": seq, "same": x["同級分超額篩選"] == "*"})
    report.append(f"{y} 申請篩選：對應 {m.hit} 列、未對應 {m.miss} 列")
for y in years_of("申請入學_分發標準.csv"):
    m = M["apply"]; m.hit = m.miss = 0
    for x in csv.DictReader(open(HERE / f"{y}申請入學_分發標準.csv", encoding="utf-8-sig")):
        code = m(x["學校"], x["學系(組)名稱"], x["校系代碼"])
        if not code:
            continue
        h = HIST["apply"].setdefault(code, {}).setdefault(str(y), {"sv": [], "en": []})
        h["en"].append({"t": x["名額類別"], "sk": dash(x["術科項目別"]), "sex": x["性別限制"], "s": x["分發最低標準"]})
    report.append(f"{y} 申請分發：對應 {m.hit} 列、未對應 {m.miss} 列")
for y in years_of("分發入學_錄取結果.csv"):
    m = M["dist"]; m.hit = m.miss = 0
    for x in csv.DictReader(open(HERE / f"{y}分發入學_錄取結果.csv", encoding="utf-8-sig")):
        code = m(x["校名"], x["系組名"], x["系組代碼"])
        if not code:
            continue
        HIST["dist"].setdefault(code, {})[str(y)] = {
            "n": x["錄取人數(含外加)"], "s": x["普通生錄取分數"], "ts": x["普通生同分參酌科目"], "tv": x["普通生同分參酌分數"],
            "sp": {k: x[f"{k}錄取分數"] for k in ["原住民", "退伍軍人", "僑生", "蒙藏生", "派外子女"] if x[f"{k}錄取分數"]},
            # 有「校系條件與招生名額錄取人數一覽表」合併進來的年度才有招生名額（核定＋回流）
            "q": x.get("招生名額", ""), "rf": x.get("回流名額", "")}
    report.append(f"{y} 分發：對應 {m.hit} 列、未對應 {m.miss} 列")
# 四技申請第一階段最低篩選標準（百分制＝加權平均級分 ÷ 15 × 100）
HIST["tech"] = {}
M["tech"] = Matcher(tech_out)
for y in years_of("四技申請_篩選標準.csv"):
    m = M["tech"]; m.hit = m.miss = 0
    for x in csv.DictReader(open(HERE / f"{y}四技申請_篩選標準.csv", encoding="utf-8-sig")):
        code = m(x["學校"], x["系組名稱"], x["志願代碼"])
        if code:
            HIST["tech"].setdefault(code, {})[str(y)] = {
                "s": x["學測成績最低篩選標準"], "a": x["APCS超額篩選最低標準級分"], "aw": x["APCS超額篩選標準加權成績"]}
    report.append(f"{y} 四技：對應 {m.hit} 列、未對應 {m.miss} 列")
print("\n".join(report))

# ---------- 離原聯保（師資培育公費生保送甄試）：取最新學年度的校系分則，代碼自成一套，不與其他管道合併 ----------
JR = []
jr_years = years_of("離原聯保_校系分則.csv")
if jr_years:
    for x in csv.DictReader(open(HERE / f"{jr_years[0]}離原聯保_校系分則.csv", encoding="utf-8-sig")):
        JR.append({"y": x["學年度"], "k": x["類別"], "c": x["校系代碼"], "s": x["學校"], "d": x["學系"],
                   "lang": x["族語別"], "area": x["保送縣市"], "id": x["身分別"], "q": x["招生名額"],
                   "std": {s: x[f"檢定_{s}"] for s in SUBJ[:6] if x[f"檢定_{s}"] not in ("", "--")},
                   "w": {s: x[f"採計_{s}"] for s in SUBJ[:6] if x[f"採計_{s}"] not in ("", "--")},
                   "p": x["學測佔總成績比例"], "sk": x["術科採計"], "skp": x["術科佔總成績比例"],
                   "tie": [x[f"同分參酌{i}"] for i in range(1, 7) if x[f"同分參酌{i}"]], "need": x["需求專長與分發"]})

# 離原聯保歷年分發最低標準（甄選委員會 teacher.html）：保送代碼每年會換系，
# 以「代碼前 2 碼（族語＋縣市）＋學校＋學系」對應；同一學年度則直接比對代碼
jr_hist_report = []
for y in years_of("離原聯保_分發標準.csv"):
    res = list(csv.DictReader(open(HERE / f"{y}離原聯保_分發標準.csv", encoding="utf-8-sig")))
    hit = 0
    for r in JR:
        same_year = str(y) == r["y"]
        m = [x for x in res if (x["簡章代碼"] == r["c"]) if same_year] or \
            [x for x in res if not same_year and x["簡章代碼"][:2] == r["c"][:2]
             and norm(x["學校"]) == norm(r["s"]) and norm(x["學系"]) == norm(r["d"])]
        if m:
            hit += 1
            r.setdefault("h", {})[str(y)] = [{"c": x["簡章代碼"], "n": x["學系(組)名稱"], "s": x["分發最低標準"]} for x in m]
    jr_hist_report.append(f"{y} 離原聯保：{len(res)} 個校系，對應到 115 年 {hit} 個保送名額")
print("\n".join(jr_hist_report))

# 醫事人員養成計畫（衛福部公費生）：最新學年度的校系名額；代碼自成一套
MED = []
med_years = years_of("醫事人員養成計畫_校系名額.csv")
if med_years:
    for x in csv.DictReader(open(HERE / f"{med_years[0]}醫事人員養成計畫_校系名額.csv", encoding="utf-8-sig")):
        MED.append({"y": x["學年度"], "s": x["學校"], "d": x["學系"], "yr": x["修業年限"], "id": x["籍屬身分"],
                    "c": x["校系代碼"], "q": x["招生名額"]})

# 醫事人員養成計畫歷年分發最低標準（甄選委員會 doctor.html，代碼為「D_」＋簡章代碼）：
# 同一學年度直接比對代碼；往年須學校與籍屬相同，學系名稱相同或相似度 ≥ 0.75
med_report = []
for y in years_of("醫事人員養成計畫_分發標準.csv"):
    res = list(csv.DictReader(open(HERE / f"{y}醫事人員養成計畫_分發標準.csv", encoding="utf-8-sig")))
    hit = 0
    for r in MED:
        if str(y) == r["y"]:
            m = [x for x in res if x["簡章代碼"] == r["c"]]
        else:
            cand = [x for x in res if norm(x["學校"]) == norm(r["s"]) and x["類別"] == r["id"]]
            m = [x for x in cand if norm(x["學系"]) == norm(r["d"])] or \
                [x for x in cand if difflib.SequenceMatcher(None, norm(x["學系"]), norm(r["d"])).ratio() >= 0.75]
        if m:
            hit += 1
            r.setdefault("h", {})[str(y)] = [{"c": x["簡章代碼"], "n": x["學系(組)名稱"], "s": x["分發最低標準"]} for x in m]
    med_report.append(f"{y} 醫事人員養成計畫：{len(res)} 個校系，對應到 115 年 {hit} 個名額列")
print("\n".join(med_report))

js = "window.MED=" + json.dumps(MED, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.JRACOIA=" + json.dumps(JR, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.HIST=" + json.dumps(HIST, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.TECH=" + json.dumps(tech_out, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.DIST=" + json.dumps(dist_out, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.STAR=" + json.dumps(star, ensure_ascii=False, separators=(",", ":")) + ";\n"
js += "window.APPLY=" + json.dumps(apply, ensure_ascii=False, separators=(",", ":")) + ";\n"
(HERE / "data.js").write_text(js, encoding="utf-8")
print(f"star {len(star)} / apply {len(apply)} / dist {len(dist_out)} / tech {len(tech_out)} -> data.js ({len(js.encode())//1024} KB)")
