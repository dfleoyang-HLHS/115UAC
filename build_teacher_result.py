"""離原聯保（離島地區及原住民師資培育公費生聯合保送甄試）各校系分發標準一覽表 → CSV。

來源：https://www.cac.edu.tw/cacportal/apply_his_report/{學年度}/{學年度}_entrance_standard/teacher.html
（甄選委員會統一分發結果，與申請入學分發標準同一份報表的「師資保送」部分）
校系代碼為「T」＋簡章的保送代碼（如 TAAC01 ↔ AAC01），保送代碼前 3 碼表示族語別與保送縣市。
用法：uv run --with beautifulsoup4 python build_teacher_result.py 113 114 115
輸出：{學年度}離原聯保_分發標準.csv；原始網頁存於 離原聯保_簡章/teacher{學年度}.html
"""
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
RAW = HERE / "離原聯保_簡章"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

for year in sys.argv[1:]:
    base = f"https://www.cac.edu.tw/cacportal/apply_his_report/{year}/{year}_entrance_standard"
    html_f = RAW / f"teacher{year}.html"
    RAW.mkdir(exist_ok=True)
    if not html_f.exists():
        # 先開分發標準首頁，再從首頁點進 teacher.html（同一 cookie 檔、帶 Referer）
        ck = RAW / "cookies.txt"
        subprocess.run(["curl", "-s", "-L", "-A", UA, "-c", str(ck), "-b", str(ck), "-e", "https://www.cac.edu.tw/",
                        "-o", "NUL" if sys.platform == "win32" else "/dev/null", f"{base}/standard_index.php"], check=True)
        time.sleep(0.5)
        subprocess.run(["curl", "-s", "-f", "-L", "-A", UA, "-c", str(ck), "-b", str(ck), "-e", f"{base}/standard_index.php",
                        "-o", str(html_f), f"{base}/teacher.html"], check=True)
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
        if len(tds) == 3 and re.fullmatch(r"T[A-Z]{3}\d{2}", tds[0]):
            code = tds[0]
            name = re.sub(r"\s+", "", tds[1])
            m2 = re.match(r"(.+)\((.+)\)$", name)
            dept, where = (m2.group(1), m2.group(2)) if m2 else (name, "")
            kind = "離島" if code[1] == "Z" else "原住民"   # 保送代碼第 1 碼 Z 為離島；原住民第 3 碼各年不同（113 年 B、115 年 C）
            rows.append([year, sc, school, code, code[1:], name, dept, where, kind, tds[2]])
    out = HERE / f"{year}離原聯保_分發標準.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["學年度", "學校代碼", "學校", "校系代碼", "保送代碼", "學系(組)名稱", "學系", "保送縣市或類別", "類別", "分發最低標準"])
        w.writerows(rows)
    print(f"{year}：{len({r[1] for r in rows})} 所學校、{len(rows)} 個保送校系"
          f"（原住民 {sum(r[8] == '原住民' for r in rows)}、離島 {sum(r[8] == '離島' for r in rows)}）-> {out.name}")
