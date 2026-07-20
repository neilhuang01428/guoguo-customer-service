#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
# build-homepage.py — 讀 articles.json → 產生 index.html（首頁）
#   首頁＝F 方案：左「教學內容」＋右「常駐商品側欄」雙欄版面
#   來源：articles.json（文章清單，SSR 進原始碼＝SEO）
#         products.json（105 商品，只在瀏覽器 fetch，首頁不預讀）
#   產出：index.html（覆寫；此檔含導購側欄與商品連結，
#         不進 build-neutral.sh 的無導外版 allowlist）
#   用法：articles.json 有異動（新增/修改文章）後重跑一次：
#         python3 build-homepage.py
# ─────────────────────────────────────────────────────────────
import json
import os
import html

ROOT = os.path.dirname(os.path.abspath(__file__))
ARTICLES_PATH = os.path.join(ROOT, "articles.json")
OUT_PATH = os.path.join(ROOT, "index.html")

SHOP_URL = "https://www.guoguo.tw/shop"          # 果果賣場（側欄 CTA 導外目的地）
UTM = "utm_source=guide&utm_medium=home"          # 首頁導購一律帶這組 UTM

# ── OG / 分享 / canonical：只加在「導外版」首頁；中性版 noindex 不加，
#    也避免把 guoguo.tw 寫進中性版而觸發 build-neutral.sh 的洩漏檢查。──
GUIDE_HOME_URL = "https://www.guoguo.tw/guide/"
# 首頁分享圖（og:image）：1200×630。實際檔名讀 site.json 的 ogImage
# （由後台「首圖管理」發佈時維護）；沒有就用預設。組成 GitHub Pages 的絕對網址。
def _home_og_image():
    default_rel = "assets/og/guoguo-ipad-tutorial-home-cover.png"
    try:
        with open(os.path.join(ROOT, "site.json"), encoding="utf-8") as f:
            rel = json.load(f).get("ogImage") or default_rel
    except (OSError, ValueError):
        rel = default_rel
    return "https://www.guoguo.tw/guide/" + rel


OG_IMAGE = _home_og_image()
HOME_OG = """<link rel="canonical" href="{home}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="果果國際" />
<meta property="og:title" content="果果 · iPad 使用教學" />
<meta property="og:description" content="跟果果買 iPad，不只機況透明，還教你用得順——巧控鍵盤、大陸區 App、Apple Pencil、越獄…實用教學一次收錄。" />
<meta property="og:url" content="{home}" />
<meta property="og:image" content="{img}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="果果 · iPad 使用教學" />
<meta name="twitter:description" content="跟果果買 iPad，不只機況透明，還教你用得順——實用教學一次收錄。" />
<meta name="twitter:image" content="{img}" />""".format(home=GUIDE_HOME_URL, img=OG_IMAGE)

# 文章卡配色：依 articles.json 陣列「第一次出現的分類」依序輪流上色。
# 目前 4 篇剛好落在 上手→navy／技巧→green／選購→teal／觀念→red，
# 之後新增分類會自動接續 amber、purple，再繞回 navy。
HUES = ["navy", "green", "teal", "red", "amber", "purple"]

# 首頁文章卡外觀：導外版預設 "image"（圖卡，用每篇 ogImage；沒有就 fallback emoji）；
# 改成 "emoji" 可讓導外版全站切回 emoji 方塊。中性版一律 emoji（不引用任何圖，保持零導外）。
CARD_MODE = "image"


def esc(s):
    """HTML escape，供插入文字內容／屬性值使用（含雙引號，供 data-* 屬性安全）。"""
    return html.escape(str(s if s is not None else ""), quote=True)


