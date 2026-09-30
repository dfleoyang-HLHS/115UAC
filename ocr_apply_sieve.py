"""115 學年度申請入學「各校系篩選標準一覽表」圖片 → CSV（OCR）。

作法：
1. 用形態學偵測表格格線，找出每一個資料列（橫線之間）與該列的欄位分隔（直線）。
2. 逐格裁切，用 RapidOCR 辨識；「--」「*」這類符號用墨跡形狀判斷，避免 OCR 漏字。
3. 校系代碼、招生名額、檢定標準、篩選倍率與 115 校系分則（apply115.db）交叉核對，
   不一致的格子列入 115申請入學_篩選標準_待確認.csv。

用法：uv run --with rapidocr-onnxruntime --with opencv-python-headless python ocr_apply_sieve.py [學校代碼...]
輸出：115申請入學_篩選標準.csv
"""
import csv
import difflib
import re
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

HERE = Path(__file__).parent
IMG_DIR = HERE / "申請115結果_原始資料" / "篩選標準圖片"
OUT = HERE / "115申請入學_篩選標準.csv"
REVIEW = HERE / "115申請入學_篩選標準_待確認.csv"
SUBJ = ["國文", "英文", "數學A", "數學B", "社會", "自然"]
# 一般校系表格的 25 欄
COLS = (["校系代碼", "性別要求", "校系名稱", "招生名額"]
        + [f"檢定_{s}" for s in SUBJ + ["英聽"]]
        + [f"倍率_{s}" for s in SUBJ + ["學測科目組合"]]
        + [f"篩選順序{i}" for i in range(1, 7)] + ["同級分超額篩選"])
# OCR 常見簡體／誤認字 → 繁體
S2T = str.maketrans({"国": "國", "数": "數", "学": "學", "会": "會", "语": "語", "认": "認", "识": "識", "读": "讀",
                     "实": "實", "筝": "箏", "竖": "豎", "撃": "擊", "论": "論", "标": "標", "顶": "頂", "后": "後", "（": "(", "）": ")", "＋": "+", "十": "+",
                     "－": "-", "一": "-", "—": "-", "：": ":", "O": "0", "o": "0", "l": "1", "I": "1"})
ocr = RapidOCR()


def lines_mask(gray):
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    h = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (120, 1)))
    v = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 18)))
    return bw, h, v


