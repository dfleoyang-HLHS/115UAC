"""把 115 學年度四技申請官方 Excel（技專校院招生委員會聯合會公告）整理成 CSV。

來源：https://www.jctv.ntut.edu.tw/caac/contents.php?academicYear=115&subId=109
  115_caac_minute.xlsx      招生學校系(組)、學程資料
  115_caac_onlyschool.xlsx  招生學校區位及申請生可選填該校系(組)、學程數
  115_caac_APCS.xlsx        採計 APCS 超額篩選之校系(組)、學程
輸出：115四技申請_校系分則.csv（一列一個系組）
"""
import csv
from pathlib import Path

import openpyxl

HERE = Path(__file__).parent
SRC = HERE / "四技申請_115原始資料"
OUT = HERE / "115四技申請_校系分則.csv"
SUBJ = ["國文", "英文", "數學A", "數學B", "社會", "自然"]


def rows(name):
    ws = openpyxl.load_workbook(SRC / name, read_only=True).worksheets[0]
    data = list(ws.iter_rows(values_only=True))
    head = [str(h).strip() for h in data[0]]
    return [dict(zip(head, ["" if v is None else str(v).strip() for v in r])) for r in data[1:] if any(r)]


def clean(v):
    return "" if v in ("---", "--", "-") else v


schools = {r["學校代碼"]: r for r in rows("115_caac_onlyschool.xlsx")}
apcs = {r["志願代碼"]: r for r in rows("115_caac_APCS.xlsx")}

header = ["志願代碼", "學校代碼", "學校", "區位", "該校可選填系組數", "系組名稱", "招生名額", "預計複試人數", "第二階段複試費"]
header += [f"{s}權重" for s in SUBJ]
header += ["書面資料審查", "到校評分項目"]
for i in range(1, 8):
    header += [f"同分參酌{i}", f"同分參酌{i}佔總成績比例"]
header += ["APCS超額篩選人數", "APCS資格標準級分", "公告第二階段複試通知", "資料上傳及繳費截止", "第二階段複試日期",
           "公告總成績日期", "成績複查截止", "公告錄取名單日期", "網址", "備註"]

out = []
for r in rows("115_caac_minute.xlsx"):
    code, sc = r["志願代碼"], r["學校代碼"]
    s = schools.get(sc, {})
    a = apcs.get(code, {})
    row = [code, sc, r["學校"], s.get("區位", ""), s.get("申請生可選填之該校系(組)、學程數", ""),
           r["系（組）、學程名稱"], r["招生名額"], r["預計複試人數"], r["第二階段複試費"]]
    row += [clean(r[f"{x}權重"]) for x in SUBJ]
    row += [r["第二階段複試評分項目申請生不須到校(書面資料審查)"], r["第二階段複試評分項目申請生須到校參加(面試/其他)"]]
    for i in range(1, 8):
        row += [r.get(f"同分參酌順序{i}評分項目", ""), clean(r.get(f"同分參酌順序{i}評分項目之占總成績比例", ""))]
    row += [a.get("大學程式設計先修檢測（APCS）超額篩選人數", ""), a.get("大學程式設計先修檢測（APCS）超額篩選資格標準級", ""),
            r["公告第二階段複試通知"], r["網路上傳資格審查暨學習歷程備審資料及繳費截止日期"], clean(r["第二階段複試日期"]),
            r["公告總成績日期"], r["成績複查截止日期"], r["公告錄取名單日期"], r["網址"], r["備註"]]
    out.append(row)

with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(out)
print(f"{len({r[1] for r in out})} 所學校，{len(out)} 個系組，APCS {sum(1 for r in out if r[header.index('APCS超額篩選人數')])} 個 -> {OUT.name}")