def load_articles():
    with open(ARTICLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def category_colors(articles):
    colors = {}
    for a in articles:
        cat = a.get("category", "")
        if cat not in colors:
            colors[cat] = HUES[len(colors) % len(HUES)]
    return colors


def search_blob(a):
    """title + summary + tags + category 全部小寫串起來，給前端搜尋框比對用。"""
    parts = [a.get("title", ""), a.get("summary", ""), a.get("category", "")]
    parts += list(a.get("tags", []) or [])
    return esc(" ".join(str(p) for p in parts if p).lower())


def render_card(a, colors, card_mode="image"):
    """card_mode="image"：有 ogImage 就用圖卡（首圖），否則 fallback emoji 方塊；
       card_mode="emoji"：一律 emoji 方塊（中性版用，保持零導外、不引用任何圖）。"""
    hue = colors.get(a.get("category", ""), "navy")
    tags = [t for t in (a.get("tags") or []) if t]
    data_tags = esc(";".join(tags))
    icon = esc(a.get("icon", "📄"))
    category = esc(a.get("category", ""))
    title = esc(a.get("title", ""))
    summary = esc(a.get("summary", ""))
    url = esc(a.get("url", "#"))
    og = a.get("ogImage")
    if card_mode == "image" and og:
        top = ('<div class="thumb"><img src="{src}" alt="{alt}" '
               'loading="lazy" decoding="async"></div>').format(src=esc(og), alt=title)
    else:
        top = '<div class="ic">{icon}</div>'.format(icon=icon)
    return (
        '      <a class="g" style="--c:var(--{hue});--cbg:var(--{hue}-bg)" '
        'href="{url}" data-tags="{tags}" data-search="{search}">\n'
        '        {top}\n'
        '        <div class="tag">{cat}</div>\n'
        '        <h3>{title}</h3>\n'
        '        <p>{summary}</p>\n'
        '        <div class="go">閱讀指南</div>\n'
        '      </a>'
    ).format(
        hue=hue, url=url, tags=data_tags, search=search_blob(a),
        top=top, cat=category, title=title, summary=summary,
    )


def render_jsonld(articles):
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "name": a.get("title", ""),
            "url": a.get("url", ""),
        }
        for i, a in enumerate(articles)
    ]
    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "果果國際 iPad 使用教學總覽",
        "description": "果果國際客戶專屬的 iPad 使用教學指南集合。",
        "inLanguage": "zh-TW",
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "numberOfItems": len(articles),
        "itemListElement": items,
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    return raw.replace("</script", "<\\/script")  # 防止內容意外提早關閉 script 標籤


LOGO_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="11" fill="#17345f"/>'
    '<circle cx="15.5" cy="24.5" r="7" fill="#fff"/><circle cx="24.5" cy="24.5" r="7" fill="#fff" opacity=".85"/>'
    '<path d="M20 7.8c3.3-2.1 7.6-1.3 8.4 1.8-2.9 2.5-7.1 1.6-8.4-1.8z" fill="#3fbf6f"/>'
    '<rect x="19.1" y="8.2" width="1.8" height="6.6" rx=".9" fill="#3fbf6f"/></svg>'
)

SEARCH_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
    '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'
)

