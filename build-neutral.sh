#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 無導外版建置：產生「零導外」的 dist/ 給中性網域（蝦皮買家用）
# 用於 Cloudflare Pages —— Build command: bash build-neutral.sh ／ Output dir: dist
#
# 原理：導外資訊（回賣場/LINE/電話…）只在導外版由 Worker 注入，原始檔天生乾淨；
#       這裡再用 allowlist 只挑乾淨檔、加 noindex、並用洩漏檢查當最後守門。
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

OUT=dist
rm -rf "$OUT"; mkdir -p "$OUT"

# 0) 首頁即時重印：用「當下 commit 的 articles.json」現場重生 index.neutral.html
#    → 中性版首頁永遠與 articles.json 同步，因此 index.neutral.html 不再 commit（見 .gitignore）。
#    build-homepage.py 也會順手覆寫導外版 index.html，但那份靠 GitHub Pages 直吐 commit、
#    不走這支腳本；在 Cloudflare 臨時建置機器上覆寫它無害，也不會被 commit 回去。
python3 build-homepage.py

# 0b) 靜態標籤頁即時重生：用「當下 commit 的 articles.json」現場產生 tag/<slug>/index.html。
#     標籤頁是「一份檔雙版共用」（靠相對連結），原始檔天生零導外；下方會一起複製進 dist、
#     並由洩漏檢查守門。必須在複製前先產出，否則 dist/tag/ 會是空的。
python3 build-tags.py

# 1) allowlist：只複製「乾淨內容」——絕不含 worker/(有全部聯絡資料)、sitemap.xml(有 guoguo 網址)、內部文件
#    導外版首頁 index.html（含常駐商品側欄、CTA 連 www.guoguo.tw/shop）不進來；
#    改放 build-homepage.py 另產的「中性版」index.neutral.html（無側欄、無任何 guoguo 連結、頁尾不涉聯繫，
#    僅保留 logo 與教學總覽）→ 搬成中性網域的 dist/index.html。products.json 一樣不進來（中性版不 fetch）。
#    文章資料夾清單直接從 articles.json 的 slug 讀出（＝資料夾名），不再手動維護：
#    新增文章只要進 articles.json（並重跑 build-homepage.py），這裡與麵包屑注入都會自動跟上。
ARTICLE_SLUGS=$(python3 -c "import json;print(' '.join(a['slug'] for a in json.load(open('articles.json'))))")

cp -R assets "$OUT"/
rm -rf "$OUT"/assets/og   # 中性版一律 emoji 卡、不引用首圖；連圖檔都不上（圖內可能有 guide.guoguo.tw 字樣）
for d in $ARTICLE_SLUGS; do
  if [ -d "$d" ]; then
    cp -R "$d" "$OUT"/
  else
    echo "❌ articles.json 列了 slug「$d」，卻找不到對應資料夾 → 中止（首頁會連到 404，請先建好資料夾）。"
    exit 1
  fi
done
cp index.neutral.html "$OUT"/index.html   # 中性版首頁（step 0 剛重印的乾淨版；下方洩漏檢查會再守門一次）

# 靜態標籤頁：step 0b 剛產出的 tag/（一份檔雙版共用、相對連結、零導外）整包搬進中性網域。
# 不需注入麵包屑（它自帶相對麵包屑）；下方洩漏檢查會一併掃它。
if [ -d tag ]; then
  cp -R tag "$OUT"/
else
  echo "❌ 找不到 tag/ 資料夾（build-tags.py 應已在 step 0b 產出）→ 中止。"
  exit 1
fi

# 2) 中性版麵包屑：導外版由 Worker 注入「果果賣場 › iPad 使用教學 › 本篇教學」；
#    中性版不經 Worker，改在此把「iPad 使用教學 › 本篇教學」注入到 dist/ 的文章頁
#    （拿掉會導外的「果果賣場」；「iPad 使用教學」連回中性版首頁 "/"）。原始檔不動 → 導外版不受影響。
python3 - "$OUT" <<'PY'
import os, re, sys, glob, json, html
from urllib.parse import quote

OUT = sys.argv[1]
# 文章清單同樣從 articles.json 讀（＝每篇 slug／tags），與上面 cp 迴圈同一個真實來源。
ARTS = json.load(open("articles.json", encoding="utf-8"))
BY_SLUG = {a["slug"]: a for a in ARTS}
DIRS = [a["slug"] for a in ARTS]

