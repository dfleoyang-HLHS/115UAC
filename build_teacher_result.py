"""甄選委員會統一分發結果中的兩個特殊管道 → CSV：
  teacher：離島地區及原住民師資培育公費生聯合保送甄試（離原聯保），校系代碼「T」＋保送代碼（TAAC01 ↔ AAC01）
  doctor ：原住民族及離島地區醫事人員養成計畫公費生甄試，校系代碼「D_」＋簡章代碼（D_A011 ↔ A011）

來源：https://www.cac.edu.tw/cacportal/apply_his_report/{學年度}/{學年度}_entrance_standard/{teacher|doctor}.html
用法：uv run --with beautifulsoup4 python build_teacher_result.py [teacher|doctor] 113 114 115
      （第一個參數省略時為 teacher）
輸出：teacher → {學年度}離原聯保_分發標準.csv（原始網頁存於 離原聯保_簡章/teacher{學年度}.html）
      doctor  → {學年度}醫事人員養成計畫_分發標準.csv（原始網頁存於 醫事人員養成計畫/doctor{學年度}.html）
"""
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
ARGS = sys.argv[1:]
PAGE = ARGS.pop(0) if ARGS and ARGS[0] in ("teacher", "doctor") else "teacher"
CFG = {
    "teacher": {"raw": HERE / "離原聯保_簡章", "code": r"T[A-Z]{3}\d{2}", "prefix": "T", "out": "離原聯保_分發標準.csv"},
    "doctor": {"raw": HERE / "醫事人員養成計畫", "code": r"D_[A-Z]\d{3}", "prefix": "D_", "out": "醫事人員養成計畫_分發標準.csv"},
}[PAGE]
RAW = CFG["raw"]

for year in ARGS:
    base = f"https://www.cac.edu.tw/cacportal/apply_his_report/{year}/{year}_entrance_standard"
    html_f = RAW / f"{PAGE}{year}.html"
    RAW.mkdir(exist_ok=True)
    if not html_f.exists():
        # 先開分發標準首頁，再從首頁點進 teacher.html／doctor.html（同一 cookie 檔、帶 Referer）
        ck = RAW / "cookies.txt"
        subprocess.run(["curl", "-s", "-L", "-A", UA, "-c", str(ck), "-b", str(ck), "-e", "https://www.cac.edu.tw/",
                        "-o", "NUL" if sys.platform == "win32" else "/dev/null", f"{base}/standard_index.php"], check=True)
        time.sleep(0.5)
        subprocess.run(["curl", "-s", "-f", "-L", "-A", UA, "-c", str(ck), "-b", str(ck), "-e", f"{base}/standard_index.php",
                        "-o", str(html_f), f"{base}/{PAGE}.html"], check=True)
    soup = BeautifulSoup(html_f.read_text(encoding="utf-8-sig", errors="replace"), "html.parser")
    rows, school, sc = [], "", ""
    # 依文件順序走訪：遇到「校名 : (002)國立臺灣師範大學」就更新學校，遇到資料列就記錄
    for el in soup.find_all(["tr", "div", "p", "span", "font", "b", "td"]):
        txt = el.get_text(" ", strip=True)
        m = re.match(r"校名\s*[:：]\s*\((\d+)\)\s*(\S+)$", txt)
        if m and el.name != "tr":
            sc, school = m.group(1), m.group(2)
            continue
        if el.name != "tr":
            continue
        tds = [td.get_text(" ", strip=True) for td in el.find_all("td")]
        if len(tds) == 3 and re.fullmatch(CFG["code"], tds[0]):
            code = tds[0]
            short = code[len(CFG["prefix"]):]
            name = re.sub(r"\s+", "", tds[1])
            m2 = re.match(r"(.+)\((.+)\)$", name)
            dept, where = (m2.group(1), m2.group(2)) if m2 else (name, "")
            if PAGE == "teacher":
                kind = "離島" if short[0] == "Z" else "原住民"   # 保送代碼第 1 碼 Z 為離島；原住民第 3 碼各年不同（113 年 B、115 年 C）
            else:
                # 籍屬以簡章代碼第 4 碼為準（113 年寫「原住民族」、115 年寫「原住民」；114 年有一筆少了左括號）
                where = {"1": "原住民", "2": "澎湖縣", "3": "金門縣", "4": "連江縣", "5": "琉球鄉",
                         "6": "綠島鄉", "7": "蘭嶼鄉", "8": "偏鄉"}.get(short[3], where)
                dept = re.sub(r"\(?(原住民族?|澎湖縣|金門縣|連江縣|琉球鄉|綠島鄉|蘭嶼鄉|偏鄉)\)$", "", name)
                kind = where
            rows.append([year, sc, school, code, short, name, dept, where, kind, tds[2]])
    out = HERE / f"{year}{CFG['out']}"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["學年度", "學校代碼", "學校", "校系代碼", "簡章代碼", "學系(組)名稱", "學系", "保送縣市或籍屬", "類別", "分發最低標準"])
        w.writerows(rows)
    print(f"{PAGE} {year}：{len({r[1] for r in rows})} 所學校、{len(rows)} 個校系 -> {out.name}")
