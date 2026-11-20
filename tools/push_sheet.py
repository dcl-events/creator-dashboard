"""管理シート「20万以上ダイヤライバーダッシュボード」へ名簿＋ダッシュボードURLを書き込む。
列は最新の creator_data TSV（毎朝のルーティン出力）から、URLは private/index.json から。"""
import csv, glob, json, os, datetime as dt
import gspread
ROOT = os.path.join(os.path.dirname(__file__), "..")
SHEET, GID = "1A-WSX4mteR-E5kY8V82dTUqoTcD0GDLA0Uq0qiDTzh4", 119268426
COLS = ["ライバー名", "バックステージリンク", "Liny URL", "データ期間", "クリエイターID",
        "クリエイターのユーザー名", "グループ", "クリエイターマネージャー"]
tsv = sorted(glob.glob(os.path.expanduser("~/Claude/tiktok-automation/out/creator_data_*.tsv")))[-1]
src = {r["クリエイターID"]: r for r in csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t")}
idx = json.load(open(os.path.join(ROOT, "private", "index.json")))
rows = []
for p in idx:  # 当月ダイヤの多い順
    r = src.get(p["id"], {})
    row = [r.get(c, "") for c in COLS]
    row[0] = row[0] or p["name"]; row[4] = p["id"]; row[5] = row[5] or p["username"]
    rows.append(row + [p["url"]])
gc = gspread.service_account(os.path.expanduser("~/Claude/pococha/service_account.json"))
ws = [w for w in gc.open_by_key(SHEET).worksheets() if w.id == GID][0]
ws.clear()
ws.update(range_name="A1", values=[[f"最終更新 {dt.datetime.now():%Y/%m/%d %H:%M}（対象＝当月or前月 20万ダイヤ以上・退会者除く）"],
                                   COLS + ["ダッシュボードURL"]] + rows, value_input_option="RAW")
print(f"{len(rows)}行を書き込み（元TSV: {os.path.basename(tsv)}）")
