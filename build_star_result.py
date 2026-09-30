"""115 學年度大學繁星推薦「各校系錄取標準一覽表」→ CSV。

來源（大學甄選入學委員會）：
  第一至七類學群：.../115_result_standard/one2seven/collegeList_1.php
  第八類學群    ：.../115_result_standard/eight/collegeList_1.php
第一層是學校清單，第二層是各校 PDF。以同一個連線階段（保留 cookie、帶清單頁 Referer）
模擬點擊下載，PDF 存在 繁星115錄取標準_PDF/，再用 pdfplumber 解析表格。

用法：uv run --with pdfplumber --with beautifulsoup4 --no-binary-package charset-normalizer python build_star_result.py [學年度，預設 115]
輸出：115繁星推薦_錄取標準.csv（一列一個校系）
"""
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

HERE = Path(__file__).parent
YEAR = sys.argv[1] if len(sys.argv) > 1 else "115"
BASE = f"https://www.cac.edu.tw/cacportal/star_his_report/{YEAR}/{YEAR}_result_standard"
GROUPS = [("one2seven", "第一至七類學群"), ("eight", "第八類學群")]
PDF_DIR = HERE / f"繁星{YEAR}錄取標準_PDF"
OUT = HERE / f"{YEAR}繁星推薦_錄取標準.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
COOKIES = PDF_DIR / "cookies.txt"
SUBJ = ["國文", "英文", "數學A", "數學B", "社會", "自然", "英聽"]


def curl(url, referer, out=None):
    """同一個 cookie 檔 = 同一個連線階段；每次都帶上一頁當 Referer，像人從清單點進去。"""
    cmd = ["curl", "-s", "-f", "-L", "--max-time", "60", "-A", UA, "-e", referer,
           "-c", str(COOKIES), "-b", str(COOKIES), url]
    if out:
        cmd += ["-o", str(out)]
    for i in range(4):
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            return r.stdout.decode("utf-8-sig", errors="replace") if not out else None
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"下載失敗：{url}")


def lines(cell):
    return [x.strip() for x in (cell or "").split("\n")]


def join_wrapped(items):
    """PDF 儲存格內自動折行會把「體育(百分等級)」拆成兩行；括號沒閉合就接回下一行。"""
    out = []
    for x in items:
        if out and out[-1].count("(") > out[-1].count(")"):
            out[-1] += x
        else:
            out.append(x)
    return out


def download():
    PDF_DIR.mkdir(exist_ok=True)
    jobs = []
    for key, label in GROUPS:
        list_url = f"{BASE}/{key}/collegeList_1.php"
        html = curl(list_url, "https://www.cac.edu.tw/")
        soup = BeautifulSoup(html, "html.parser")
        schools = []
        for a in soup.find_all("a"):
            m = re.match(r"\((\d+)\)(.+)", a.get_text(strip=True))
            # 115 年：href 直接是 PDF；114 年：href 為 javascript，PDF 路徑在 onclick="openPdfWithViewer('./001/...pdf')"
            href = a.get("href", "")
            if not href.endswith(".pdf"):
                j = re.search(r"'([^']+\.pdf)'", a.get("onclick", ""))
                href = j.group(1) if j else ""
            if m and href:
                schools.append((m.group(1), m.group(2), href))
        print(f"{label}：{len(schools)} 所學校")
        for code, name, href in schools:
            pdf = PDF_DIR / f"{key}_{code}.pdf"
            if not pdf.exists() or pdf.stat().st_size < 1000:
                curl(f"{BASE}/{key}/{href.lstrip('./')}", list_url, pdf)
                time.sleep(0.5)
            jobs.append((key, label, code, name, pdf))
    return jobs


def parse(jobs):
    rows = []
    for key, label, code, name, pdf in jobs:
        with pdfplumber.open(pdf) as doc:
            for page in doc.pages:
                for table in page.extract_tables():
                    for r in table:
                        if not r or not re.fullmatch(r"\d{5}", (r[0] or "").strip()):
                            continue
                        r = list(r) + [None] * (15 - len(r))
                        subj, std, lvl = lines(r[4]), lines(r[5]), lines(r[6])
                        subject = {}
                        for i, s in enumerate(subj):
                            if s in SUBJ:
                                subject[s] = (std[i] if i < len(std) else "", lvl[i] if i < len(lvl) and s != "英聽" else "")
                        items = [x for x in lines(r[10]) if x]
                        r1, r2 = lines(r[12]), lines(r[14])
                        rows.append({
                            "group": label, "school_code": code, "school": name,
                            "code": r[0].strip(), "dept": re.sub(r"\s+", "", r[1] or ""),
                            "quota": (r[2] or "").strip(), "admitted": (r[3] or "").strip(),
                            "subject": subject,
                            "skill": list(zip(join_wrapped(lines(r[7])), lines(r[8]), lines(r[9]))),
                            "items": items, "n1": (r[11] or "").strip(), "n2": (r[13] or "").strip(),
                            "r1": r1, "r2": r2,
                        })
    return rows


def write(rows):
    max_skill = max(len([s for s in r["skill"] if s[0] not in ("", "--")]) for r in rows)
    max_items = max(len(r["items"]) for r in rows)
    head = ["學群類別", "學校代碼", "學校", "校系代碼", "校系名稱", "主修樂器", "名額類別", "招生名額", "總錄取人數(第八類為通過篩選人數)"]
    for s in SUBJ:
        head += [f"{s}_檢定標準"] + ([] if s == "英聽" else [f"{s}_級分"])
    for i in range(1, max(max_skill, 1) + 1):
        head += [f"術科項目{i}", f"術科檢定標準{i}", f"術科分數{i}"]
    head += ["第一輪人數", "第二輪人數"]
    for i in range(1, max_items + 1):
        head += [f"比序{i}_項目", f"比序{i}_第一輪標準", f"比序{i}_第二輪標準"]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in rows:
            # 「人類學系【外加】」→ 名額類別=外加；「音樂學系《鋼琴》」→ 主修樂器=鋼琴
            dept = r["dept"]
            kind = "外加" if "【外加】" in dept else "一般"
            dept = dept.replace("【外加】", "")
            m = re.search(r"《(.+?)》", dept)
            inst = m.group(1) if m else ""
            dept = re.sub(r"《.+?》", "", dept)
            row = [r["group"], r["school_code"], r["school"], r["code"], dept, inst, kind, r["quota"], r["admitted"]]
            for s in SUBJ:
                std, lvl = r["subject"].get(s, ("", ""))
                row += [std] + ([] if s == "英聽" else [lvl])
            sk = [s for s in r["skill"] if s[0] not in ("", "--")]
            for i in range(max(max_skill, 1)):
                row += list(sk[i]) if i < len(sk) else ["", "", ""]
            row += [r["n1"], r["n2"]]
            for i in range(max_items):
                row += [r["items"][i] if i < len(r["items"]) else "",
                        r["r1"][i] if i < len(r["r1"]) else "", r["r2"][i] if i < len(r["r2"]) else ""]
            w.writerow(row)
    print(f"寫出 {len(rows)} 個校系，{len(head)} 欄（術科最多 {max_skill} 項、分發比序最多 {max_items} 項）-> {OUT.name}")


if __name__ == "__main__":
    rows = parse(download())
    write(rows)