# 麵包屑樣式（沿用導外版 .gg-crumb；補 --sans fallback，脫離 Worker 環境也能對）
CRUMB_CSS = "<style>" + (
    ".gg-crumb{position:sticky;top:0;z-index:50;display:flex;align-items:center;flex-wrap:wrap;"
    "gap:5px 7px;font-family:var(--sans,-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans TC',sans-serif);"
    "font-size:.94rem;color:var(--muted,#8590a6);padding:11px 0 12px;margin:0;"
    "border-bottom:1px solid var(--line,#e2e8f0);background:var(--bg,#f6f8fb)}"
    ".gg-crumb a.gg-cr{display:inline-flex;align-items:center;gap:7px;color:var(--navy,#17345f);"
    "text-decoration:none;font-weight:700;padding:8px 16px;border:1px solid #cfdaec;border-radius:999px;"
    "background:#fff;box-shadow:0 1px 2px rgba(20,39,68,.05);transition:.14s;cursor:pointer}"
    ".gg-crumb a.gg-cr:hover{border-color:var(--navy,#17345f);background:#f2f7fd;"
    "box-shadow:0 4px 12px rgba(20,39,68,.13);transform:translateY(-1px)}"
    ".gg-crumb a.gg-cr:active{transform:translateY(0)}"
    ".gg-crumb a.gg-cr svg{width:18px;height:18px;flex:none;stroke:currentColor;stroke-width:2;"
    "fill:none;stroke-linecap:round;stroke-linejoin:round}"
    ".gg-crumb .gg-sep{color:#b8c3d4;font-size:1.05rem;line-height:1;margin:0 1px}"
    ".gg-crumb .gg-cur{color:var(--body,#45506a);font-weight:700;padding:0 6px;font-size:.94rem}"
) + "</style>"

# 頁尾「相關主題」標籤樣式（沿用導外版 .gg-tags；補 var fallback，脫離 Worker 也能對）
TAGS_CSS = "<style>" + (
    "nav.gg-tags{display:block!important;width:auto!important;min-width:0!important;position:static!important;"
    "height:auto!important;overflow:visible;margin:52px 0 0;padding:22px 26px;"
    "background:linear-gradient(180deg,#ffffff,#f4f8fd);"
    "border:1px solid #e4ebf4;border-top:3px solid var(--teal,#1c8a9a);border-radius:18px;"
    "font-family:var(--sans,-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans TC',sans-serif);"
    "box-shadow:0 8px 30px rgba(20,39,68,.05)}"
    "nav.gg-tags .gg-tags-h{font-size:.98rem;font-weight:800;color:var(--ink,#16223a);margin:0 0 14px}"
    "nav.gg-tags .gg-tags-list{display:flex!important;flex-direction:row!important;flex-wrap:wrap!important;"
    "align-items:center;gap:9px}"
    "nav.gg-tags a.gg-tag{display:inline-flex!important;width:auto!important;align-items:center;"
    "text-decoration:none;font-size:.9rem;"
    "font-weight:700;color:var(--navy,#17345f);background:#fff;border:1px solid #cfdaec;"
    "border-radius:999px;padding:8px 16px;transition:.14s}"
    "nav.gg-tags a.gg-tag::before{content:'#';color:var(--teal,#1c8a9a);margin-right:5px;font-weight:800}"
    "nav.gg-tags a.gg-tag:hover{border-color:var(--navy,#17345f);background:#f2f7fd;transform:translateY(-1px);"
    "box-shadow:0 4px 12px rgba(20,39,68,.13)}"
    "@media(max-width:520px){nav.gg-tags{padding:18px 16px}nav.gg-tags .gg-tags-list{gap:8px}"
    "nav.gg-tags a.gg-tag{padding:7px 13px;font-size:.86rem}}"
) + "</style>"

# 麵包屑本體：iPad 使用教學（連回中性版首頁 /）› 本篇教學。無「果果賣場」、無任何聯絡/導購連結。
CRUMB_HTML = (
    # data-pagefind-ignore：麵包屑在 <main> 內、會被 Pagefind 掃到，標記排除 → 搜尋片段只留文章內文。
    '<div class="gg-crumb" data-pagefind-ignore aria-label="麵包屑導覽">'
    '<a class="gg-cr" href="/" aria-label="回 iPad 使用教學總覽首頁">'
    '<svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
    '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>iPad 使用教學</a>'
    '<span class="gg-sep" aria-hidden="true">›</span>'
    '<span class="gg-cur">本篇教學</span>'
    '</div>'
)

def tag_slug(t):
    # 與 build-tags.py / worker 的 tag_slug 同規則：strip → 小寫 ASCII → 空白換 '-' → 中日文保留
    return re.sub(r"\s+", "-", t.strip().lower())

def tags_html(slug):
    a = BY_SLUG.get(slug) or {}
    tags = [t for t in (a.get("tags") or []) if t]
    if not tags:
        return ""
    # 連到「靜態標籤頁」（相對 ../tag/<slug>/）：文章在中性版 /<art>/ → /tag/<slug>/。
    # 用相對路徑，同一份注入邏輯在導外（Worker）與中性都對。
    chips = "".join(
        '<a class="gg-tag" href="../tag/{q}/">{t}</a>'.format(q=quote(tag_slug(t)), t=html.escape(t))
        for t in tags
    )
    return ('<nav class="gg-tags" data-pagefind-ignore aria-label="相關主題標籤">'
            '<div class="gg-tags-h">想看更多同主題的教學？點標籤逛逛 👇</div>'
            '<div class="gg-tags-list">' + chips + '</div></nav>')

