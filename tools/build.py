"""TikTok LIVE クリエイター個別ダッシュボードのデータ生成。
最新の当月クリエイターデータ(N/DCL)から、当月 or 前月 20万ダイヤ以上の人を対象に
docs/data/<クリエイターID>.json を作る。日別推移は当月の日次xlsxから。"""
import glob, json, os, re, datetime as dt
import openpyxl, base64, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
DL = os.path.expanduser("~/Claude/tiktok-automation/downloads")
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "docs", "data")          # 公開：暗号文のみ
PRIV = os.path.join(ROOT, "private")              # 非公開：鍵・平文の一覧（git管理外）
BASE_URL = "https://dcl-events.github.io/creator-dashboard/"
os.makedirs(PRIV, exist_ok=True)
KEYS_F = os.path.join(PRIV, "keys.json")
keys = json.load(open(KEYS_F)) if os.path.exists(KEYS_F) else {}
b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
THRESH = 200_000
ROSTER_F = os.path.join(PRIV, "roster.json")   # {クリエイターID: 掲載開始月}。一度入ったら残す
roster = json.load(open(ROSTER_F)) if os.path.exists(ROSTER_F) else {cid: "2026-11" for cid in keys}
AGENCIES = {"Nグループ": "Nグループ", "DCL": "DCL"}

def num(v):
    try: return float(str(v).replace(",", ""))
    except: return None
def hours(v):
    if v in (None, "-", ""): return None
    s = str(v); h = re.search(r"(\d+)時間", s); m = re.search(r"(\d+)分", s); se = re.search(r"(\d+)秒", s)
    if not (h or m or se): return num(v)
    return round((int(h.group(1)) if h else 0) + (int(m.group(1)) if m else 0)/60 + (int(se.group(1)) if se else 0)/3600, 2)
def rows(f):
    r = list(openpyxl.load_workbook(f).active.iter_rows(values_only=True))
    h = r[0]; return [dict(zip(h, x)) for x in r[1:]]

files = {}
for ag in AGENCIES:
    fs = sorted(f for f in glob.glob(f"{DL}/{ag}_Backstage_TikTokLIVE/tt_creator_*.xlsx") if "asof" not in f)
    files[ag] = fs
latest_month = max(re.search(r"_(\d{6})_", f).group(1) for fs in files.values() for f in fs)

# ライバー名（表示名）＝毎朝のnicknames_*.json（creatorId→liverName）
names = {}
for ag in AGENCIES:
    ns = sorted(glob.glob(f"{DL}/{ag}_Backstage_TikTokLIVE/nicknames_*.json"))
    if ns:
        for x in json.load(open(ns[-1]))["rows"]:
            if x.get("liverName"): names[str(x["creatorId"])] = x["liverName"]

# アイコン＝毎朝のavatars_*.json。署名付きURLは数日で切れるので画像を落として暗号化JSONに埋め込む
import urllib.request
avatars = {}
for ag in AGENCIES:
    fs = sorted(glob.glob(f"{DL}/{ag}_Backstage_TikTokLIVE/avatars_*.json"))
    if fs:
        for x in json.load(open(fs[-1]))["rows"]:
            u = (x.get("raw") or {}).get("avatar")
            if u: avatars[str(x["creatorId"])] = u
def fetch_avatar(cid):
    u = avatars.get(cid)
    if not u: return None
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
            ctype = r.headers.get("Content-Type", "image/webp").split(";")[0]
            return f"data:{ctype};base64," + base64.b64encode(r.read()).decode()
    except Exception as e:
        print("avatar取得失敗", cid, e); return None

