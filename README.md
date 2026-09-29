# 115 志願選擇庫

依 115 學年度學測成績與五標，篩選繁星推薦、個人申請、分發入學的校系，並可加入選擇庫並排比較。

直接用瀏覽器開啟 `index.html` 即可使用（需與 `data.js` 放在同一資料夾）。

## 資料檔

| 檔案 | 內容 |
|---|---|
| `star115_校系分則.csv` / `star115.db` | 115 繁星推薦校系分則（64 校、1664 校系） |
| `apply115_校系分則.csv` / `apply115.db` | 115 個人申請校系分則（64 校、2206 校系） |
| `115分發入學_校系分則.csv` | 115 分發入學招生簡章校系分則（60 校、1764 學系） |
| `114分發入學_校系分則.csv` | 114 分發入學招生簡章校系分則（61 校、1780 學系） |
| `star_school_pct.json` | 繁星推薦各校「在校學業成績全校排名百分比」標準 |
| `data.js` | 網頁用資料，由 `build_data.py` 產生 |

資料來源：大學甄選入學委員會 115 學年度校系分則、大學分發入學招生簡章。

## 程式

| 檔案 | 用途 |
|---|---|
| `build_data.py` | 由 db / CSV 產生 `data.js` |
| `export_csv.py` | `apply115.db` 匯出 CSV |
| `export_star_csv.py` | `star115.db` 匯出 CSV |
| `parse_recruit_pdf.py` | 解析分發入學招生簡章 PDF：`uv run --with pdfplumber python parse_recruit_pdf.py <pdf> <輸出csv> <起始頁> <結束頁> <頁碼偏移>` |