n = 0
for d in DIRS:
    th = tags_html(d)
    for f in glob.glob(os.path.join(OUT, d, "**", "*.html"), recursive=True):
        with open(f, encoding="utf-8") as fh:
            s = fh.read()
        if "gg-crumb" in s:                      # 已注入過 → 冪等跳過
            continue
        if not re.search(r"<main\b", s):         # 沒有 <main> 的頁面不硬塞
            continue
        # 把麵包屑塞進 <main> 開頭，並替 <main> 標記 data-pagefind-body：
        #   → Pagefind 只索引 <main>（文章內文），排除上方 masthead／logo／信賴條等 chrome，
        #     命中片段才乾淨（不會出現「果果國際 GUOGUO…」這類頁首雜訊）。
        #   → 只要全站有任一頁帶 data-pagefind-body，沒帶的頁（首頁／標籤頁）就完全不進索引，
        #     與它們的 data-pagefind-ignore 雙保險。
        def _open_main(m):
            tag = m.group(1)
            if "data-pagefind-body" not in tag:
                tag = tag[:-1] + " data-pagefind-body>"
            return tag + CRUMB_HTML
        s = re.sub(r"(<main\b[^>]*>)", _open_main, s, count=1)
        # 文章自帶的 masthead（<header class="masthead">：logo／品牌／標語，在 <main> 內、<h1> 之前）
        # 也標 data-pagefind-ignore，否則會被當成內文開頭 → 命中片段出現「果果國際 GUOGUO…台灣最專業…」頁首雜訊。
        s = re.sub(
            r'(<header\b[^>]*class="masthead"[^>]*>)',
            lambda m: m.group(1) if "data-pagefind-ignore" in m.group(1)
                      else m.group(1)[:-1] + " data-pagefind-ignore>",
            s, count=1,
        )
        # 頁尾「相關主題」標籤：插在 <main> 內容最後（最後一個 </main> 之前）
        if th:
            idx = s.rfind("</main>")
            if idx != -1:
                s = s[:idx] + th + s[idx:]
        if "</head>" in s:
            s = s.replace("</head>", CRUMB_CSS + TAGS_CSS + "</head>", 1)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(s)
        n += 1

print("  ↳ 已為 {} 個文章頁注入中性版麵包屑（→ /）＋頁尾相關主題標籤".format(n))
PY

# 3) noindex 整個中性網域（與導外版 www.guoguo.tw/guide 同內容，避免 Google 重複內容懲罰）
printf 'User-agent: *\nDisallow: /\n' > "$OUT"/robots.txt

# 3b) Pagefind 全文搜尋索引：對「已組好的乾淨 dist/」建索引 → 產出 dist/pagefind/。
#     ▸ 只掃 dist（不掃 repo 根）＝天生避開 _planning 等內部規劃文件，不會被索引進公開站。
#     ▸ 首頁 index.html 與 tag/*/ 都帶 data-pagefind-ignore（不進索引）；上面注入的麵包屑/相關標籤
#       也標了 data-pagefind-ignore → Pagefind 只索引 4 篇文章「內文」，命中片段乾淨。
#     ▸ 產出的 dist/pagefind/ 會被下方洩漏檢查一併掃過守門（索引內容＝乾淨文章內文，零導外）。
#     ▸ npx -y pagefind@1：本機/CI/Cloudflare 首次會自動下載 pagefind（需 node，見 build-guide.yml）。
echo "▸ 建 Pagefind 全文搜尋索引（npx pagefind --site ${OUT}）"
npx -y pagefind@1 --site "$OUT"

# 4) 洩漏檢查守門：dist/ 內若出現任何「果果導流資訊」就中止部署
#    （品牌名「果果國際」允許；只擋連結/聯絡方式。電話只擋果果真實號碼 0906-536-833，教學裡的範例號碼放行）
LEAK='guoguo\.tw|guoguostock|lin\.ee|@guoguo|0906[- ]?536[- ]?833|superior\.ipad\.tw|景興路|文山區|11685|maps\.app\.goo\.gl|facebook\.com'
if grep -rEnI "$LEAK" "$OUT"; then
  echo ""
  echo "❌ 洩漏檢查失敗：上列位置出現導外資訊 → 中止部署（不要讓它上中性網域）。"
  exit 1
fi

echo "✅ 洩漏檢查通過：dist/ 零導外，可安全部署到中性網域。"
echo "── dist/ 檔案清單 ──"
find "$OUT" -type f | sort