# ── CSS（純字串，不做 Python 插值，避免跟 CSS 的 {} 打架）───────────────
CSS = r"""
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
:root {
  --bg: #f6f8fb; --panel: #ffffff; --panel2: #f0f3f8; --line: #e2e8f0; --grid: #edf1f6;
  --ink: #16223a; --body: #45506a; --muted: #8590a6;
  --navy: #17345f;   --navy-deep: #0f2547; --navy-bg: #eef2f8;
  --green: #2f9e57;  --green-deep: #237a43; --green-bg: #eaf5ee;
  --amber: #b47d1e;  --amber-bg: #f8f0dc;
  --red: #c0492f;    --red-bg: #fbeae5;
  --teal: #1c8a9a;   --teal-bg: #e3f3f4;
  --purple: #7150c9; --purple-bg: #efeafb;
  --mono: 'SF Mono','JetBrains Mono','Menlo','Consolas',monospace;
  --sans: 'Noto Sans TC',-apple-system,BlinkMacSystemFont,'Segoe UI','Inter',sans-serif;
}
body { background: var(--bg); color: var(--body); font-family: var(--sans); line-height: 1.72; -webkit-font-smoothing: antialiased; min-height: 100vh; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 0 22px 100px; }

/* ── masthead（沿用既有 card-head 風格）── */
header.mast { padding: 30px 0 0; }
.card-head { background: #fff; border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 6px 20px rgba(20,39,68,.06); padding: 22px 26px; }
.card-head .top { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.logo { display: flex; align-items: center; gap: 12px; }
.logo svg { width: 42px; height: 42px; flex: none; }
.logo .wm { font-weight: 800; font-size: 1.1rem; color: var(--ink); line-height: 1.15; }
.logo .wm-sub { font-family: var(--mono); font-size: .55rem; letter-spacing: .2em; color: var(--muted); }
.tagline { text-align: right; font-size: .82rem; color: var(--muted); line-height: 1.5; }
.tagline b { color: var(--navy); }
.trust { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.trust span { font-size: .74rem; color: var(--navy); border: 1px solid var(--line); background: #fff; padding: 5px 12px; border-radius: 999px; }
.trust span b { color: var(--green-deep); }

/* ── hero + 搜尋（教學）── */
.hero { padding: 44px 4px 6px; }
.kicker { font-family: var(--mono); font-size: .72rem; letter-spacing: .05em; color: var(--navy); margin-bottom: 14px; }
.kicker::before { content: '// '; color: var(--muted); }
h1 { font-weight: 800; font-size: 2.5rem; line-height: 1.14; letter-spacing: -.02em; color: var(--ink); margin-bottom: 14px; }
.sub { font-size: 1.12rem; color: var(--body); max-width: 680px; }
.search-pill { display: flex; align-items: center; gap: 10px; background: #fff; border: 1.5px solid var(--line); border-radius: 16px; padding: 8px 8px 8px 18px; box-shadow: 0 6px 20px rgba(20,39,68,.06); max-width: 560px; margin-top: 24px; }
.search-pill svg { flex: none; width: 17px; height: 17px; color: var(--muted); }
.search-pill input { flex: 1; min-width: 0; border: 0; outline: 0; font: inherit; font-size: .92rem; color: var(--ink); background: transparent; }
.search-pill input::placeholder { color: var(--muted); }
.search-pill .sbtn { flex: none; background: var(--navy); color: #fff; font-size: .82rem; font-weight: 700; padding: 10px 20px; border-radius: 11px; border: 0; cursor: pointer; transition: .15s; font-family: inherit; }
.search-pill .sbtn:hover { background: var(--navy-deep); }

/* ── 雙欄：左教學內容／右常駐商品側欄 ── */
.cols { display: grid; grid-template-columns: minmax(0,1fr) 320px; gap: 26px; align-items: start; margin-top: 46px; }
.main { min-width: 0; }
.side { position: sticky; top: 20px; }
.cols.cols-solo { grid-template-columns: 1fr; }   /* 中性版首頁：無商品側欄 → 單欄 */

h2.glabel { font-family: var(--mono); font-weight: 700; font-size: .72rem; letter-spacing: .05em; color: var(--muted); margin: 0 0 4px; }
h2.glabel::before { content: '['; } h2.glabel::after { content: ']'; }
h2.glabel.small { font-size: .68rem; margin: 0; }

/* 篩選晶片（教學標籤／商品分類共用） */
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.chip { font-family: var(--mono); font-size: .78rem; font-weight: 600; padding: 7px 14px; border-radius: 999px; border: 1px solid var(--line); background: #fff; color: var(--body); cursor: pointer; transition: .15s; white-space: nowrap; }
.chip:hover { border-color: var(--navy); color: var(--navy); }
.chip.on { background: var(--navy); border-color: var(--navy); color: #fff; }
.chip .cnt { margin-left: 4px; opacity: .72; font-size: .85em; }
.chip.sm { font-size: .72rem; padding: 5px 11px; }

/* 文章卡 grid（沿用既有 a.g 卡片語彙） */
.grid2 { display: grid; grid-template-columns: repeat(auto-fill,minmax(260px,1fr)); gap: 14px; margin-top: 18px; }
a.g { display: flex; flex-direction: column; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 22px; text-decoration: none; box-shadow: 0 2px 10px rgba(20,39,68,.03); transition: .14s; border-top: 3px solid var(--c); }
a.g:hover { transform: translateY(-3px); box-shadow: 0 10px 26px rgba(20,39,68,.10); border-color: var(--c); }
a.g .ic { width: 46px; height: 46px; border-radius: 12px; background: var(--cbg); color: var(--c); display: grid; place-items: center; font-size: 1.4rem; margin-bottom: 14px; }
a.g .thumb { aspect-ratio: 1.9/1; border-radius: 10px; overflow: hidden; background: var(--cbg); margin-bottom: 14px; }
a.g .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
a.g .tag { font-family: var(--mono); font-size: .64rem; letter-spacing: .05em; color: var(--c); margin-bottom: 6px; }
a.g h3 { font-size: 1.16rem; color: var(--ink); font-weight: 800; margin-bottom: 7px; line-height: 1.3; }
a.g p { font-size: .9rem; color: var(--body); margin-bottom: 16px; flex: 1; }
a.g .go { font-family: var(--mono); font-size: .74rem; color: var(--c); font-weight: 700; }
a.g .go::after { content: ' →'; }

.empty-note { padding: 28px 20px; text-align: center; color: var(--muted); font-size: .92rem; background: var(--panel2); border-radius: 14px; border: 1px dashed var(--line); margin-top: 18px; }

__SHOP_CSS__

/* ── footer ── */
footer { margin-top: 54px; background: var(--navy-bg); border: 1px solid #dfe7f2; border-radius: 14px; padding: 22px 26px; }
footer .ft { font-size: 1.02rem; font-weight: 800; color: var(--navy); margin-bottom: 4px; }
footer p { font-size: .9rem; color: var(--body); margin: 0; }
.copy { text-align: center; font-family: var(--mono); font-size: .66rem; color: var(--muted); margin-top: 26px; }

@media (max-width: 900px) {
  .cols { grid-template-columns: 1fr; gap: 32px; }
  .side { position: static; }
}
@media (max-width: 640px) {
  .wrap { padding-left: 16px; padding-right: 16px; }
  .tagline { display: none; }
  h1 { font-size: 1.9rem; }
  .search-pill { flex-wrap: wrap; padding: 10px; }
  .search-pill .sbtn { width: 100%; justify-content: center; }
  .grid2 { grid-template-columns: 1fr; }
}
"""

