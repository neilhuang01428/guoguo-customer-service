#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
# radar.py — 選題雷達：供給面（YouTube 語料）× 需求面（Google 自動完成）雙面掃描
#
#   這支工具回答一個問題：「哪些主題大家在搜、但創作者還沒怎麼做？」
#   供給面＝11 個 3C 頻道的字幕檔「檔名」命中各主題關鍵詞的數量（不精讀內文）；
#   需求面＝Google 自動完成對種子詞的擴張數量（台灣區＋美國區）。
#   兩面交叉成四象限：紅海／金礦／泡沫／沙漠，金礦（低供給×高需求）就是該寫的題。
#
#   三個子命令：
#     sync    三路收集，只寫檔案、不做判斷：
#             a. bootstrap：掃既有檔名建 yt-dlp 下載紀錄（_archive.txt），避免重抓整批
#             b. channels：用一支影片反查每個頻道的網址，回填 radar.json
#             c. videos：yt-dlp 增量抓每頻道最新 30 支的自動字幕 → 轉純文字入語料庫
#             d. suggest：Google 自動完成（TW＋US 兩區）→ context/radar/raw/suggest/
#             e. official：官方頁面存檔＋與前次 diff → context/radar/raw/official/
#     scan    讀語料檔名＋最新 suggest 資料，算雙面象限，產出 4 個檔案
#     report  比對最近兩張月快照，產變化報告（首月只有一張時提示下月起可用）
#
#   設定檔：scripts/radar.json（channels / topics / topic_seeds / seeds / thresholds）
#   輸出：context/radar/（已在 .gitignore，內容不對外）
#   ⚠️ 語料庫 research/3c/youtube 是另一個 git repo：本工具只寫檔案，絕不 git 操作。
# ─────────────────────────────────────────────────────────────
import argparse
import datetime
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# ── 路徑與常數 ────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)                     # repo 根（Guoguo_Customer_Service）
CONFIG_PATH = os.path.join(SCRIPT_DIR, "radar.json")
RADAR_DIR = os.path.join(ROOT, "context", "radar")     # 所有雷達輸出（已 gitignore）
SUGGEST_DIR = os.path.join(RADAR_DIR, "raw", "suggest")
OFFICIAL_DIR = os.path.join(RADAR_DIR, "raw", "official")
SNAPSHOT_DIR = os.path.join(RADAR_DIR, "snapshots")

YTDLP = "/opt/homebrew/bin/yt-dlp"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TODAY = datetime.date.today().isoformat()              # 例：2026-07-25
THIS_MONTH = TODAY[:7]                                 # 例：2026-07

# 檔名結尾的 video ID：11 碼 [A-Za-z0-9_-]（語料已驗證 100% 符合）
ID_RE = re.compile(r"_([A-Za-z0-9_-]{11})\.txt$")
# 問句庫用的疑問詞
QUESTION_RE = re.compile(r"嗎|怎麼|為什麼|該不該|值不值得|差在哪|哪個|要不要")
# 問句庫的產品分群順序（iPad 排最前＝果果主戰場）
PRODUCT_ORDER = ["iPad", "Pencil", "iPhone", "Mac", "Watch", "AirPods"]

OK = "✓"
NG = "✗"


# ── 執行紀錄器：warning／error 分級、結尾彙總、決定 exit code ──
class Log:
    """收集警告與錯誤，最後彙總；有 error 級失敗時 exit code 非 0（fail loudly）。"""

    def __init__(self):
        self.warnings = []
        self.errors = []

    def ok(self, msg):
        print(f"  {OK} {msg}")

    def info(self, msg):
        print(f"  · {msg}")

    def warn(self, msg):
        self.warnings.append(msg)
        print(f"  ⚠ {msg}", file=sys.stderr)

    def err(self, msg):
        self.errors.append(msg)
        print(f"  {NG} {msg}", file=sys.stderr)

    def finish(self, name):
        """印出彙總並回傳建議的 exit code。"""
        print()
        print(f"── {name} 結束彙總 " + "─" * 30)
        if not self.warnings and not self.errors:
            print(f"  {OK} 全部成功，無警告、無錯誤")
            return 0
        if self.warnings:
            print(f"  ⚠ 警告 {len(self.warnings)} 件：", file=sys.stderr)
            for w in self.warnings:
                print(f"    - {w}", file=sys.stderr)
        if self.errors:
            print(f"  {NG} 錯誤 {len(self.errors)} 件：", file=sys.stderr)
            for e in self.errors:
                print(f"    - {e}", file=sys.stderr)
            return 1
        return 0


# ── 設定檔 ────────────────────────────────────────────────────
def load_config():
    """讀 scripts/radar.json；壞掉時直接報錯（設定檔是一切的根）。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"{NG} 找不到設定檔 {CONFIG_PATH}，請先建立 radar.json")
    except json.JSONDecodeError as e:
        sys.exit(f"{NG} 設定檔 {CONFIG_PATH} 不是合法 JSON：{e}")


def save_config(cfg):
    """把（回填頻道網址後的）設定寫回 radar.json，保留中文可讀。"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── 小工具 ────────────────────────────────────────────────────
def quantile(values, q):
    """線性插值分位數（等同 numpy 預設法）；判定線一律走這裡，不硬編碼絕對值。"""
    xs = sorted(values)
    if not xs:
        return 0.0
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def sanitize_title(title):
    """把影片標題清成語料庫既有檔名風格：只留字母數字（含中日文）、空格、連字號。

    既有 13,270 個檔名統計過：標點（【】｜！？.）都是「移除」而非換成空格，
    例：iOS 18.3 → iOS 183。這裡照同樣規則處理，維持全庫一致。
    """
    kept = "".join(ch for ch in title if ch.isalnum() or ch in " -")
    kept = re.sub(r"\s+", " ", kept).strip()
    return kept[:120] or "untitled"


def list_corpus_txt(corpus_dir, channels):
    """列出語料庫全部 .txt：回傳 [(頻道, 檔名)]，忽略 .DS_Store 與 _archive.txt。"""
    out = []
    for ch in channels:
        ch_dir = os.path.join(corpus_dir, ch)
        if not os.path.isdir(ch_dir):
            continue
        for name in sorted(os.listdir(ch_dir)):
            if name.startswith(".") or not name.endswith(".txt"):
                continue
            out.append((ch, name))
    return out


