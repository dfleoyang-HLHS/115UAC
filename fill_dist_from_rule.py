"""沒有「校系條件與招生名額錄取人數一覽表」的年度，改用同年度分發入學校系分則補上可取得的欄位。

補上：檢定標準1～3、英聽檢定、同分參酌順序、核定名額（取自 {學年度}分發入學_校系分則.csv），
      錄取總人數（等於既有的「錄取人數(含外加)」，114 年兩份報表逐筆比對一致）。
留空：回流名額、招生名額、錄取人數男女、外加錄取男女（只有官方名額錄取人數一覽表才有）。
欄位與順序與 parse_uac_quota.py 合併後的格式相同。

用法：uv run python fill_dist_from_rule.py <學年度>
"""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
YEAR = sys.argv[1]
TARGET = HERE / f"{YEAR}分發入學_錄取結果.csv"
RULE = HERE / f"{YEAR}分發入學_校系分則.csv"
NEW = ["檢定標準1", "檢定標準2", "檢定標準3", "英聽檢定", "同分參酌順序", "核定名額", "回流名額", "招生名額",
       "錄取人數_男", "錄取人數_女", "外加錄取_男", "外加錄取_女", "錄取總人數"]

rule = {x["系組代碼"]: x for x in csv.DictReader(open(RULE, encoding="utf-8-sig"))}
rows = list(csv.reader(open(TARGET, encoding="utf-8-sig")))
head = [h for h in rows[0] if h not in NEW]
keep = [i for i, h in enumerate(rows[0]) if h in head]
H = {h: i for i, h in enumerate(head)}
out, miss = [], []
for r in rows[1:]:
    base = [r[i] for i in keep]
    x = rule.get(base[H["系組代碼"]])
    if not x:
        miss.append(base[H["系組代碼"]])
        out.append(base + [""] * (len(NEW) - 1) + [base[H["錄取人數(含外加)"]]])
        continue
    std, listen = [], ""
    for i in range(1, 4):
        v = x.get(f"檢定標準{i}", "")
        m = re.fullmatch(r"英聽\((.+?)\)", v)
        if m:
            listen = m.group(1)
        elif v:
            std.append(v)
    std += [""] * (3 - len(std))
    # 同分參酌順序：依分則每科的「同分參酌順序」編號排列採計科目，去掉(學測)(分科)(術科)
    subs = [(int(x[f"同分參酌順序{i}"]), re.sub(r"\(.+?\)$", "", x[f"採計科目{i}"]))
            for i in range(1, 6) if x.get(f"採計科目{i}") and x.get(f"同分參酌順序{i}", "").isdigit()]
    tie = "→".join(s for _, s in sorted(subs))
    out.append(base + std[:3] + [listen, tie, x["核定名額"]] + [""] * 6 + [base[H["錄取人數(含外加)"]]])
with open(TARGET, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(head + NEW)
    w.writerows(out)
print(f"{TARGET.name}：以 {RULE.name} 補上 {len(out) - len(miss)} 列，分則找不到 {len(miss)} 列 {miss[:8]}")