# ── 商品側欄 CSS（只在導外版填入 __SHOP_CSS__；中性版以空字串取代，樣式表天生無側欄殘留）──
CSS_SHOP = r"""/* ── 側欄：果果精選商品 ── */
.side-card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 18px; box-shadow: 0 6px 20px rgba(20,39,68,.06); display: flex; flex-direction: column; gap: 13px; }
.stitle { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pin { font-family: var(--mono); font-size: .62rem; font-weight: 700; color: var(--teal); background: var(--teal-bg); padding: 3px 10px; border-radius: 999px; letter-spacing: .03em; flex: none; }

.shop-search { display: flex; align-items: center; gap: 8px; background: var(--panel2); border: 1px solid var(--line); border-radius: 11px; padding: 8px 12px; }
.shop-search svg { flex: none; width: 15px; height: 15px; color: var(--muted); }
.shop-search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; font: inherit; font-size: .84rem; color: var(--ink); }
.shop-search input::placeholder { color: var(--muted); }

.shop-cats { display: flex; flex-wrap: wrap; gap: 6px; }

.shop-list { display: flex; flex-direction: column; gap: 2px; max-height: min(520px,55vh); overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; margin-right: -4px; scrollbar-width: thin; scrollbar-color: var(--line) transparent; }
.shop-list::-webkit-scrollbar { width: 6px; }
.shop-list::-webkit-scrollbar-track { background: transparent; }
.shop-list::-webkit-scrollbar-thumb { background: var(--line); border-radius: 999px; }

.shop-status { display: flex; align-items: center; gap: 10px; padding: 26px 6px; font-size: .84rem; color: var(--muted); text-align: center; justify-content: center; }
.shop-status a { color: var(--navy); font-weight: 700; text-decoration: none; border-bottom: 1px dotted var(--navy); }
.spinner { width: 15px; height: 15px; border-radius: 50%; border: 2px solid var(--line); border-top-color: var(--navy); flex: none; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }

.shop-empty { padding: 20px 8px; font-size: .83rem; color: var(--muted); text-align: center; }

.shop-item { display: flex; gap: 12px; align-items: center; padding: 9px 6px; border-bottom: 1px solid var(--grid); text-decoration: none; border-radius: 10px; transition: .15s; }
.shop-item:last-child { border-bottom: 0; }
.shop-item:hover { background: var(--panel2); }
.shop-item .pic { width: 52px; height: 52px; border-radius: 10px; background: var(--panel2); flex: none; overflow: hidden; display: grid; place-items: center; }
.shop-item .pic img { width: 100%; height: 100%; object-fit: contain; padding: 5px; }
.shop-item .info { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 5px; }
.shop-item .ttl { font-size: .79rem; line-height: 1.42; color: var(--ink); font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.shop-item .price { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; font-variant-numeric: tabular-nums; }
.shop-item .now { font-size: .86rem; font-weight: 800; color: var(--red); }
.shop-item .was { font-size: .68rem; color: var(--muted); text-decoration: line-through; }
.shop-item .off { font-size: .64rem; font-weight: 700; color: var(--red); background: var(--red-bg); padding: 1px 7px; border-radius: 999px; }

.shop-cta { display: flex; align-items: center; justify-content: center; gap: 6px; background: var(--navy); color: #fff; text-decoration: none; font-size: .86rem; font-weight: 700; padding: 12px 16px; border-radius: 11px; transition: .15s; }
.shop-cta:hover { background: var(--navy-deep); transform: translateY(-1px); box-shadow: 0 8px 20px rgba(23,52,95,.22); }"""