def fetch_url(url, timeout=30):
    """帶瀏覽器 UA 抓網頁，回傳解碼後文字。任何失敗往上丟，由呼叫端記錄。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def html_to_text(src):
    """粗略抽純文字：去 script／style／註解／標籤，供官方頁存檔與 diff 用。"""
    src = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", src)
    src = re.sub(r"(?is)<!--.*?-->", " ", src)
    src = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>|</section>", "\n", src)
    src = re.sub(r"(?is)<[^>]+>", " ", src)
    src = html.unescape(src)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in src.splitlines()]
    return "\n".join(ln for ln in lines if ln) + "\n"


def url_slug(url):
    """網址轉存檔用 slug：support.apple.com/zh-tw → support-apple-com-zh-tw。"""
    bare = re.sub(r"^https?://", "", url.lower())
    return re.sub(r"[^a-z0-9]+", "-", bare).strip("-")[:80]


def vtt_to_txt(vtt_text):
    """YouTube 自動字幕 VTT → 語料庫既有純文字格式。

    保留 VTT 開頭的 `Kind: captions`／`Language: xx` 兩行當 header（既有檔案就是這樣），
    去掉 WEBVTT 行、時間軸行、行內 <c>／<00:00:00.000> 標記，並去掉連續重複行
    （自動字幕逐字捲動會讓同一句出現兩次）。
    """
    header, body, prev = [], [], None
    for raw in vtt_text.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT":
            continue
        if line.startswith(("Kind:", "Language:")):
            header.append(line)
            continue
        if "-->" in line or line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if re.fullmatch(r"\d+", line):        # cue 編號（保險）
            continue
        text = html.unescape(re.sub(r"<[^>]+>", "", line))
        text = re.sub(r"\s+", " ", text).strip()   # &nbsp;（\xa0）等空白統一，去重才對得上
        if not text or text == prev:
            continue
        body.append(text)
        prev = text
    return "\n".join(header + body) + "\n"


# ═════════════════════════════════════════════════════════════
# sync — 三路收集，只寫檔案、不做判斷
# ═════════════════════════════════════════════════════════════
def sync_bootstrap(cfg, log):
    """a. 建 yt-dlp 下載紀錄：掃全部既有檔名抽 video ID → _archive.txt。

    這是關鍵第一步：沒有這份紀錄，第一次增量會把 13,270 支全部重抓一遍。
    """
    corpus = cfg["corpus_dir"]
    archive = os.path.join(corpus, "_archive.txt")
    print("【sync a】Bootstrap 下載紀錄（_archive.txt）")
    if os.path.exists(archive):
        with open(archive, encoding="utf-8") as f:
            n = sum(1 for _ in f)
        log.ok(f"_archive.txt 已存在（{n:,} 行），略過 bootstrap")
        return archive

    files = list_corpus_txt(corpus, cfg["channels"])
    ids, seen, bad = [], set(), 0
    for _, name in files:
        m = ID_RE.search(name)
        if not m:
            bad += 1
            continue
        vid = m.group(1)
        if vid not in seen:      # 同支影片若出現在兩個資料夾，紀錄一次即可
            seen.add(vid)
            ids.append(vid)
    with open(archive, "w", encoding="utf-8") as f:
        for vid in ids:
            f.write(f"youtube {vid}\n")
    log.ok(f"掃描 {len(files):,} 個檔名 → 寫入 {len(ids):,} 行下載紀錄：{archive}")
    if bad:
        log.warn(f"有 {bad} 個檔名抽不出 video ID（不影響其他檔案）")
    if len(ids) != len(files):
        log.info(f"檔名 {len(files):,} 筆、唯一 ID {len(ids):,} 筆（差額為跨資料夾重複）")
    return archive


def sync_channels(cfg, log):
    """b. 解析頻道網址：從資料夾挑一支影片 → yt-dlp 反查 channel_url → 回填 radar.json。"""
    corpus = cfg["corpus_dir"]
    print("【sync b】解析頻道網址（回填 radar.json）")
    changed = False
    for i, (name, url) in enumerate(cfg["channels"].items(), 1):
        if url:
            log.info(f"[{i:2}/{len(cfg['channels'])}] {name}：已有網址，跳過")
            continue
        ch_dir = os.path.join(corpus, name)
        candidates = [f for f in sorted(os.listdir(ch_dir))
                      if f.endswith(".txt") and ID_RE.search(f)] if os.path.isdir(ch_dir) else []
        if not candidates:
            log.err(f"頻道 {name}：資料夾內找不到可用檔名，請檢查 radar.json 手動填入 url")
            continue
        resolved = None
        for attempt, fname in enumerate(candidates[:3], 1):   # 影片可能已下架，最多換 3 支重試
            vid = ID_RE.search(fname).group(1)
            try:
                r = subprocess.run(
                    [YTDLP, "--print", "channel_url", f"https://youtu.be/{vid}"],
                    capture_output=True, text=True, timeout=90)
                out = r.stdout.strip()
                if r.returncode == 0 and out.startswith("http"):
                    resolved = out
                    break
                log.info(f"{name}：第 {attempt} 次（{vid}）失敗，換一支影片重試")
            except (subprocess.TimeoutExpired, OSError) as e:
                log.info(f"{name}：第 {attempt} 次（{vid}）例外 {e}，換一支影片重試")
        if resolved:
            cfg["channels"][name] = resolved
            changed = True
            log.ok(f"[{i:2}/{len(cfg['channels'])}] {name} → {resolved}")
        else:
            log.err(f"頻道 {name} 解析失敗 3 次，請檢查 radar.json 手動填入 url（channels.{name}）")
    if changed:
        save_config(cfg)
        log.ok("已把頻道網址回填 scripts/radar.json")


def load_meta_ids(meta_path):
    """讀 meta.jsonl 既有的 video ID，避免重複附加。"""
    ids = set()
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            for line in f:
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return ids


def update_archive(archive, add_ids, drop_ids):
    """雙向校正下載紀錄：字幕到手的影片必須在紀錄裡；沒到手的必須不在。

    背景：yt-dlp 只在「真的有下載到東西」時才寫紀錄，而且寫入時機在下載完成後。
    - add：字幕已寫進語料庫的影片，補進紀錄（避免下次重抓）。
    - drop：這次沒抓到字幕的影片（字幕還沒生成／YouTube 暫時不給匿名 session
      字幕軌），從紀錄移除讓下次 sync 重試；影片掉出「每頻道最新 N 支」窗口
      後就不再重試，不會無限累積。
    """
    with open(archive, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    have = set(lines)
    drop = {f"youtube {vid}" for vid in drop_ids}
    out = [ln for ln in lines if ln not in drop]
    out += [f"youtube {vid}" for vid in add_ids if f"youtube {vid}" not in have]
    if out != lines:
        with open(archive, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")


def sync_videos(cfg, log, only=None, playlist_end=30):
    """c. 增量抓新字幕：yt-dlp 讀下載紀錄，只抓每頻道最新 N 支中沒抓過的。

    流程：字幕輸出到暫存資料夾（<id>.<lang>.vtt）＋ metadata 寫 meta.tsv →
    轉成語料庫格式 `標題_ID.txt` 存進對應頻道資料夾 → metadata 附進 meta.jsonl。
    """
    corpus = cfg["corpus_dir"]
    archive = os.path.join(corpus, "_archive.txt")
    meta_path = os.path.join(corpus, "meta.jsonl")
    print(f"【sync c】增量抓新字幕（每頻道最新 {playlist_end} 支）")
    if not os.path.exists(archive):
        log.err("_archive.txt 不存在，請先跑 bootstrap（否則會重抓整批 13,270 支）")
        return {}

    known_meta = load_meta_ids(meta_path)
    targets = {k: v for k, v in cfg["channels"].items() if (only is None or k == only)}
    stats = {}
    for i, (name, url) in enumerate(targets.items(), 1):
        prefix = f"[{i:2}/{len(targets)}] {name}"
        if not url:
            log.err(f"{prefix}：radar.json 沒有頻道網址，請先跑 sync --steps channels")
            continue
        videos_url = url.rstrip("/") + ("" if url.rstrip("/").endswith("/videos") else "/videos")
        tmp = tempfile.mkdtemp(prefix=f"guoguo-radar-{i:02}-")
        meta_tsv = os.path.join(tmp, "meta.tsv")
        cmd = [
            YTDLP, videos_url,
            "--download-archive", archive,
            "--playlist-end", str(playlist_end),
            "--skip-download",
            "--write-auto-subs",
            "--sub-langs", "zh-Hant,zh-TW,zh",
            "--sub-format", "vtt",
            "-o", f"subtitle:{tmp}/%(id)s.%(ext)s",
            "--print-to-file", "\t".join(["%(id)s", "%(title)s", "%(channel)s", "%(upload_date)s"]), meta_tsv,
            "--no-simulate",
            "--ignore-errors",
        ]
        print(f"  … {prefix}：抓取中（{videos_url}）")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            log.err(f"{prefix}：yt-dlp 超過 15 分鐘未完成，本頻道略過（可單獨重跑：--steps videos --only {name}）")
            continue
        combined = r.stdout + r.stderr
        skipped = combined.count("has already been recorded in the archive")

        # 解析 meta.tsv（只有「新處理」的影片會被寫進來；已在紀錄裡的不會）
        new_rows = []
        if os.path.exists(meta_tsv):
            with open(meta_tsv, encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 4:
                        new_rows.append({"id": parts[0], "title": parts[1],
                                         "channel": parts[2], "upload_date": parts[3]})

        # vtt → txt，存進語料庫（不覆寫既有檔案）
        wrote, no_sub = 0, 0
        got_ids, retry_ids = [], []
        for row in new_rows:
            vid = row["id"]
            vtts = sorted(glob.glob(os.path.join(tmp, f"{vid}.*.vtt")))
            # 同支影片可能同時有 zh-Hant／zh-TW／zh 三種字幕，挑優先序最高的一份
            pick = None
            for lang in ("zh-Hant", "zh-TW", "zh"):
                hit = [p for p in vtts if p.endswith(f".{lang}.vtt")]
                if hit:
                    pick = hit[0]
                    break
            if pick is None and vtts:
                pick = vtts[0]
            if pick is None:
                no_sub += 1        # 沒抓到中文字幕（還沒生成／YouTube 暫時不給），記 metadata 並排入重試
                retry_ids.append(vid)
            else:
                with open(pick, encoding="utf-8") as f:
                    txt = vtt_to_txt(f.read())
                out_name = f"{sanitize_title(row['title'])}_{vid}.txt"
                out_path = os.path.join(corpus, name, out_name)
                if os.path.exists(out_path):
                    log.info(f"{name}：{out_name} 已存在，不覆寫")
                else:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(txt)
                    wrote += 1
                got_ids.append(vid)
            if vid not in known_meta:   # metadata 一律附進 meta.jsonl（含沒字幕的）
                with open(meta_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                known_meta.add(vid)

        update_archive(archive, got_ids, retry_ids)   # 雙向校正下載紀錄（詳見函式說明）

        stats[name] = {"new": len(new_rows), "wrote": wrote, "no_sub": no_sub, "skipped": skipped}
        note = f"新影片 {len(new_rows)} 支（寫入字幕 {wrote}、未取得字幕 {no_sub}、已在庫略過 {skipped}）"
        if retry_ids:
            note += "；未取得字幕者不列入下載紀錄，下次 sync 自動重試"
        if r.returncode == 0:
            log.ok(f"{prefix}：{note}")
        else:
            # --ignore-errors 下 exit 1 通常是個別影片（會員限定／已下架）失敗，整體照常
            log.warn(f"{prefix}：{note}；yt-dlp exit {r.returncode}，個別影片可能失敗（會員限定／已下架）")

    # 全體檢視：有新影片卻一支字幕都沒抓到，多半是 YouTube 對匿名工具的字幕封鎖，要講清楚
    total_new = sum(s["new"] for s in stats.values())
    total_wrote = sum(s["wrote"] for s in stats.values())
    if total_new > 0 and total_wrote == 0:
        log.warn("本次偵測到新影片但一支字幕都沒抓到——目前 YouTube 對無 PO token 的匿名工具"
                 "不回傳字幕軌（連舊影片也一樣，已驗證非影片本身問題）。metadata 已記錄、"
                 "影片會自動重試；要恢復字幕抓取，可考慮安裝 bgutil-ytdlp-pot-provider "
                 "或讓 yt-dlp 帶登入 cookies（需 Neil 決定）。")
    return stats


def sync_suggest(cfg, log):
    """d. Google 自動完成：seeds_tw（台灣區）＋ seeds_us（美國區）逐一查詢。

    已知行為：查詢含空格有時回空陣列——「空」是合法結果照記；
    HTTP 錯誤／JSON 解析失敗才是錯誤。每一筆都記 status（ok/empty/error），
    錯誤絕不靜默當成空。
    """
    print("【sync d】Google 自動完成（TW＋US）")
    os.makedirs(SUGGEST_DIR, exist_ok=True)
    plan = ([("tw", "zh-TW", "tw", q) for q in cfg["seeds_tw"]] +
            [("us", "en", "us", q) for q in cfg["seeds_us"]])
    results = []
    counts = {"ok": 0, "empty": 0, "error": 0}
    flag = {"tw": "🇹🇼", "us": "🇺🇸"}
    for i, (region, hl, gl, q) in enumerate(plan, 1):
        url = ("https://suggestqueries.google.com/complete/search"
               f"?client=firefox&hl={hl}&gl={gl}&q={urllib.parse.quote(q)}")
        entry = {"query": q, "region": region, "status": None, "suggestions": []}
        try:
            raw = fetch_url(url, timeout=20)
            parsed = json.loads(raw)
            sugg = parsed[1] if isinstance(parsed, list) and len(parsed) > 1 else []
            sugg = [s for s in sugg if isinstance(s, str)]
            entry["suggestions"] = sugg
            entry["status"] = "ok" if sugg else "empty"
            counts[entry["status"]] += 1
            mark = OK if sugg else "∅"
            print(f"  {mark} [{i:2}/{len(plan)}] {flag[region]} {q} → {len(sugg)} 條")
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
                TimeoutError, OSError) as e:
            entry["status"] = "error"
            entry["error"] = f"{type(e).__name__}: {e}"
            counts["error"] += 1
            log.err(f"[{i:2}/{len(plan)}] {flag[region]} {q} 查詢失敗：{entry['error']}（此筆是「失敗」不是「空」）")
        results.append(entry)
        time.sleep(1.1)     # 禮貌間隔 ≥1 秒，避免被擋

    out_path = os.path.join(SUGGEST_DIR, f"{TODAY}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"date": TODAY,
                   "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                   "summary": counts,
                   "results": results}, f, ensure_ascii=False, indent=2)
    log.ok(f"自動完成彙總：成功 {counts['ok']}／空 {counts['empty']}／失敗 {counts['error']} → {out_path}")
    return counts


def parse_official_pages(cfg):
    """讀官方入口清單：radar.json 的 official_pages 留空時，改讀 skill 文件裡的表格。"""
    pages = cfg.get("official_pages") or []
    if pages:
        return [(p["name"], p["url"]) for p in pages]
    src = os.path.join(ROOT, cfg["official_pages_source"])
    rows = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^\|\s*([^|]+?)\s*\|\s*(https?://\S+)\s*\|", line)
            if m:
                rows.append((m.group(1), m.group(2)))
    return rows


def sync_official(cfg, log):
    """e. 官方頁存檔：逐頁抓下轉純文字，存日期資料夾；有前次存檔就逐檔 diff。"""
    print("【sync e】官方頁存檔＋變動偵測")
    pages = parse_official_pages(cfg)
    if not pages:
        log.err("官方入口清單是空的：請檢查 radar.json 的 official_pages 或 skill 文件表格")
        return
    today_dir = os.path.join(OFFICIAL_DIR, TODAY)
    os.makedirs(today_dir, exist_ok=True)

    # 找更早日期的資料夾（diff 基準）
    prev_dirs = sorted(d for d in glob.glob(os.path.join(OFFICIAL_DIR, "????-??-??"))
                       if os.path.isdir(d) and os.path.basename(d) < TODAY)
    prev_dir = prev_dirs[-1] if prev_dirs else None

    fetch_log, changed = [], []
    for i, (name, url) in enumerate(pages, 1):
        slug = url_slug(url)
        try:
            text = html_to_text(fetch_url(url, timeout=40))
            out_path = os.path.join(today_dir, f"{slug}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            status = "ok"
            log.ok(f"[{i:2}/{len(pages)}] {name} → {slug}.txt（{len(text):,} 字）")
            # 與前次存檔比對
            if prev_dir:
                prev_path = os.path.join(prev_dir, f"{slug}.txt")
                if os.path.exists(prev_path):
                    with open(prev_path, encoding="utf-8") as f:
                        if f.read() != text:
                            changed.append((name, slug))
                else:
                    changed.append((name, f"{slug}（前次無存檔，視為新增）"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            status = f"error: {type(e).__name__}: {e}"
            log.err(f"[{i:2}/{len(pages)}] {name}（{url}）抓取失敗：{e}——單頁失敗不中斷其他頁")
        fetch_log.append({"name": name, "url": url, "slug": slug, "status": status})
        time.sleep(1.0)     # 對官方站也保持禮貌間隔

    # 抓取紀錄（scan 的錯誤區塊會讀這份，分清「查到 0」與「查詢失敗」）
    with open(os.path.join(today_dir, "_fetch-log.json"), "w", encoding="utf-8") as f:
        json.dump({"date": TODAY, "prev_dir": prev_dir, "pages": fetch_log},
                  f, ensure_ascii=False, indent=2)

    if prev_dir:
        lines = [f"# 官方頁變動清單（{os.path.basename(prev_dir)} → {TODAY}）", ""]
        if changed:
            lines += [f"- {name}：`{slug}`" for name, slug in changed]
        else:
            lines.append("本次比對：全部頁面無變動。")
        with open(os.path.join(today_dir, "changed.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        log.ok(f"與 {os.path.basename(prev_dir)} 比對：{len(changed)} 頁有變動 → changed.md")
    else:
        log.info("沒有更早日期的存檔，本次為首次基準（下次起會自動 diff）")


def cmd_sync(args):
    """sync 主流程：依 --steps 順序執行 a~e。"""
    log = Log()
    cfg = load_config()
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    valid = {"bootstrap", "channels", "videos", "suggest", "official"}
    unknown = set(steps) - valid
    if unknown:
        sys.exit(f"{NG} 不認識的步驟：{'、'.join(unknown)}（可用：{'、'.join(sorted(valid))}）")

    if "bootstrap" in steps:
        sync_bootstrap(cfg, log)
    if "channels" in steps:
        sync_channels(cfg, log)
    if "videos" in steps:
        sync_videos(cfg, log, only=args.only, playlist_end=args.playlist_end)
    if "suggest" in steps:
        sync_suggest(cfg, log)
    if "official" in steps:
        sync_official(cfg, log)
    sys.exit(log.finish("sync"))


# ═════════════════════════════════════════════════════════════
# scan — 讀語料檔名＋最新 suggest 資料，算雙面象限
# ═════════════════════════════════════════════════════════════
def latest_suggest():
    """找最新一份 suggest 存檔；沒有就回 None（scan 會 fail loudly）。"""
    files = sorted(glob.glob(os.path.join(SUGGEST_DIR, "????-??-??.json")))
    if not files:
        return None, None
    with open(files[-1], encoding="utf-8") as f:
        return os.path.basename(files[-1])[:-5], json.load(f)


def latest_official_log():
    """找最新一份官方頁抓取紀錄（給錯誤區塊用）；沒有回 None。"""
    logs = sorted(glob.glob(os.path.join(OFFICIAL_DIR, "????-??-??", "_fetch-log.json")))
    if not logs:
        return None
    with open(logs[-1], encoding="utf-8") as f:
        return json.load(f)


def fmt_cut(x):
    """判定線數值顯示：整數就不帶小數。"""
    return f"{x:g}" if x == int(x) else f"{x:.1f}"


def compute_scan(cfg):
    """算供給（戰場內）、需求（絕對證據分級）、象限與交叉，回傳一包資料（給 md/html/snapshot 共用）。

    v2 邏輯（2026-07-25 重建，修正兩個框架級錯誤）：
    1. 供給軸只算「戰場內」（scope_topic 的 regex，預設 iPad）。
       v1 用全庫數 → 「電池續航 674」其實是 iPhone 299 支＋行動電源等 358 支灌出來的假紅海，
       戰場內只有 29 支。全庫數降為參考欄。
    2. 需求軸改「絕對證據分級」（已驗證／有訊號／未驗證），廢除分位數排名。
       v1 的 P50 在 8 個主題上＝強制一半當輸家：全部都有需求也硬分出「低需求」，
       且加種子會把別的主題擠下去（零和、不穩定）。分級是絕對制——
       加新主題、加種子，永遠不影響其他主題的判定。
    3. 第一方證據（cfg.first_party：真實流量／客服）直接判「已驗證」，代理指標讓位。
    """
    corpus_files = list_corpus_txt(cfg["corpus_dir"], cfg["channels"])
    titles = [(ch, ID_RE.sub("", name)) for ch, name in corpus_files]

    topic_re = {t: re.compile(pat, re.IGNORECASE) for t, pat in cfg["topics"].items()}
    scope_topic = cfg.get("scope_topic", "iPad")
    scope_rx = topic_re[scope_topic]
    scope_titles = [title for _, title in titles if scope_rx.search(title)]

    # ── 供給面：全庫數（參考）＋ 戰場內數（象限判定用） ──
    supply = {t: sum(1 for _, title in titles if rx.search(title)) for t, rx in topic_re.items()}
    supply_scoped = {t: sum(1 for title in scope_titles if rx.search(title))
                     for t, rx in topic_re.items() if t != scope_topic}

    # ── 需求面：種子詞擴張（去重）→ 意圖形問句數 → 絕對分級 ──
    sug_date, sug_data = latest_suggest()
    if sug_data is None:
        sys.exit(f"{NG} 找不到 suggest 存檔（{SUGGEST_DIR}），請先跑：python3 scripts/radar.py sync")
    by_query = {}
    for r in sug_data["results"]:
        by_query.setdefault(r["query"], []).append(r)

    rules = cfg.get("demand_rules", {})
    prob_tw = re.compile(rules.get("problem_regex_tw", "嗎|怎麼|如何|為什麼|不能|無法"))
    prob_en = re.compile(rules.get("problem_regex_en", r"\b(not|how|why|fix)\b"), re.IGNORECASE)
    min_prob = rules.get("verified_min_problem", 5)
    min_exp = rules.get("signal_min_expansions", 10)
    first_party = cfg.get("first_party", {})

    demand, problem_hits, expansions, seed_miss = {}, {}, {}, []
    for t, seeds in cfg["topic_seeds"].items():
        uniq = set()
        for s in seeds:
            entries = by_query.get(s)
            if not entries:
                seed_miss.append(f"{t}／{s}")
                continue
            for e in entries:
                if e["status"] == "ok":
                    uniq.update(e["suggestions"])
        expansions[t] = sorted(uniq)
        demand[t] = len(uniq)                                    # 不重複擴張數
        problem_hits[t] = sum(1 for s in uniq
                              if prob_tw.search(s) or prob_en.search(s))

    tier = {}
    for t in cfg["topic_seeds"]:
        if t in first_party or problem_hits[t] >= min_prob:
            tier[t] = "已驗證"
        elif demand[t] >= min_exp:
            tier[t] = "有訊號"
        else:
            tier[t] = "未驗證"

    measured = [t for t in cfg["topic_seeds"] if t != scope_topic]
    unmeasured = [t for t in cfg["topics"] if t not in cfg["topic_seeds"] and t != scope_topic]

    # ── 供給判定線：戰場內供給的分位數（供給軸樣本大、分位數仍適用）＋ 邊界帶 ──
    th = cfg["thresholds"]
    supply_cut = quantile(list(supply_scoped.values()), th["supply_quantile"])
    band = th.get("border_band", 0.10)

    quad, border = {}, {}
    for t in measured:
        hs = supply_scoped[t] >= supply_cut
        hd = tier[t] == "已驗證"
        quad[t] = ("紅海" if hs and hd else
                   "金礦" if (not hs) and hd else
                   "泡沫" if hs else "沙漠")
        border[t] = supply_cut > 0 and abs(supply_scoped[t] - supply_cut) / supply_cut <= band

    return {
        "titles": titles,
        "corpus_count": len(corpus_files),
        "scope_topic": scope_topic, "scope_count": len(scope_titles),
        "supply": supply, "supply_scoped": supply_scoped,
        "demand": demand, "problem_hits": problem_hits, "expansions": expansions,
        "tier": tier, "first_party": first_party,
        "measured": measured, "unmeasured": unmeasured,
        "supply_cut": supply_cut, "border": border,
        "rules": {"min_prob": min_prob, "min_exp": min_exp},
        "quad": quad, "ipad_cross": supply_scoped,
        "sug_date": sug_date, "sug_data": sug_data,
        "seed_miss": seed_miss,
        "official_log": latest_official_log(),
        "topic_re": topic_re,
    }


QUAD_ORDER = ["金礦", "紅海", "泡沫", "沙漠"]
QUAD_DESC = {
    "金礦": "戰場內沒人做 × 需求已驗證——優先寫",
    "紅海": "戰場內擁擠 × 需求已驗證——要有果果獨家證據才進",
    "泡沫": "戰場內擁擠 × 需求未驗證——創作者自嗨，先觀望",
    "沙漠": "戰場內沒人做 × 需求未驗證——先驗證需求再寫（不是永遠不寫）",
}
TIER_MARK = {"已驗證": "✅ 已驗證", "有訊號": "🔎 有訊號", "未驗證": "⬜ 未驗證"}


def error_block_lines(sc):
    """錯誤與資料品質區塊（md 用）：嚴守「查到 0 ≠ 查詢失敗」。"""
    lines = []
    s = sc["sug_data"]["summary"]
    lines.append(f"- Google 自動完成（{sc['sug_date']}）：成功 {s['ok']}／空 {s['empty']}／失敗 {s['error']}。"
                 "「空」是合法結果（該詞沒有擴張），「失敗」是查詢本身出錯，兩者分開計。")
    errs = [r for r in sc["sug_data"]["results"] if r["status"] == "error"]
    for r in errs:
        lines.append(f"  - {NG} {'🇹🇼' if r['region'] == 'tw' else '🇺🇸'} 「{r['query']}」：{r.get('error', '')}")
    ol = sc["official_log"]
    if ol:
        bad = [p for p in ol["pages"] if p["status"] != "ok"]
        lines.append(f"- 官方頁存檔（{ol['date']}）：成功 {len(ol['pages']) - len(bad)}／失敗 {len(bad)}。")
        for p in bad:
            lines.append(f"  - {NG} {p['name']}（{p['url']}）：{p['status']}")
    else:
        lines.append("- 官方頁存檔：找不到抓取紀錄（尚未跑過 sync 的 official 步驟）。")
    if sc["seed_miss"]:
        lines.append(f"- 有 {len(sc['seed_miss'])} 個主題種子在 suggest 存檔中找不到查詢結果："
                     f"{'、'.join(sc['seed_miss'])}（請檢查 radar.json 的 topic_seeds 與 seeds 清單是否對得上）")
    lines.append("- TODO：歷史 13,270 筆的 upload_date 尚未回補 meta.jsonl（13k 次網路呼叫太慢，另擇期批次補）。")
    return lines


def _fp_note(sc, t):
    """第一方證據註記（有列 first_party 的主題附 🏅）。"""
    return f"　🏅 {sc['first_party'][t]}" if t in sc["first_party"] else ""


def write_quadrant_md(cfg, sc, path):
    """輸出 1：00-雙面象限圖.md——給 apple-topic-explorer skill 當 context 用。"""
    th = cfg["thresholds"]
    scope = sc["scope_topic"]
    L = []
    L.append(f"# 選題雷達｜雙面象限圖 v2（{THIS_MONTH}）")
    L.append("")
    L.append(f"- 資料基準日：{TODAY}（語料檔名 {sc['corpus_count']:,} 筆，其中 {scope} 戰場內 "
             f"{sc['scope_count']:,} 筆；Google 自動完成 {sc['sug_date']}，TW＋US）")
    L.append(f"- **供給軸＝{scope} 戰場內檔名命中數**（全庫數只是參考——會被 iPhone 等鄰近內容灌水）；"
             f"高供給線＝戰場內供給 P{int(th['supply_quantile'] * 100)} = **{fmt_cut(sc['supply_cut'])}**"
             f"（±{int(th.get('border_band', 0.1) * 100)}% 內標「邊界」）")
    L.append(f"- **需求軸＝絕對證據分級**（非零和；加種子、加主題不影響其他主題判定）："
             f"✅ 已驗證＝意圖形問句 ≥ {sc['rules']['min_prob']} 條或有第一方證據🏅；"
             f"🔎 有訊號＝不重複擴張 ≥ {sc['rules']['min_exp']}；⬜ 未驗證＝其餘")
    L.append("- 第一方證據（真實流量／客服）> 任何代理指標；雷達的職責是「排雷」，不是「判死」。")
    L.append("")
    L.append("## 象限總表")
    L.append("")
    L.append(f"| 主題 | 供給（{scope} 戰場內） | 全庫參考 | 不重複擴張 | 意圖問句 | 需求分級 | 象限 |")
    L.append("|---|---:|---:|---:|---:|---|---|")
    order = sorted(sc["measured"],
                   key=lambda x: (QUAD_ORDER.index(sc["quad"][x]),
                                  -sc["problem_hits"][x], sc["supply_scoped"][x]))
    for t in order:
        b = "（邊界）" if sc["border"][t] else ""
        fp = " 🏅" if t in sc["first_party"] else ""
        L.append(f"| {t}{fp} | {sc['supply_scoped'][t]:,}{b} | {sc['supply'][t]:,} | "
                 f"{sc['demand'][t]} | {sc['problem_hits'][t]} | {TIER_MARK[sc['tier'][t]]} | {sc['quad'][t]} |")
    L.append("")
    for q in QUAD_ORDER:
        members = [t for t in sc["measured"] if sc["quad"][t] == q]
        L.append(f"### {q}（{QUAD_DESC[q]}）")
        L.append("")
        if members:
            for t in sorted(members, key=lambda x: (-sc["problem_hits"][x], sc["supply_scoped"][x])):
                L.append(f"- **{t}**：戰場內供給 {sc['supply_scoped'][t]:,}（全庫 {sc['supply'][t]:,}）、"
                         f"意圖問句 {sc['problem_hits'][t]}、{TIER_MARK[sc['tier'][t]]}{_fp_note(sc, t)}")
        else:
            L.append("-（本月無主題落在此象限）")
        L.append("")
    L.append("## 需求未測主題（無種子詞，僅供給面，不參與象限判定）")
    L.append("")
    L.append(f"| 主題 | 供給（{scope} 戰場內） | 全庫參考 |")
    L.append("|---|---:|---:|")
    for t in sorted(sc["unmeasured"], key=lambda x: -sc["supply_scoped"].get(x, 0)):
        L.append(f"| {t} | {sc['supply_scoped'].get(t, 0):,} | {sc['supply'][t]:,} |")
    L.append("")
    L.append("## 方法論 v2（為什麼跟 v1 不一樣）")
    L.append("")
    L.append("1. **v1 供給用全庫數** → 「電池續航 674」其實是 iPhone 299＋行動電源等 358 灌出來的，"
             f"{scope} 戰場內只有 29。v2 供給只算戰場內。")
    L.append("2. **v1 需求用 P50 分位數** → 8 個主題強制一半當輸家，加種子會把別人擠下去（零和）。"
             "v2 改絕對分級，判定互不影響、跨月穩定。")
    L.append("3. **第一方證據掛鉤**：`radar.json → first_party` 有列的主題直接「已驗證」＋🏅。")
    L.append("")
    L.append("## 錯誤與資料品質")
    L.append("")
    L.extend(error_block_lines(sc))
    L.append("")
    L.append(f"---\n產生：`scripts/radar.py scan`（{datetime.datetime.now().isoformat(timespec='seconds')}）")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ── HTML 視覺版（設計語言對齊 _planning/topic-engine-optimization.html） ──
HTML_CSS = """
* { box-sizing:border-box; margin:0; padding:0; }
:root {
  --bg:#f6f8fb; --panel:#fff; --panel2:#f0f3f8; --line:#e2e8f0; --grid:#edf1f6;
  --ink:#16223a; --body:#45506a; --muted:#8590a6;
  --navy:#17345f; --navy-deep:#0f2547; --navy-bg:#eef2f8;
  --green:#2f9e57; --green-deep:#237a43; --green-bg:#eaf5ee;
  --red:#c0492f; --red-bg:#fbeae5;
  --teal:#1c8a9a; --teal-bg:#e3f3f4;
  --purple:#7150c9; --purple-bg:#efeafb;
  --gray:#6b7280; --gray-bg:#f0f2f5;
  --mono:'SF Mono','JetBrains Mono','Menlo','Consolas',monospace;
  --sans:'Noto Sans TC',-apple-system,BlinkMacSystemFont,'Segoe UI','Inter',sans-serif;
}
body { background:var(--bg); color:var(--body); font-family:var(--sans); line-height:1.75; -webkit-font-smoothing:antialiased; }
.wrap { max-width:1000px; margin:0 auto; padding:40px 22px 100px; }
.kicker { font-family:var(--mono); font-size:.72rem; letter-spacing:.05em; color:var(--navy); margin-bottom:12px; }
.kicker::before { content:'// '; color:var(--muted); }
h1 { font-weight:800; font-size:2rem; line-height:1.2; letter-spacing:-.02em; color:var(--ink); margin-bottom:12px; }
.lede { font-size:1rem; color:var(--body); max-width:760px; }
.meta-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }
.meta-row span { font-size:.74rem; color:var(--navy); border:1px solid var(--line); background:#fff; padding:5px 12px; border-radius:999px; }
h2.sec { font-size:1.3rem; font-weight:800; color:var(--ink); margin:52px 0 6px; letter-spacing:-.01em; }
h2.sec .mono { font-family:var(--mono); font-size:.7rem; color:var(--muted); font-weight:700; display:block; letter-spacing:.08em; margin-bottom:2px; }
.sec-sub { color:var(--body); font-size:.94rem; margin-bottom:14px; max-width:780px; }
strong { color:var(--ink); font-weight:700; }
code { font-family:var(--mono); font-size:.84em; background:var(--panel2); padding:2px 6px; border-radius:5px; color:var(--navy-deep); }

/* ── 2×2 象限圖 ── */
.quad-frame { margin:22px 0 8px; }
.axis-top { text-align:center; font-size:.8rem; font-weight:700; color:var(--muted); letter-spacing:.12em; margin-bottom:8px; }
.quad-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.qcell { border-radius:14px; padding:18px 18px 16px; border:1px solid var(--line); min-height:190px; box-shadow:0 4px 16px rgba(20,39,68,.05); }
.qcell .qtag { font-family:var(--mono); font-size:.68rem; letter-spacing:.06em; opacity:.85; margin-bottom:2px; }
.qcell h3 { font-size:1.15rem; font-weight:800; margin-bottom:2px; }
.qcell .qdesc { font-size:.78rem; margin-bottom:12px; opacity:.9; }
.qcell.gold { background:var(--green-bg); border-color:#cfe7d8; }
.qcell.gold h3, .qcell.gold .qtag { color:var(--green-deep); }
.qcell.red { background:var(--red-bg); border-color:#eccfc5; }
.qcell.red h3, .qcell.red .qtag { color:var(--red); }
.qcell.bubble { background:var(--purple-bg); border-color:#dcd2f2; }
.qcell.bubble h3, .qcell.bubble .qtag { color:var(--purple); }
.qcell.desert { background:var(--gray-bg); border-color:var(--line); }
.qcell.desert h3, .qcell.desert .qtag { color:var(--gray); }
.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chip { background:#fff; border:1px solid var(--line); border-radius:10px; padding:7px 11px; font-size:.86rem; color:var(--ink); font-weight:700; line-height:1.4; box-shadow:0 1px 4px rgba(20,39,68,.05); }
.chip small { display:block; font-family:var(--mono); font-size:.68rem; font-weight:400; color:var(--muted); }
.chip-none { font-size:.82rem; color:var(--muted); }
.axis-bottom { display:flex; justify-content:space-between; font-size:.78rem; font-weight:700; color:var(--muted); letter-spacing:.1em; margin-top:8px; }
.unmeasured { margin-top:14px; background:var(--panel); border:1px dashed var(--line); border-radius:12px; padding:12px 16px; font-size:.84rem; color:var(--muted); }
.unmeasured b { color:var(--body); }

/* ── 表格 ── */
.tbl-scroll { overflow-x:auto; margin:16px 0; }
table { width:100%; border-collapse:collapse; font-size:.88rem; background:#fff; border:1px solid var(--line); border-radius:12px; overflow:hidden; }
.tbl-scroll table { min-width:520px; }
thead th { background:var(--navy-bg); color:var(--navy-deep); font-weight:700; text-align:left; padding:11px 14px; font-size:.82rem; border-bottom:1px solid var(--line); }
tbody td { padding:10px 14px; border-bottom:1px solid var(--grid); vertical-align:top; }
tbody tr:last-child td { border-bottom:none; }
tbody tr:nth-child(even) { background:#fafbfd; }
td.num, th.num { font-family:var(--mono); text-align:right; white-space:nowrap; }
.bar { display:inline-block; height:8px; border-radius:4px; background:var(--teal); vertical-align:middle; margin-right:8px; }

/* ── 說明卡與錯誤卡 ── */
.card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:20px 22px; margin:16px 0; box-shadow:0 4px 16px rgba(20,39,68,.05); }
.card.rule { border-left:5px solid var(--navy); }
.card.err-none { border-left:5px solid var(--green); }
.card.err-some { border-left:5px solid var(--red); }
.card h3 { font-size:1rem; color:var(--ink); font-weight:800; margin-bottom:8px; }
.card ul { margin:6px 0 0 20px; font-size:.9rem; }
.card li { margin:4px 0; }
footer { margin-top:56px; font-size:.78rem; color:var(--muted); border-top:1px solid var(--line); padding-top:16px; font-family:var(--mono); }

@media (max-width:640px) {
  .wrap { padding:28px 14px 80px; }
  h1 { font-size:1.5rem; }
  .quad-grid { grid-template-columns:1fr; }
  .qcell { min-height:0; }
  .axis-top, .axis-bottom { display:none; }  /* 手機改直排，軸標籤交給各格自己的「低供給×高需求」小字 */
}
"""


def chips_html(sc, members, sort_key):
    """象限格子裡的主題小卡（v2：戰場內供給＋意圖問句＋分級徽章）。"""
    if not members:
        return '<span class="chip-none">（本月無主題落在此象限）</span>'
    out = []
    for t in sorted(members, key=sort_key):
        fp = " 🏅" if t in sc["first_party"] else ""
        b = "（邊界）" if sc["border"][t] else ""
        out.append(f'<span class="chip">{html.escape(t)}{fp}'
                   f'<small>戰場供 {sc["supply_scoped"][t]:,}{b}｜問句 {sc["problem_hits"][t]}'
                   f'｜{TIER_MARK[sc["tier"][t]]}</small></span>')
    return "".join(out)


def write_quadrant_html(cfg, sc, path):
    """輸出 2：00-雙面象限圖.html——給人看的視覺版（自包含單檔、RWD、無 JS）。"""
    th = cfg["thresholds"]
    scope = sc["scope_topic"]
    q_members = {q: [t for t in sc["measured"] if sc["quad"][t] == q] for q in QUAD_ORDER}
    by_prob = lambda t: (-sc["problem_hits"][t], sc["supply_scoped"][t])
    by_supply = lambda t: -sc["supply_scoped"][t]

    # iPad 交叉表（附比例長條，讓相對量一眼可讀）
    cross_max = max(sc["ipad_cross"].values() or [1])
    cross_rows = []
    for t, n in sorted(sc["ipad_cross"].items(), key=lambda kv: -kv[1]):
        w = max(4, round(n / cross_max * 140)) if n else 0
        bar = f'<span class="bar" style="width:{w}px"></span>' if n else ""
        cross_rows.append(f"<tr><td>{html.escape(t)}</td>"
                          f'<td class="num">{bar}{n:,}</td></tr>')

    # 錯誤區塊
    s = sc["sug_data"]["summary"]
    err_items = []
    for r in sc["sug_data"]["results"]:
        if r["status"] == "error":
            err_items.append(f"{'🇹🇼' if r['region'] == 'tw' else '🇺🇸'} 「{html.escape(r['query'])}」："
                             f"{html.escape(r.get('error', ''))}")
    ol = sc["official_log"]
    off_line = "官方頁存檔：找不到抓取紀錄（尚未跑過 sync official）。"
    if ol:
        bad = [p for p in ol["pages"] if p["status"] != "ok"]
        off_line = f"官方頁存檔（{ol['date']}）：成功 {len(ol['pages']) - len(bad)}／失敗 {len(bad)}。"
        for p in bad:
            err_items.append(f"官方頁 {html.escape(p['name'])}：{html.escape(p['status'])}")
    for miss in sc["seed_miss"]:
        err_items.append(f"種子詞未查到結果：{html.escape(miss)}（檢查 radar.json 的 topic_seeds／seeds）")
    err_cls = "err-some" if err_items else "err-none"
    err_html = ("<ul>" + "".join(f"<li>{it}</li>" for it in err_items) + "</ul>") if err_items \
        else "<p style='font-size:.9rem'>本次收集無失敗項目。</p>"

    unmeasured_txt = " ｜ ".join(
        f"<b>{html.escape(t)}</b> 戰場供 {sc['supply_scoped'].get(t, 0):,}（全庫 {sc['supply'][t]:,}）"
        for t in sorted(sc["unmeasured"], key=lambda x: -sc["supply_scoped"].get(x, 0)))

    body = f"""<div class="wrap">
  <div class="kicker">guoguo topic radar · v2</div>
  <h1>選題雷達｜雙面象限圖</h1>
  <p class="lede">供給軸＝<strong>{html.escape(scope)} 戰場內</strong>的檔名命中數（{sc['scope_count']:,} 檔；全庫數只是參考，會被 iPhone 等鄰近內容灌水）；
  需求軸＝<strong>絕對證據分級</strong>（✅已驗證／🔎有訊號／⬜未驗證，非零和——加種子不會把別的主題擠下去）。
  <strong>金礦＝戰場內沒人做 × 需求已驗證</strong>。第一方證據（🏅 真實流量／客服）永遠壓過代理指標。</p>
  <div class="meta-row">
    <span>資料基準日 {TODAY}</span>
    <span>語料 {sc['corpus_count']:,} 檔（{html.escape(scope)} 戰場 {sc['scope_count']:,}）</span>
    <span>自動完成 {sc['sug_date']}</span>
    <span>高供給線（戰場內）P{int(th['supply_quantile'] * 100)} = {fmt_cut(sc['supply_cut'])}</span>
    <span>✅線＝意圖問句 ≥ {sc['rules']['min_prob']}</span>
  </div>

  <h2 class="sec"><span class="mono">01 / QUADRANT</span>雙面象限圖</h2>
  <p class="sec-sub">縱向：上排＝需求已驗證、下排＝尚未驗證；橫向：左欄＝戰場內低供給、右欄＝高供給。
  只納入「有種子詞、需求有實測」的主題；卡片上的「問句」＝意圖形問句條數（怎麼／嗎／不能／not／how…）。</p>
  <div class="quad-frame">
    <div class="axis-top">▲ 需求已驗證（搜尋端有真人在問）</div>
    <div class="quad-grid">
      <div class="qcell gold">
        <div class="qtag">戰場內低供給 × 已驗證</div>
        <h3>金礦</h3><div class="qdesc">{QUAD_DESC['金礦']}</div>
        <div class="chips">{chips_html(sc, q_members['金礦'], by_prob)}</div>
      </div>
      <div class="qcell red">
        <div class="qtag">戰場內高供給 × 已驗證</div>
        <h3>紅海</h3><div class="qdesc">{QUAD_DESC['紅海']}</div>
        <div class="chips">{chips_html(sc, q_members['紅海'], by_supply)}</div>
      </div>
      <div class="qcell desert">
        <div class="qtag">戰場內低供給 × 未驗證</div>
        <h3>沙漠</h3><div class="qdesc">{QUAD_DESC['沙漠']}</div>
        <div class="chips">{chips_html(sc, q_members['沙漠'], by_supply)}</div>
      </div>
      <div class="qcell bubble">
        <div class="qtag">戰場內高供給 × 未驗證</div>
        <h3>泡沫</h3><div class="qdesc">{QUAD_DESC['泡沫']}</div>
        <div class="chips">{chips_html(sc, q_members['泡沫'], by_supply)}</div>
      </div>
    </div>
    <div class="axis-bottom"><span>◀ 戰場內低供給（沒人做）</span><span>戰場內高供給（擁擠）▶</span></div>
    <div class="unmeasured">需求未測（無種子詞，僅供給面、不參與象限）：{unmeasured_txt}</div>
  </div>

  <h2 class="sec"><span class="mono">02 / SUPPLY DETAIL</span>{html.escape(scope)} 戰場內供給明細</h2>
  <p class="sec-sub">這一欄就是象限用的供給軸：檔名<strong>同時</strong>命中「{html.escape(scope)}」與該主題的數量。
  跟全庫數落差越大，代表該主題的全庫聲量被其他產品線灌得越兇。</p>
  <div class="tbl-scroll"><table>
    <thead><tr><th>主題</th><th class="num">戰場內檔數</th></tr></thead>
    <tbody>{''.join(cross_rows)}</tbody>
  </table></div>

  <h2 class="sec"><span class="mono">03 / RULES</span>v2 判定規則（為什麼跟 v1 不一樣）</h2>
  <div class="card rule">
    <h3>兩個 v1 框架錯誤的修正</h3>
    <ul>
      <li><strong>供給軸限定戰場</strong>：v1 用全庫數 → 「電池續航 674」其實是 iPhone 299＋行動電源等 358 灌的，
      {html.escape(scope)} 戰場內只有 29。v2 只算戰場內；高供給線＝戰場內供給 P{int(th['supply_quantile'] * 100)}
      = <strong>{fmt_cut(sc['supply_cut'])}</strong>（差距 ±{int(th.get('border_band', 0.1) * 100)}% 標「邊界」）</li>
      <li><strong>需求軸絕對分級、廢除分位數</strong>：v1 的 P50 在 8 個主題上＝強制一半當輸家（零和），
      加種子會把別人擠下去。v2 分級互不影響：<strong>✅已驗證</strong>＝意圖形問句 ≥ {sc['rules']['min_prob']} 條
      <em>或</em>有第一方證據🏅；<strong>🔎有訊號</strong>＝不重複擴張 ≥ {sc['rules']['min_exp']}；<strong>⬜未驗證</strong>＝其餘</li>
      <li><strong>第一方證據掛鉤</strong>：<code>radar.json → first_party</code>（真實流量／客服）直接判已驗證——
      代理指標與第一方衝突時，第一方贏</li>
      <li>參數都在 <code>scripts/radar.json</code>（thresholds／demand_rules／first_party），可調</li>
    </ul>
  </div>

  <h2 class="sec"><span class="mono">04 / DATA QUALITY</span>資料基準與錯誤彙報</h2>
  <div class="card {err_cls}">
    <h3>自動完成：成功 {s['ok']}／空 {s['empty']}／失敗 {s['error']}（「空」是合法結果，與「失敗」分開計）；{off_line}</h3>
    {err_html}
  </div>

  <footer>scripts/radar.py scan ｜ 產生於 {datetime.datetime.now().isoformat(timespec='seconds')} ｜ 語料：research/3c/youtube（僅檔名，不精讀內文）</footer>
</div>"""

    doc = ("<!DOCTYPE html>\n<html lang=\"zh-TW\">\n<head>\n<meta charset=\"UTF-8\" />\n"
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
           f"<title>選題雷達｜雙面象限圖 {THIS_MONTH}</title>\n<style>{HTML_CSS}</style>\n</head>\n"
           f"<body>\n{body}\n</body>\n</html>\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def write_questions_md(cfg, sc, path):
    """輸出 3：01-問句庫.md——語料疑問句標題（按產品分群）＋兩區自動完成擴張。"""
    L = [f"# 選題雷達｜問句庫（{THIS_MONTH}）", ""]
    L.append(f"- 來源標記：語料＝11 頻道影片標題（{TODAY} 掃描）；🇹🇼／🇺🇸＝Google 自動完成（{sc['sug_date']}）")
    L.append(f"- 語料疑問詞：`{QUESTION_RE.pattern}`")
    L.append("")

    # ── 語料問句：按產品分群（一個標題只歸入第一個命中的產品群） ──
    groups = {p: [] for p in PRODUCT_ORDER}
    groups["其他"] = []
    seen = set()
    for ch, title in sc["titles"]:
        if not QUESTION_RE.search(title) or title in seen:
            continue
        seen.add(title)
        for p in PRODUCT_ORDER:
            if sc["topic_re"][p].search(title):
                groups[p].append((title, ch))
                break
        else:
            groups["其他"].append((title, ch))
    total_q = sum(len(v) for v in groups.values())
    L.append(f"## 一、語料問句標題（共 {total_q:,} 條，去重後）")
    L.append("")
    for p in PRODUCT_ORDER + ["其他"]:
        rows = groups[p]
        L.append(f"### {p}（{len(rows):,} 條）〔來源：語料〕")
        L.append("")
        for title, ch in sorted(rows):
            L.append(f"- {title} （{ch}）")
        L.append("")

    # ── 自動完成擴張：兩區分列（空與失敗都如實標示，不混為一談） ──
    for region, flag, label in (("tw", "🇹🇼", "台灣區"), ("us", "🇺🇸", "美國區")):
        rows = [r for r in sc["sug_data"]["results"] if r["region"] == region]
        n_ok = sum(1 for r in rows if r["status"] == "ok")
        L.append(f"## {'二' if region == 'tw' else '三'}、{flag} {label}自動完成（{n_ok}/{len(rows)} 個種子有擴張）")
        L.append("")
        for r in rows:
            if r["status"] == "ok":
                L.append(f"### {flag} {r['query']}")
                L.append("")
                L.extend(f"- {s}" for s in r["suggestions"])
            elif r["status"] == "empty":
                L.append(f"### {flag} {r['query']} （查到 0 條——合法結果，非錯誤）")
            else:
                L.append(f"### {flag} {r['query']} （{NG} 查詢失敗：{r.get('error', '')}——是失敗、不是空）")
            L.append("")
    L.append(f"---\n產生：`scripts/radar.py scan`（{datetime.datetime.now().isoformat(timespec='seconds')}）")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def write_snapshot(cfg, sc, path):
    """輸出 4：snapshots/YYYY-MM.json——機器讀的完整快照，下月 report 靠它算差分。"""
    sugg_by_region = {"tw": {}, "us": {}}
    for r in sc["sug_data"]["results"]:
        sugg_by_region[r["region"]][r["query"]] = {
            "status": r["status"], "suggestions": r["suggestions"],
            **({"error": r["error"]} if "error" in r else {}),
        }
    snap = {
        "schema": 2,
        "month": THIS_MONTH,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "data_date": TODAY,
        "suggest_date": sc["sug_date"],
        "corpus_count": sc["corpus_count"],
        "scope_topic": sc["scope_topic"], "scope_count": sc["scope_count"],
        "cuts": {"supply_scoped": sc["supply_cut"]},
        "demand_rules": sc["rules"],
        "topics": {t: {"supply": sc["supply"][t],
                       "supply_scoped": sc["supply_scoped"].get(t),
                       "demand": sc["demand"].get(t),
                       "problem_hits": sc["problem_hits"].get(t),
                       "tier": sc["tier"].get(t),
                       "first_party": sc["first_party"].get(t),
                       "quadrant": sc["quad"].get(t),
                       "border": sc["border"].get(t),
                       "demand_measured": t in cfg["topic_seeds"],
                       "seeds": cfg["topic_seeds"].get(t, [])}
                   for t in cfg["topics"]},
        "ipad_cross": sc["ipad_cross"],
        "suggest": sugg_by_region,
        "config_echo": {k: cfg[k] for k in
                        ("topics", "topic_seeds", "seeds_tw", "seeds_us", "thresholds")
                        if k in cfg} | {"scope_topic": sc["scope_topic"],
                                        "demand_rules": cfg.get("demand_rules", {}),
                                        "first_party": sc["first_party"]},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)


def cmd_scan(args):
    """scan 主流程：算象限 → 產 4 個輸出檔。"""
    log = Log()
    cfg = load_config()
    print("【scan】讀語料檔名＋最新 suggest 資料，算雙面象限")
    sc = compute_scan(cfg)
    log.info(f"語料 {sc['corpus_count']:,} 檔（{sc['scope_topic']} 戰場 {sc['scope_count']:,}）；"
             f"自動完成基準 {sc['sug_date']}；高供給線（戰場內）{fmt_cut(sc['supply_cut'])}；"
             f"✅線＝意圖問句 ≥ {sc['rules']['min_prob']}")
    for q in QUAD_ORDER:
        members = [f"{t}{'🏅' if t in sc['first_party'] else ''}"
                   for t in sc["measured"] if sc["quad"][t] == q]
        log.info(f"{q}：{'、'.join(members) if members else '（無）'}")
    if sc["seed_miss"]:
        log.warn(f"{len(sc['seed_miss'])} 個主題種子在 suggest 存檔查不到（見輸出的錯誤區塊）")

    os.makedirs(RADAR_DIR, exist_ok=True)
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    outs = [
        (os.path.join(RADAR_DIR, "00-雙面象限圖.md"), write_quadrant_md),
        (os.path.join(RADAR_DIR, "00-雙面象限圖.html"), write_quadrant_html),
        (os.path.join(RADAR_DIR, "01-問句庫.md"), write_questions_md),
        (os.path.join(SNAPSHOT_DIR, f"{THIS_MONTH}.json"), write_snapshot),
    ]
    for path, fn in outs:
        fn(cfg, sc, path)
        log.ok(f"寫出 {os.path.relpath(path, ROOT)}")
    sys.exit(log.finish("scan"))


# ═════════════════════════════════════════════════════════════
# report — 比對最近兩張月快照，產變化報告
# ═════════════════════════════════════════════════════════════
def cmd_report(args):
    """report 主流程：新出現的建議詞、象限移動、供給數變化。"""
    log = Log()
    files = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "????-??.json")))
    print("【report】比對月快照")
    if len(files) < 2:
        if len(files) == 1:
            print(f"  · 首月只有一張快照（{os.path.basename(files[0])}），變化報告下月起可用")
        else:
            print("  · 還沒有任何快照，請先跑：python3 scripts/radar.py scan")
        sys.exit(0)

    with open(files[-2], encoding="utf-8") as f:
        prev = json.load(f)
    with open(files[-1], encoding="utf-8") as f:
        cur = json.load(f)
    p_m, c_m = prev["month"], cur["month"]
    log.info(f"比較 {p_m} → {c_m}")

    L = [f"# 選題雷達｜變化報告（{p_m} → {c_m}）", ""]

    # ── 象限移動 ──
    L.append("## 象限移動")
    L.append("")
    moved = []
    for t, info in cur["topics"].items():
        old = prev["topics"].get(t, {}).get("quadrant")
        new = info.get("quadrant")
        if old and new and old != new:
            moved.append(f"- **{t}**：{old} → {new}")
    L.extend(moved or ["-（本月無主題換象限）"])
    L.append("")

    # ── 供給數變化（優先看戰場內；舊快照無此欄則退回全庫數） ──
    key = "supply_scoped" if any(v.get("supply_scoped") is not None
                                 for v in cur["topics"].values()) else "supply"
    L.append(f"## 供給數變化（{'戰場內' if key == 'supply_scoped' else '全庫'}檔名命中）")
    L.append("")
    L.append("| 主題 | 上月 | 本月 | 變化 |")
    L.append("|---|---:|---:|---:|")
    for t, info in cur["topics"].items():
        new = info.get(key) if info.get(key) is not None else info.get("supply")
        if new is None:
            continue
        old = prev["topics"].get(t, {}).get(key)
        if old is None:
            old = prev["topics"].get(t, {}).get("supply")
        if old is None:
            L.append(f"| {t} | （新主題） | {new:,} | — |")
        else:
            L.append(f"| {t} | {old:,} | {new:,} | {new - old:+,} |")
    L.append("")

    # ── 需求分級變化（v2 快照才有） ──
    tiers_cur = {t: v.get("tier") for t, v in cur["topics"].items() if v.get("tier")}
    if tiers_cur:
        L.append("## 需求分級變化")
        L.append("")
        tmoved = []
        for t, new_tier in tiers_cur.items():
            old_tier = prev["topics"].get(t, {}).get("tier")
            if old_tier and old_tier != new_tier:
                tmoved.append(f"- **{t}**：{old_tier} → {new_tier}")
        L.extend(tmoved or ["-（本月無主題變更需求分級）"])
        L.append("")

    # ── 新出現的建議詞 ──
    L.append("## 新出現的自動完成建議詞")
    L.append("")
    any_new = False
    for region, flag in (("tw", "🇹🇼"), ("us", "🇺🇸")):
        for seed, info in cur.get("suggest", {}).get(region, {}).items():
            old_set = set(prev.get("suggest", {}).get(region, {}).get(seed, {}).get("suggestions", []))
            fresh = [s for s in info.get("suggestions", []) if s not in old_set]
            if fresh:
                any_new = True
                L.append(f"### {flag} {seed}")
                L.append("")
                L.extend(f"- {s}" for s in fresh)
                L.append("")
    if not any_new:
        L.append("-（本月無新出現的建議詞）")
        L.append("")

    L.append(f"---\n產生：`scripts/radar.py report`（{datetime.datetime.now().isoformat(timespec='seconds')}）")
    out = os.path.join(RADAR_DIR, f"02-變化報告-{c_m}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    log.ok(f"寫出 {os.path.relpath(out, ROOT)}（象限移動 {len(moved)} 件）")
    sys.exit(log.finish("report"))


# ═════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════
USAGE = f"""選題雷達 radar.py — 供給面（YouTube 語料）× 需求面（Google 自動完成）

用法：python3 scripts/radar.py <子命令> [選項]

子命令：
  sync    三路收集（字幕增量／自動完成／官方頁存檔），只寫檔案、不做判斷
          例：python3 scripts/radar.py sync
          例：python3 scripts/radar.py sync --steps videos --only 3ctim --playlist-end 3
  scan    讀語料檔名＋最新 suggest 資料，算雙面象限，產出 4 個檔案到 context/radar/
          例：python3 scripts/radar.py scan
  report  比對最近兩張月快照產變化報告（首月會提示「下月起可用」）
          例：python3 scripts/radar.py report

sync 選項：
  --steps a,b,…      只跑指定步驟（bootstrap／channels／videos／suggest／official，預設全跑）
  --only 頻道名      videos 步驟只跑單一頻道（煙霧測試用）
  --playlist-end N   videos 步驟每頻道檢查最新 N 支（預設 30）
"""


def main():
    if len(sys.argv) == 1:
        print(USAGE)
        sys.exit(0)
    parser = argparse.ArgumentParser(prog="radar.py", add_help=True,
                                     description="選題雷達：供給×需求雙面掃描")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sync = sub.add_parser("sync", help="三路收集，只寫檔案、不做判斷")
    p_sync.add_argument("--steps", default="bootstrap,channels,videos,suggest,official",
                        help="要跑的步驟（逗號分隔，預設全跑）")
    p_sync.add_argument("--only", default=None, help="videos 步驟只跑這個頻道（煙霧測試用）")
    p_sync.add_argument("--playlist-end", type=int, default=30,
                        help="videos 步驟每頻道檢查最新 N 支（預設 30）")
    p_sync.set_defaults(fn=cmd_sync)

    p_scan = sub.add_parser("scan", help="算雙面象限，產出 4 個檔案")
    p_scan.set_defaults(fn=cmd_scan)

    p_report = sub.add_parser("report", help="比對兩張月快照產變化報告")
    p_report.set_defaults(fn=cmd_report)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