people = {}
for ag, fs in files.items():
    mfs = [f for f in fs if f"_{latest_month}_" in f]
    latest = mfs[-1]
    for r in rows(latest):
        cur, prev = num(r["ダイヤモンド"]) or 0, num(r["先月のダイヤモンド数"]) or 0
        cid = str(r["クリエイターID"])
        if not cid.isdigit(): continue  # 退会済みはIDが「クリエイターがエージェンシーを退会しました」になる
        # 一度20万ダイヤを超えて名簿に入った人は、下回っても消さない（退会だけが外れる条件）
        if max(cur, prev) >= THRESH:
            roster.setdefault(cid, f"{latest_month[:4]}-{latest_month[4:]}")
        elif cid not in roster: continue
        people[cid] = {
            "id": cid, "agency": ag, "username": r["クリエイターのユーザー名"], "name": names.get(str(r["クリエイターID"]), r["クリエイターのユーザー名"]),
            "period": r["データ期間"], "month": latest_month,
            "fetched": re.search(r"_(\d{4}-\d{2}-\d{2})_", latest).group(1),
            "asof": (dt.date.fromisoformat(re.search(r"_(\d{4}-\d{2}-\d{2})_", latest).group(1)) - dt.timedelta(days=2)).isoformat(),
            "cur": {"diamonds": cur, "live_hours": hours(r["LIVE時間"]), "valid_days": num(r["有効LIVE日数"]),
                    "new_followers": num(r["新規フォロワー"]), "match_count": num(r["LIVE Match数"]),
                    "match_diamonds": num(r["LIVE Matchで獲得したダイヤモンド数"]), "impressions": num(r["インプレッション"])},
            "prev": {"diamonds": prev, "live_hours": hours(r["先月のLIVE時間（時間）"]), "valid_days": num(r["先月の有効LIVE日数"])},
            "daily": [],
        }
    # 日別推移（各日次ファイル＝その時点の当月累計。Backstageは約2日遅れ）
    for f in mfs:
        d = (dt.date.fromisoformat(re.search(r"_(\d{4}-\d{2}-\d{2})_", f).group(1)) - dt.timedelta(days=2)).isoformat()
        if not d.startswith(f"{latest_month[:4]}-{latest_month[4:]}"): continue
        for r in rows(f):
            p = people.get(str(r["クリエイターID"]))
            if p: p["daily"].append({"date": d, "diamonds": num(r["ダイヤモンド"]) or 0,
                                     "live_hours": hours(r["LIVE時間"]) or 0, "valid_days": num(r["有効LIVE日数"]) or 0})
for p in people.values():
    seen = {}
    for x in p["daily"]: seen[x["date"]] = x
    p["daily"] = sorted(seen.values(), key=lambda x: x["date"])
    p["avatar"] = fetch_avatar(p["id"])
    # 1人ずつ固有の鍵でAES-GCM暗号化（鍵は一度作ったら固定＝配ったURLが変わらない）
    if p["id"] not in keys: keys[p["id"]] = b64(secrets.token_bytes(16))
    k = base64.urlsafe_b64decode(keys[p["id"]] + "==")
    iv = secrets.token_bytes(12)
    ct = AESGCM(k).encrypt(iv, json.dumps(p, ensure_ascii=False).encode(), None)
    json.dump({"v": 1, "iv": b64(iv), "ct": b64(ct)}, open(f"{OUT}/{p['id']}.enc.json", "w"))
    p["url"] = f"{BASE_URL}?id={p['id']}#k={keys[p['id']]}"
json.dump(keys, open(KEYS_F, "w"), indent=1)
json.dump(roster, open(ROSTER_F, "w"), indent=1)
for f in glob.glob(f"{OUT}/*.json"):   # 平文や対象外になった人の古いファイルを掃除
    if not any(f.endswith(f"/{i}.enc.json") for i in people): os.remove(f)
json.dump(sorted(({"id": p["id"], "username": p["username"], "name": p["name"], "agency": p["agency"],
                   "diamonds": p["cur"]["diamonds"], "url": p["url"],
                   "over_now": p["cur"]["diamonds"] >= THRESH, "since": roster[p["id"]]} for p in people.values()),
                 key=lambda x: -x["diamonds"]), open(f"{PRIV}/index.json", "w"), ensure_ascii=False, indent=1)
print(f"{latest_month}: {len(people)}人 → {OUT}")