# ── JS（純字串，不做 Python 插值）─────────────────────────────────────
JS = r"""
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  // 依出現次數（多→少，同數依字母序）排序、渲染成 chip 按鈕，補進 wrap 容器
  // （容器裡已經有一顆寫死的「全部」chip，這裡只補其餘）
  function renderCountChips(wrap, attr, counts) {
    var order = Object.keys(counts).sort(function (a, b) {
      return counts[b] - counts[a] || a.localeCompare(b, 'zh-Hant');
    });
    var frag = document.createDocumentFragment();
    order.forEach(function (key) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.dataset[attr] = key;
      b.innerHTML = esc(key) + '<span class="cnt">(' + counts[key] + ')</span>';
      frag.appendChild(b);
    });
    wrap.appendChild(frag);
  }

  function wireChips(wrap, attr, onChange) {
    wrap.addEventListener('click', function (e) {
      var btn = e.target.closest && e.target.closest('button[data-' + attr + ']');
      if (!btn) return;
      Array.prototype.forEach.call(wrap.children, function (b) {
        b.classList.toggle('on', b === btn);
      });
      onChange(btn.dataset[attr]);
    });
  }

  /* ---------- 全部教學：搜尋 + 標籤篩選 ---------- */
  (function () {
    var grid = document.getElementById('articleGrid');
    var chipsWrap = document.getElementById('filterChips');
    var emptyNote = document.getElementById('articleEmpty');
    var searchInput = document.getElementById('articleSearch');
    var searchBtn = document.getElementById('articleSearchBtn');
    if (!grid || !chipsWrap) return;

    var cards = Array.prototype.slice.call(grid.querySelectorAll('.g[data-tags]'));
    var activeTag = '__all__';
    var query = '';

    var counts = {};
    cards.forEach(function (c) {
      (c.dataset.tags || '').split(';').forEach(function (t) {
        t = t.trim();
        if (t) counts[t] = (counts[t] || 0) + 1;
      });
    });
    renderCountChips(chipsWrap, 'tag', counts);

    function apply() {
      var visible = 0;
      cards.forEach(function (c) {
        var tags = (c.dataset.tags || '').split(';');
        var ok = (activeTag === '__all__' || tags.indexOf(activeTag) > -1) &&
                 (!query || (c.dataset.search || '').indexOf(query) > -1);
        // 用 style.display（不是 hidden 屬性）：卡片本身有 a.g{display:flex} 規則，
        // hidden 屬性的 UA 樣式特異性打不贏它，會出現「設了 hidden 卻沒隱藏」的 bug。
        c.style.display = ok ? '' : 'none';
        if (ok) visible++;
      });
      if (!emptyNote) return;
      if (visible === 0) {
        emptyNote.textContent = query
          ? '找不到符合「' + query + '」的教學，換個關鍵字試試？'
          : '這個標籤還沒有文章，先看看其他教學吧！';
        emptyNote.style.display = '';
      } else {
        emptyNote.style.display = 'none';
      }
    }

    wireChips(chipsWrap, 'tag', function (v) {
      activeTag = v; apply();
      // 把目前標籤寫進網址 hash，方便分享／重新整理保留篩選
      try {
        var u = (v && v !== '__all__') ? '#tag=' + encodeURIComponent(v)
                                       : location.pathname + location.search;
        history.replaceState(null, '', u);
      } catch (e) {}
    });
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        query = searchInput.value.trim().toLowerCase();
        apply();
      });
    }
    if (searchBtn) {
      searchBtn.addEventListener('click', function () {
        if (searchInput) searchInput.focus();
        apply();
      });
    }
    apply();

    /* 深連結：從文章頁點「相關主題」標籤（/#tag=xxx 或 ?tag=xxx）進來
       → 自動套用該標籤篩選、把該 chip 標記為選中、並捲到教學區。 */
    (function () {
      var raw = location.hash.replace(/^#/, '') + '&' + location.search.replace(/^\?/, '');
      var m = /(?:^|&)tag=([^&]+)/.exec(raw);
      if (!m) return;
      var tag;
      try { tag = decodeURIComponent(m[1].replace(/\+/g, ' ')); } catch (e) { tag = m[1]; }
      var hit = Array.prototype.some.call(chipsWrap.children, function (b) { return b.dataset.tag === tag; });
      if (!hit) return;
      Array.prototype.forEach.call(chipsWrap.children, function (b) {
        b.classList.toggle('on', b.dataset.tag === tag);
      });
      activeTag = tag; apply();
      var g = document.getElementById('guides');
      if (g && g.scrollIntoView) setTimeout(function () { g.scrollIntoView({ block: 'start' }); }, 40);
    })();
  })();

__SHOP_JS__
})();
"""

