"""針對 ocr_apply_sieve.py 的待確認清單中「讀不出來」的格子（招生名額、倍率），以不同前處理重新辨識。

低解析度圖片（如 113 年）中單獨一個數字的格子常讀不出來；這裡把該格放大 3～4 倍、轉黑白後再辨識，
取第一個符合格式的結果寫回 CSV。仍讀不出的格子保留在待確認清單。
用法：uv run --with rapidocr-onnxruntime --with opencv-python-headless python reread_sieve_cells.py <學年度>
"""
import csv
import re
import sys
from pathlib import Path

import cv2
import numpy as np

YEAR = sys.argv[1]
sys.argv = [sys.argv[0], "--year", YEAR]           # 讓 ocr_apply_sieve 讀到同一個學年度
import ocr_apply_sieve as O                           # noqa: E402

HERE = Path(__file__).parent
SUBJ = O.SUBJ
COL = {"招生名額": 3, **{f"倍率_{s}": 11 + i for i, s in enumerate(SUBJ)}}
PAT = {"招生名額": re.compile(r"\d+"), "倍率": re.compile(r"--|\d+(\.\d+)?")}


def variants(cell):
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    for fx in (3, 4):
        big = cv2.resize(g, None, fx=fx, fy=fx, interpolation=cv2.INTER_CUBIC)
        _, bw = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for im in (big, bw):
            im = cv2.copyMakeBorder(im, 20, 20, 30, 30, cv2.BORDER_CONSTANT, value=255)
            yield cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)


def reread(img, x0, x1, y0, y1, kind):
    cell = img[y0 + 3:y1 - 2, x0 + 3:x1 - 2]
    for v in variants(cell):
        for det in (False, True):
            res, _ = O.ocr(v, use_det=det, use_cls=False)
            if not res:
                continue
            txt = "".join((r[1] if det else r[0]) for r in res).replace(" ", "").rstrip(".")
            if PAT[kind].fullmatch(txt):
                return txt
    return None


def row_bounds(img, code):
    """回傳該校系代碼所在列的 (top, bot, xs)（可能有多列，例如男女分列）。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, hmask, vmask = O.lines_mask(gray)
    W = gray.shape[1]
    left = int(np.argmax(vmask[:, :W // 8].sum(axis=0)))
    ys = O.runs(hmask[:, left + 8:left + 60].min(axis=1) > 0)
    for top, bot in zip(ys, ys[1:]):
        if bot - top < 18:
            continue
        xs = O.runs(vmask[top + 4:bot - 3].min(axis=0) > 0, min_gap=4)
        if len(xs) >= 10 and O.read_cell(img, xs[0], xs[1], top, bot) == code:
            yield top, bot, xs


review_f = HERE / f"{YEAR}申請入學_篩選標準_待確認.csv"
data_f = HERE / f"{YEAR}申請入學_篩選標準.csv"
review = list(csv.DictReader(open(review_f, encoding="utf-8-sig")))
rows = list(csv.reader(open(data_f, encoding="utf-8-sig")))
H = {h: i for i, h in enumerate(rows[0])}
todo = {}
for x in review:
    m = re.match(r"(招生名額|倍率_\S+?) 可疑", x["待確認內容"])
    if m and m.group(1) in COL:
        todo.setdefault((x["學校代碼"], x["校系代碼"]), set()).add(m.group(1))
fixed, left = 0, []
for (sc, code), fields in todo.items():
    img = cv2.imdecode(np.fromfile(str(O.IMG_DIR / f"{sc}.png"), dtype=np.uint8), cv2.IMREAD_COLOR)
    targets = [r for r in rows[1:] if r[H["校系代碼"]] == code]
    for (top, bot, xs), r in zip(row_bounds(img, code), targets):
        if len(xs) - 1 != len(O.COLS):
            continue
        for f in fields:
            v = reread(img, xs[COL[f]], xs[COL[f] + 1], top, bot, "招生名額" if f == "招生名額" else "倍率")
            if v is not None:
                print(f"{sc} {code} {f}：{r[H[f]] or '(空白)'} → {v}")
                r[H[f]] = v
                fixed += 1
            else:
                left.append((sc, code, f))
with open(data_f, "w", newline="", encoding="utf-8-sig") as fh:
    csv.writer(fh).writerows(rows)
print(f"重新辨識補上 {fixed} 格，仍讀不出 {len(left)} 格：{left}")