def runs(arr, min_gap=3):
    """把 True 的連續區段合併成中心位置清單。"""
    idx = np.where(arr)[0]
    if not len(idx):
        return []
    groups, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > min_gap:
            groups.append((start + prev) // 2)
            start = i
        prev = i
    groups.append((start + prev) // 2)
    return groups


def ink_symbol(cell):
    """判斷沒有文字的格子：空白、「--」或「*」。"""
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(g, 110, 255, cv2.THRESH_BINARY_INV)
    bw = bw[2:-2, 3:-3]
    ys, xs = np.where(bw > 0)
    if len(ys) < 4:
        return ""
    hgt, wid = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    if hgt <= 4 and wid >= 6:
        return "--"
    if 6 <= hgt <= 16 and wid <= 16:
        return "*"
    return None


def read_cell(img, x0, x1, y0, y1, star=False):
    """逐行辨識：依墨跡水平投影切出文字行，每行只做文字辨識（不跑文字偵測，快很多）。"""
    cell = img[y0 + 3:y1 - 2, x0 + 3:x1 - 2]
    if cell.size == 0:
        return ""
    sym = ink_symbol(cell)
    if sym is not None and (sym != "*" or star):
        return sym
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(g, 110, 255, cv2.THRESH_BINARY_INV)
    prof = bw.sum(axis=1) > 0
    bands, start = [], None
    for i, on in enumerate(list(prof) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= 4:
                bands.append((start, i))
            start = None
    parts = []
    for t, b in bands:
        cols = np.where(bw[t:b].sum(axis=0) > 0)[0]
        line = cell[max(t - 3, 0):b + 3, max(cols.min() - 4, 0):cols.max() + 5]
        line = cv2.resize(line, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        line = cv2.copyMakeBorder(line, 8, 8, 8, 8, cv2.BORDER_REPLICATE)
        res, _ = ocr(line, use_det=False, use_cls=False)
        if res:
            parts.append(res[0][0])
    txt = "".join(parts).translate(S2T).replace(" ", "")
    return re.sub(r"^-+$", "--", txt) or "?"


def seq_count(widths):
    """從最右邊往回數：最後一欄是「同級分超額篩選」，前面連續等寬的欄位就是篩選順序（6 或 11 欄）。"""
    ref = widths[-2]
    k = 0
    for w in reversed(widths[:-1]):
        if abs(w - ref) / ref < 0.2:
            k += 1
        else:
            break
    # 術科類表格的檢定、倍率小欄寬度可能與篩選順序相近，會一路數過頭；篩選順序只有 6 或 11 欄
    return 11 if k >= 11 else 6 if k >= 6 else k


def parse_image(path):
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)  # 支援中文路徑
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, hmask, vmask = lines_mask(gray)
    H, W = gray.shape
    # 只看「校系代碼」欄（表格最左側）的橫線來切列：術科類校系的檢定、倍率欄內部
    # 另有分隔線（學測／術科上下兩層），但那些線不會延伸到校系代碼欄。
    left = int(np.argmax(vmask[:, :W // 8].sum(axis=0)))   # 表格左框
    band = hmask[:, left + 8:left + 60]
    ys = runs(band.min(axis=1) > 0)
    rows = []
    for top, bot in zip(ys, ys[1:]):
        if bot - top < 18:
            continue
        mid = vmask[top + 4:bot - 3]
        xs = runs(mid.min(axis=0) > 0, min_gap=4) if len(mid) else []
        if len(xs) < 10:
            continue
        cell = lambda i, star=False: read_cell(img, xs[i], xs[i + 1], top, bot, star)
        code = cell(0)
        if not re.fullmatch(r"\d{6}", code):
            continue
        widths = [b - a for a, b in zip(xs, xs[1:])]
        n = len(widths)
        k = seq_count(widths)
        seqs = [cell(n - 1 - k + j) for j in range(k)]
        same = cell(n - 1, star=True)
        # 音樂類在招生名額後面多一欄「主修」（較寬、內容為中文樂器名稱）
        major = ""
        if widths[4] > widths[3] * 1.15:
            t = cell(4)
            if re.search(r"[\u4e00-\u9fff]", t) and "標" not in t:
                major = t
        rows.append({"code": code, "gender": cell(1), "quota": cell(3), "major": major,
                     "seqs": seqs, "same": same, "ncols": n, "nseq": k})
    return rows


def main():
    schools = dict(csv.reader(open(HERE / "申請115結果_原始資料" / "篩選標準學校清單.csv", encoding="utf-8-sig")))
    schools.pop("學校代碼", None)
    only = sys.argv[1:]
    db = sqlite3.connect(HERE / "apply115.db")
    ref = {c: (q, g, n, sk) for c, q, g, n, sk in db.execute(
        "select code, admit_quota, gender_requirement, dept_name, skill_test_required from departments")}
    subj, skill, apcs = {}, {}, {}
    for c, s_, st, m in db.execute("select code, subject_name, standard, multiplier from subject_screening"):
        subj.setdefault(c, {})[s_] = (st, m)
    for c, s_, st, m in db.execute("select code, item_name, standard, multiplier from skill_test_screening where item_name not in ('--','')"):
        skill.setdefault(c, []).append(f"{s_}(檢定{st or '--'}、倍率{m or '--'})")
    for c, s_, st, m in db.execute("select code, item_name, standard, multiplier from extra_screening"):
        apcs.setdefault(c, []).append(f"{s_}(檢定{st or '--'}、倍率{m or '--'})")

    # 主修樂器名稱以分發標準（網頁文字）的「術科項目別」校正 OCR 誤字，例如「理作曲」→「理論作曲」
    majors = {}
    for x in csv.DictReader(open(HERE / "115申請入學_分發標準.csv", encoding="utf-8-sig")):
        if x["術科項目別"] not in ("--", ""):
            majors.setdefault(x["校系代碼"], set()).add(x["術科項目別"])

    maxseq = 11
    head = (["學校代碼", "學校", "校系代碼", "性別要求", "校系名稱", "主修", "招生名額", "表格類別"]
            + [f"檢定_{s_}" for s_ in SUBJ + ["英聽"]] + [f"倍率_{s_}" for s_ in SUBJ] + ["倍率_學測科目組合", "術科或APCS篩選"]
            + [f"篩選順序{i}" for i in range(1, maxseq + 1)] + ["同級分超額篩選"])
    pat = re.compile(r"--|[\(\)（）\u4e00-\u9fffAB+APCS.]+\d+(\.\d+)?")
    out_rows, review = [], []
    for sc in sorted(schools):
        if only and sc not in only:
            continue
        rows = parse_image(IMG_DIR / f"{sc}.png")
        print(f"{sc} {schools[sc]}：{len(rows)} 列", flush=True)
        counts = {}
        for r in rows:
            counts[r["code"]] = counts.get(r["code"], 0) + 1
        for r in rows:
            code, issues = r["code"], []
            if code not in ref:
                issues.append("校系代碼不在分則")
                q_ref, g_ref, name, sk = "", "", "", ""
            else:
                q_ref, g_ref, name, sk = ref[code]
            if r["major"] and majors.get(code):
                best = difflib.get_close_matches(r["major"], majors[code], n=1, cutoff=0.3)
                if best:
                    r["major"] = best[0]
                else:
                    issues.append(f"主修無法對應分發標準：{r['major']}")
            multi = counts[code] > 1          # 同一校系分男女或分主修樂器，名額以圖片為準
            g = r["gender"]
            gender = "男" if "男" in g else "女" if "女" in g else "無"
            if r["quota"] != q_ref and not multi:
                issues.append(f"招生名額 OCR={r['quota']} 分則={q_ref}")
            if multi and gender == "無" and not r["major"]:
                issues.append("同一校系有多列，但辨識不出性別或主修")
            kind = ("APCS" if code in apcs else "音樂" if r["major"] else
                    "術科(美術/體育/音樂)" if r["nseq"] >= 11 else "一般")
            sub = subj.get(code, {})
            row = [sc, schools[sc], code, gender, name, r["major"], r["quota"], kind]
            row += [(sub.get(s_, ("--", "--"))[0] or "--") for s_ in SUBJ + ["英聽"]]
            row += [(sub.get(s_, ("--", "--"))[1] or "--") for s_ in SUBJ]
            row += ["、".join(f"{k}×{m}" for k, (st, m) in sub.items() if k not in SUBJ + ["英聽"] and m and m != "--") or "--"]
            row += ["；".join(apcs.get(code, []) or skill.get(code, [])) or "--"]
            seqs = r["seqs"] + ["--"] * (maxseq - len(r["seqs"]))
            for i, v in enumerate(r["seqs"], 1):
                if not pat.fullmatch(v):
                    issues.append(f"篩選順序{i} 格式可疑：{v}")
            if r["nseq"] not in (6, 11):
                issues.append(f"篩選順序欄數異常：{r['nseq']}")
            if r["same"] not in ("*", "--"):
                issues.append(f"同級分超額篩選 可疑：{r['same']}")
            out_rows.append(row + seqs + [r["same"]])
            if issues:
                review.append([sc, schools[sc], code, name, r["major"], "；".join(issues)])

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(head)
        w.writerows(out_rows)
    with open(REVIEW, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["學校代碼", "學校", "校系代碼", "校系名稱", "主修", "待確認內容"])
        w.writerows(review)
    print(f"寫出 {len(out_rows)} 列（{len({r[2] for r in out_rows})} 個校系），待確認 {len(review)} 列")


if __name__ == "__main__":
    main()