# ── 商品側欄 JS（只在導外版注入到 __SHOP_JS__；中性版以空字串取代，天生無導購連結）──
JS_SHOP = r"""
  /* ---------- 側欄：果果精選商品（fetch products.json，可搜尋／分類／捲動） ---------- */
  (function () {
    var SHOP_CTA_URL = "__SHOP_CTA_URL__";  // 由 build-homepage.py 注入（賣場網址 + UTM）
    var listEl = document.getElementById('shopList');
    var catsWrap = document.getElementById('shopCats');
    var searchInput = document.getElementById('shopSearch');
    var statusEl = document.getElementById('shopStatus');
    var allCountEl = document.getElementById('shopAllCount');
    if (!listEl || !catsWrap) return;

    var products = [];
    var activeCat = '__all__';
    var query = '';

    function nt(n) { return 'NT$' + Number(n).toLocaleString('en-US'); }

    function withUtm(url) {
      try {
        var u = new URL(url, window.location.href);
        u.searchParams.set('utm_source', 'guide');
        u.searchParams.set('utm_medium', 'home');
        return u.toString();
      } catch (e) {
        return url + (url.indexOf('?') > -1 ? '&' : '?') + 'utm_source=guide&utm_medium=home';
      }
    }

    // category 欄位可能是分號分隔的多個階層路徑，例如
    // "充電組/轉接頭配件;充電組/轉接頭配件>充電組;其他周邊配件>更多"
    // 只取每段 '>' 之前的「第一層」，同一商品內去重。
    function topCats(catStr) {
      var out = [];
      (catStr || '').split(';').forEach(function (seg) {
        seg = seg.split('>')[0].trim();
        if (seg && out.indexOf(seg) === -1) out.push(seg);
      });
      return out;
    }

    function cardHTML(p) {
      var hasDiscount = p.compare_at_price && p.price && p.compare_at_price > p.price;
      var offPct = hasDiscount ? Math.round((1 - p.price / p.compare_at_price) * 100) : 0;
      var was = hasDiscount ? '<span class="was">' + nt(p.compare_at_price) + '</span>' : '';
      var off = (hasDiscount && offPct >= 1) ? '<span class="off">-' + offPct + '%</span>' : '';
      var now = p.price ? '<span class="now">' + nt(p.price) + '</span>' : '';
      return '<a class="shop-item" href="' + esc(withUtm(p.url)) + '" target="_blank" rel="noopener">' +
        '<span class="pic"><img src="' + esc(p.image) + '" alt="" loading="lazy" decoding="async"></span>' +
        '<span class="info"><span class="ttl">' + esc(p.title) + '</span>' +
        '<span class="price">' + now + was + off + '</span>' +
        '</span></a>';
    }

    function render() {
      var list = products.filter(function (p) {
        var catOk = activeCat === '__all__' || p._cats.indexOf(activeCat) > -1;
        var qOk = !query || p._search.indexOf(query) > -1;
        return catOk && qOk;
      });
      listEl.innerHTML = list.length ? list.map(cardHTML).join('') :
        '<p class="shop-empty">' + (query
          ? '找不到符合「' + esc(query) + '」的商品，換個關鍵字看看？'
          : '這個分類還沒有商品，看看其他分類吧！') + '</p>';
    }

    wireChips(catsWrap, 'cat', function (v) { activeCat = v; render(); });
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        query = searchInput.value.trim().toLowerCase();
        render();
      });
    }

    fetch('products.json')
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(function (data) {
        products = (data || []).map(function (p) {
          p._cats = topCats(p.category);
          p._search = (p.title || '').toLowerCase();
          return p;
        });
        if (statusEl) statusEl.style.display = 'none';
        if (allCountEl) allCountEl.textContent = '(' + products.length + ')';

        var counts = {};
        products.forEach(function (p) {
          p._cats.forEach(function (c) { counts[c] = (counts[c] || 0) + 1; });
        });
        renderCountChips(catsWrap, 'cat', counts);
        render();
      })
      .catch(function () {
        if (statusEl) {
          statusEl.style.display = '';
          statusEl.innerHTML = '商品清單暫時載入不了，<a href="' + SHOP_CTA_URL + '" target="_blank" rel="noopener">直接回賣場逛逛</a>吧！';
        }
      });
  })();
"""


