"""115 學年度大學申請入學結果 → CSV。

(1) 各校系分發標準一覽表（網頁表格）
    .../apply_his_report/115/115_entrance_standard/standard_index.php → standard_XXX.html
    同一校系的第二列（離島、原住民等名額類別）校系代碼與名稱留白，沿用上一列。
    輸出：115申請入學_分發標準.csv
(2) 各校系篩選標準一覽表（每校一張 PNG 圖片）
    .../apply_his_report/115/115_sieve_standard/collegeList.htm → report/XXX.htm → report/pict/XXX.png
    本程式只負責下載圖片；OCR 辨識由 ocr_apply_sieve.py 處理。

兩者都用同一個 cookie 檔（同一個連線階段），並帶上一頁當 Referer，模擬從清單頁點進去。
用法：uv run --with beautifulsoup4 python build_apply_result.py [學年度，預設 115]
"""
import csv
import sys
import re
import subprocess
import time
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).parent
YEAR = sys.argv[1] if len(sys.argv) > 1 else "115"
ROOT = f"https://www.cac.edu.tw/cacportal/apply_his_report/{YEAR}"
ENT = f"{ROOT}/{YEAR}_entrance_standard"
SIEVE = f"{ROOT}/{YEAR}_sieve_standard"
RAW = HERE / f"申請{YEAR}結果_原始資料"
COOKIES = RAW / "cookies.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def curl(url, referer, out=None):
    cmd = ["curl", "-s", "-f", "-L", "--max-time", "90", "-A", UA, "-e", referer,
           "-c", str(COOKIES), "-b", str(COOKIES), url]
    if out:
        cmd += ["-o", str(out)]
    for i in range(4):
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            return None if out else r.stdout.decode("utf-8-sig", errors="replace")
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"下載失敗：{url}")


def entrance():
    index = f"{ENT}/standard_index.php"
    soup = BeautifulSoup(curl(index, "https://www.cac.edu.tw/"), "html.parser")
    schools = [(re.search(r"(\d+)", a["href"]).group(1), re.sub(r"^\(\d+\)", "", a.get_text(strip=True)), a["href"])  # 113 年校名前有「(001)」
               for a in soup.find_all("a") if re.match(r"standard_\d+\.html", a.get("href", ""))]
    print(f"分發標準：{len(schools)} 所學校")
    rows = []
    for sc, name, href in schools:
        f = RAW / "分發標準" / f"standard_{sc}.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            curl(f"{ENT}/{href}", index, f)
            time.sleep(0.4)
        page = BeautifulSoup(f.read_text(encoding="utf-8-sig", errors="replace"), "html.parser")
        code = dept = ""
        for tr in page.find_all("tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(tds) != 6 or tds[0] == "校系代碼":
                continue
            if tds[0]:
                code, dept = tds[0], tds[1]
            rows.append([sc, name, code, dept, tds[2], tds[3], tds[4], tds[5]])
    out = HERE / f"{YEAR}申請入學_分發標準.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["學校代碼", "學校", "校系代碼", "學系(組)名稱", "名額類別", "術科項目別", "性別限制", "分發最低標準"])
        w.writerows(rows)
    print(f"  寫出 {len(rows)} 列、{len({r[2] for r in rows})} 個校系 -> {out.name}")


def sieve_images():
    index = f"{SIEVE}/collegeList.htm"
    soup = BeautifulSoup(curl(index, "https://www.cac.edu.tw/"), "html.parser")
    schools = [(re.search(r"(\d+)", a["href"]).group(1), a.get_text(strip=True))
               for a in soup.find_all("a") if re.match(r"report/\d+\.htm", a.get("href", ""))]
    print(f"篩選標準：{len(schools)} 所學校")
    d = RAW / "篩選標準圖片"
    d.mkdir(parents=True, exist_ok=True)
    for sc, _ in schools:
        png = d / f"{sc}.png"
        if png.exists() and png.stat().st_size > 10000:
            continue
        page_url = f"{SIEVE}/report/{sc}.htm"
        html = curl(page_url, index)                      # 先開學校頁
        img = re.search(r'src="([^"]+\.png)"', html).group(1)
        curl(f"{SIEVE}/report/{img}", page_url, png)      # 再取頁面上的圖片
        time.sleep(0.4)
    (RAW / "篩選標準學校清單.csv").write_text(
        "學校代碼,學校\n" + "\n".join(f"{sc},{re.sub(r'^\(\d+\)', '', n)}" for sc, n in schools), encoding="utf-8-sig")
    print(f"  圖片存於 {d.relative_to(HERE)}")


if __name__ == "__main__":
    RAW.mkdir(exist_ok=True)
    entrance()
    sieve_images()
