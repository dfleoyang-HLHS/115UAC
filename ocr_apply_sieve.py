"""115 學年度申請入學「各校系篩選標準一覽表」圖片 → CSV（OCR）。

作法：
1. 用形態學偵測表格格線，找出每一個資料列（橫線之間）與該列的欄位分隔（直線）。
2. 逐格裁切，用 RapidOCR 辨識；「--」「*」這類符號用墨跡形狀判斷，避免 OCR 漏字。
3. 校系代碼、招生名額、檢定標準、篩選倍率與 115 校系分則（apply115.db）交叉核對，
   不一致的格子列入 115申請入學_篩選標準_待確認.csv。

用法：uv run --with rapidocr-onnxruntime --with opencv-python-headless python ocr_apply_sieve.py [--year 114] [學校代碼...]
輸出：{學年度}申請入學_篩選標準.csv
沒有該年度校系分則資料庫（apply{學年度}.db）時，檢定標準與篩選倍率改用 OCR 辨識並檢查格式，
校系名稱取自同年度分發標準網頁（文字）。
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
ARGS = sys.argv[1:]
YEAR = "115"
if ARGS[:1] == ["--year"]:
    YEAR, ARGS = ARGS[1], ARGS[2:]
FIX_ONLY = ARGS[:1] == ["--fix-only"]      # 不重新 OCR，只對既有 CSV 重新套用校正規則
if FIX_ONLY:
    ARGS = ARGS[1:]
RAW = HERE / f"申請{YEAR}結果_原始資料"
IMG_DIR = RAW / "篩選標準圖片"
OUT = HERE / f"{YEAR}申請入學_篩選標準.csv"
REVIEW = HERE / f"{YEAR}申請入學_篩選標準_待確認.csv"
DB = HERE / f"apply{YEAR}.db"
FULL_OCR = not DB.exists()          # 沒有同年度分則資料庫時，檢定與倍率也要辨識
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
        # 一般校系（25 欄）才能逐格對應檢定 7 欄與倍率 7 欄
        std = [cell(i) for i in range(4, 18)] if FULL_OCR and n == len(COLS) else []
        rows.append({"code": code, "gender": cell(1), "quota": cell(3), "major": major,
                     "seqs": seqs, "same": same, "ncols": n, "nseq": k, "std": std})
    return rows


# 篩選順序中會出現的科目與術科項目名稱，用來校正 OCR 誤字（如「彩缩技法」→「彩繪技法」）
VOCAB = ["國文", "英文", "數學A", "數學B", "社會", "自然", "素描", "彩繪技法", "水墨書畫", "創意表現", "美術鑑賞",
         "主修", "副修", "樂理", "視唱", "聽寫", "APCS識讀", "APCS實作", "體育百分等級", "程式識讀", "程式實作"]


SEQ_CHARS = str.maketrans({"敷": "數", "园": "國", "囤": "國", "曾": "會", "缩": "繪", "书": "畫", "现": "現", "级": "級", "题": "",
                           "國": "國", "术": "術", "赏": "賞", "画": "畫", "绘": "繪", "创": "創", "体": "體"})
ABBR_RE = re.compile(r"[國英數AB社自]+")


def fix_seq(v):
    m = re.fullmatch(r"(\(?)(.+?)(\)?)(\d+(?:\.\d+)?)", v)
    if not m:
        return v
    name = m.group(2).translate(SEQ_CHARS)
    toks = name.split("+") if "+" in name else [name]
    parts = []
    for t in toks:
        if t not in VOCAB and not (len(toks) == 1 and ABBR_RE.fullmatch(t)):
            best = difflib.get_close_matches(t, VOCAB, n=1, cutoff=0.5)
            # 跨行的長名稱常被截斷（「美術鑑賞」→「美衍T」）：字首只對應一個已知名稱時就用它
            same_head = [w for w in VOCAB if w[0] == t[:1]]
            t = best[0] if best else same_head[0] if len(same_head) == 1 else t
        parts.append(t)
    return f"{m.group(1)}{'+'.join(parts)}{m.group(3)}{m.group(4)}"


def postfix(rows, head, order):
    """rows：CSV 資料列（list）。套用招生名額、主修、篩選順序的校正，回傳 (rows, 待確認清單)。"""
    H = {h: i for i, h in enumerate(head)}
    by_code = {}
    for r in rows:
        by_code.setdefault(r[H["校系代碼"]], []).append(r)
    review = []
    for code, rs in by_code.items():
        want = order.get(code, [])
        # 主修：同校系列數與分發標準的樂器數相同時，依分發標準的順序指派（圖片與網頁排列順序一致）
        if want and len(want) == len(rs):
            for r, m in zip(rs, want):
                r[H["主修"]] = m
        for r in rs:
            if r[H["主修"]] and r[H["主修"]] not in want:
                if want:
                    best = difflib.get_close_matches(r[H["主修"]], want, n=1, cutoff=0.3)
                    r[H["主修"]] = best[0] if best else r[H["主修"]]
                    if not best:
                        review.append([r[0], r[1], code, r[H["校系名稱"]], r[H["主修"]], "主修無法對應分發標準"])
                else:
                    r[H["主修"]] = ""          # 非音樂校系卻讀出「主修」，是檢定欄被誤判
                    if r[H["表格類別"]] == "音樂":
                        r[H["表格類別"]] = "APCS" if "APCS" in " ".join(r) else "一般"
            q = re.sub(r"\D+$", "", r[H["招生名額"]])     # 「2.」「22.」：數字後多出的雜點
            r[H["招生名額"]] = q
            if not re.fullmatch(r"\d+", q):
                review.append([r[0], r[1], code, r[H["校系名稱"]], r[H["主修"]], f"招生名額 可疑：{q}"])
            for i in range(1, 12):
                k = H[f"篩選順序{i}"]
                r[k] = fix_seq(r[k])
    return rows, review


def main():
    schools = dict(csv.reader(open(RAW / "篩選標準學校清單.csv", encoding="utf-8-sig")))
    schools.pop("學校代碼", None)
    only = ARGS
    ref, subj, skill, apcs = {}, {}, {}, {}
    # 主修樂器名稱以分發標準（網頁文字）的「術科項目別」校正 OCR 誤字，例如「理作曲」→「理論作曲」
    majors, names, ent_sex, order = {}, {}, {}, {}
    for x in csv.DictReader(open(HERE / f"{YEAR}申請入學_分發標準.csv", encoding="utf-8-sig")):
        names[x["校系代碼"]] = x["學系(組)名稱"]
        if x["名額類別"] == "招生" and x["術科項目別"] not in ("--", "") and x["術科項目別"] not in order.get(x["校系代碼"], []):
            order.setdefault(x["校系代碼"], []).append(x["術科項目別"])
        if x["名額類別"] == "招生" and x["性別限制"] in ("男", "女"):
            ent_sex.setdefault(x["校系代碼"], []).append(x["性別限制"])
        if x["術科項目別"] not in ("--", ""):
            majors.setdefault(x["校系代碼"], set()).add(x["術科項目別"])
    if not FULL_OCR:
        db = sqlite3.connect(DB)
        ref = {c: (q, g, n, sk) for c, q, g, n, sk in db.execute(
            "select code, admit_quota, gender_requirement, dept_name, skill_test_required from departments")}
        for c, s_, st, m in db.execute("select code, subject_name, standard, multiplier from subject_screening"):
            subj.setdefault(c, {})[s_] = (st, m)
        for c, s_, st, m in db.execute("select code, item_name, standard, multiplier from skill_test_screening where item_name not in ('--','')"):
            skill.setdefault(c, []).append(f"{s_}(檢定{st or '--'}、倍率{m or '--'})")
        for c, s_, st, m in db.execute("select code, item_name, standard, multiplier from extra_screening"):
            apcs.setdefault(c, []).append(f"{s_}(檢定{st or '--'}、倍率{m or '--'})")
    std_pat = re.compile(r"--|頂標|前標|均標|後標|底標|[ABC]級?")
    mul_pat = re.compile(r"--|\d+(\.\d+)?")

    maxseq = 11
    head = (["學校代碼", "學校", "校系代碼", "性別要求", "校系名稱", "主修", "招生名額", "表格類別"]
            + [f"檢定_{s_}" for s_ in SUBJ + ["英聽"]] + [f"倍率_{s_}" for s_ in SUBJ] + ["倍率_學測科目組合", "術科或APCS篩選"]
            + [f"篩選順序{i}" for i in range(1, maxseq + 1)] + ["同級分超額篩選"])
    pat = re.compile(r"--|[\(\)（）\u4e00-\u9fffAB+APCS.]+\d+(\.\d+)?")
    out_rows, review = [], []
    if FIX_ONLY:
        old = list(csv.reader(open(OUT, encoding="utf-8-sig")))
        rows, review = postfix(old[1:], old[0], order)
        with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows([old[0]] + rows)
        with open(REVIEW, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["學校代碼", "學校", "校系代碼", "校系名稱", "主修", "待確認內容"])
            w.writerows(review)
        print(f"校正完成：{len(rows)} 列，待確認 {len(review)} 列")
        return
    for sc in sorted(schools):
        if only and sc not in only:
            continue
        rows = parse_image(IMG_DIR / f"{sc}.png")
        print(f"{sc} {schools[sc]}：{len(rows)} 列", flush=True)
        counts, seen = {}, {}
        for r in rows:
            counts[r["code"]] = counts.get(r["code"], 0) + 1
        for r in rows:
            code, issues = r["code"], []
            if FULL_OCR:
                q_ref, name = r["quota"], names.get(code, "")
                if not name:
                    issues.append("校系代碼不在分發標準")
                if not re.fullmatch(r"\d+", r["quota"]):
                    issues.append(f"招生名額 可疑：{r['quota']}")
            elif code not in ref:
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
            # 男女分列但 OCR 讀不出時，依分發標準網頁同校系「招生」列的性別限制順序補上
            idx = seen[code] = seen.get(code, -1) + 1
            if gender == "無" and multi and not r["major"] and idx < len(ent_sex.get(code, [])):
                gender = ent_sex[code][idx]
            if r["quota"] != q_ref and not multi:
                issues.append(f"招生名額 OCR={r['quota']} 分則={q_ref}")
            if multi and gender == "無" and not r["major"]:
                issues.append("同一校系有多列，但辨識不出性別或主修")
            kind = ("APCS" if code in apcs or (FULL_OCR and r["ncols"] != len(COLS) and r["nseq"] == 6) else "音樂" if r["major"] else
                    "術科(美術/體育/音樂)" if r["nseq"] >= 11 else "一般")
            row = [sc, schools[sc], code, gender, name, r["major"], r["quota"], kind]
            if FULL_OCR:
                st = r["std"] or [""] * 14          # 術科／APCS 表格的檢定、倍率為上下兩層，不逐格辨識
                std7 = [re.sub(r"級$", "", v) if i == 6 else v for i, v in enumerate(st[:7])]
                for nm, v in zip(SUBJ + ["英聽"], std7):
                    if v and not std_pat.fullmatch(v):
                        issues.append(f"檢定_{nm} 可疑：{v}")
                for nm, v in zip(SUBJ + ["學測科目組合"], st[7:14]):
                    if v and not mul_pat.fullmatch(v):
                        issues.append(f"倍率_{nm} 可疑：{v}")
                row += std7 + st[7:14] + ["見原始圖片" if not r["std"] else "--"]
            else:
                sub = subj.get(code, {})
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

    out_rows, extra = postfix(out_rows, head, order)
    review = [x for x in review if not re.search(r"招生名額|主修無法", x[-1])] + extra
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