# 中性版首頁輸出路徑（無導外版；供 build-neutral.sh 搬成中性網域的 index.html）
NEUTRAL_OUT_PATH = os.path.join(ROOT, "index.neutral.html")

# ── 左欄「全部教學」區塊（導外／中性共用）──
GUIDES_SECTION = """      <section class="guides" id="guides">
        <h2 class="glabel">全部教學</h2>
        <div class="filters" id="filterChips">
          <button type="button" class="chip on" data-tag="__all__">全部<span class="cnt">({total})</span></button>
        </div>
        <div class="grid2" id="articleGrid">
{cards}
        </div>
        <p class="empty-note" id="articleEmpty" style="display:none" aria-live="polite"></p>
      </section>"""

# ── 右欄「果果精選商品」側欄（只在導外版；中性版不輸出，天生無導購連結）──
ASIDE = """    <aside class="side" aria-label="果果精選商品">
      <div class="side-card">
        <div class="stitle">
          <h2 class="glabel small">果果精選商品</h2>
        </div>
        <div class="shop-search" role="search">
          {search_icon}
          <input type="search" id="shopSearch" placeholder="搜尋商品，例如「鍵盤」「保護殼」…" aria-label="搜尋商品">
        </div>
        <div class="shop-cats" id="shopCats">
          <button type="button" class="chip sm on" data-cat="__all__">全部<span class="cnt" id="shopAllCount"></span></button>
        </div>
        <div class="shop-list" id="shopList" aria-live="polite">
          <div class="shop-status" id="shopStatus"><span class="spinner" aria-hidden="true"></span>商品載入中…</div>
        </div>
        <a class="shop-cta" id="shopCta" href="{shop_cta_url}" target="_blank" rel="noopener">回賣場看全部商品 →</a>
      </div>
    </aside>"""

# ── 頁尾：導外版（保留「找客服」）／中性版（不涉聯繫，只講買機教你用）──
FOOTER_FULL = """  <footer>
    <div class="ft">有 iPad 使用問題？隨時找果果客服</div>
    <p>買機教你用，終身售後諮詢。操作上有任何不確定，或想確認手上機型能不能做某件事，都歡迎先問我們的客服——我們很樂意幫你。</p>
  </footer>"""

FOOTER_NEUTRAL = """  <footer>
    <div class="ft">跟果果買 iPad，不只機況透明，還教你用得順</div>
    <p>這裡收錄我們寫給客戶的 iPad 實用教學——白話、舉例、當你是小白，一步步帶你上手。內容會持續補充更新。</p>
  </footer>"""

# ── 頁面外殼（導外／中性共用；差異只在 {middle}／{footer}／{js} 三處）──
PAGE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>果果國際 · iPad 使用教學總覽</title>
<meta name="description" content="果果國際客戶專屬的 iPad 使用教學：巧控鍵盤、下載大陸區 App、剪片要不要買 Apple Pencil、越獄該不該碰。買機教你用，終身售後諮詢。" />
{oghead}
<style>{css}</style>
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body>
<div class="wrap">
  <header class="mast">
    <div class="card-head">
      <div class="top">
        <div class="logo">
          {logo}
          <div><div class="wm">果果國際</div><div class="wm-sub">GUOGUO INTERNATIONAL</div></div>
        </div>
        <div class="tagline"><b>台灣最專業的 Apple 福利機供應商</b><br>iPad 選購，都交給我們</div>
      </div>
      <div class="trust"><span>40 道專業檢測</span><span>資訊透明・缺點揭露</span><span>買機<b>教你用</b></span><span>終身售後諮詢</span></div>
    </div>
  </header>

  <div class="hero">
    <div class="kicker">iPad 使用教學總覽</div>
    <h1>果果 · iPad 使用教學</h1>
    <p class="sub">跟果果買了 iPad，不只機況透明，還教你怎麼用得順。這裡收錄我們寫給客戶的實用指南——白話、舉例、當你是小白，一步步帶你上手。</p>
    <div class="search-pill" role="search">
      {search_icon}
      <input type="search" id="articleSearch" placeholder="搜尋教學，例如「剪映」「鍵盤」「越獄」…" aria-label="搜尋教學">
      <button type="button" class="sbtn" id="articleSearchBtn">搜尋</button>
    </div>
  </div>

{middle}

{footer}

  <div class="copy">© 果果國際 GUOGUO INTERNATIONAL</div>
</div>
<script>{js}</script>
</body>
</html>
"""


def build_html(articles, neutral=False):
    """neutral=False → 導外版首頁（含商品側欄）；neutral=True → 中性版首頁（無側欄、無導購連結）。"""
    colors = category_colors(articles)
    card_mode = "emoji" if neutral else CARD_MODE   # 中性版一律 emoji（零導外）
    cards_html = "\n".join(render_card(a, colors, card_mode) for a in articles)
    jsonld = render_jsonld(articles)
    total = len(articles)

    guides = GUIDES_SECTION.format(total=total, cards=cards_html)

    if neutral:
        # 單欄（cols-solo）、無 <aside>、頁尾不涉聯繫；JS 去掉整段商品側欄 → 無任何 guoguo 連結
        middle = (
            '  <div class="cols cols-solo">\n'
            '    <div class="main">\n{0}\n    </div>\n'
            '  </div>'
        ).format(guides)
        footer = FOOTER_NEUTRAL
        css_final = CSS.replace("__SHOP_CSS__", "")
        js_final = JS.replace("__SHOP_JS__", "")
        oghead = ""  # 中性版不加 OG/canonical（noindex + 避免 guoguo.tw 洩漏）
    else:
        shop_cta_url = "{0}?{1}".format(SHOP_URL, UTM)
        aside = ASIDE.format(search_icon=SEARCH_ICON, shop_cta_url=esc(shop_cta_url))
        middle = (
            '  <div class="cols">\n'
            '    <div class="main">\n{0}\n    </div>\n\n'
            '{1}\n'
            '  </div>'
        ).format(guides, aside)
        footer = FOOTER_FULL
        css_final = CSS.replace("__SHOP_CSS__", CSS_SHOP)
        js_final = JS.replace("__SHOP_JS__", JS_SHOP).replace(
            '"__SHOP_CTA_URL__"', json.dumps(shop_cta_url)
        )
        oghead = HOME_OG  # 導外版首頁：加 OG/twitter/canonical

    return PAGE.format(
        css=css_final,
        jsonld=jsonld,
        oghead=oghead,
        logo=LOGO_SVG,
        search_icon=SEARCH_ICON,
        middle=middle,
        footer=footer,
        js=js_final,
    )


def main():
    articles = load_articles()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(build_html(articles, neutral=False))
    with open(NEUTRAL_OUT_PATH, "w", encoding="utf-8") as f:
        f.write(build_html(articles, neutral=True))
    print(
        "✅ 產生 index.html（導外版，含商品側欄）＋ index.neutral.html"
        "（中性版，無側欄／無導購連結）：{0} 篇教學。".format(len(articles))
    )


if __name__ == "__main__":
    main()
