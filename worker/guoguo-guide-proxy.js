/* ══════════════════════════════════════════════════════════════════
   果果 GUIDE · Cloudflare Worker
   反向代理 GitHub Pages → www.guoguo.tw/guide/
   ＋ .html 容錯（有無 .html 都能開）
   ＋ 導外版共用 chrome 注入（頂部回賣場麵包屑 / 頁尾 / 浮動鈕）
   ＋ GA4 流量分析注入（導外版；與賣場同一資源，含回賣場/LINE/電話等點擊事件）

   ▸ 部署：Cloudflare 後台 → Workers & Pages → 貼上此檔 → Deploy
   ▸ Route：*guoguo.tw/guide/*  和  guoguo.tw/guide/*
   ▸ 改「chrome」＝改這一支＝全站導外版一起變（免 rebuild）
   ▸ 無導外版走中性網域、不經這支 Worker，天生沒有導外資訊
   ══════════════════════════════════════════════════════════════════ */

const ORIGIN = 'https://neilhuang01428.github.io/guoguo-customer-service'

/* ── GA4 流量分析（只注入導外版；與賣場同一個資源 → 可追「看教學→回賣場→下單」導購全貌）
   含事件：shop_click / line_click / call_click / mail_click / map_click ── */
const GA4_ID = 'G-8R0EYJ91SJ'
const ANALYTICS = `<script async src="https://www.googletagmanager.com/gtag/js?id=${GA4_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','${GA4_ID}');
document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a');if(!a)return;var h=a.getAttribute('href')||'';if(a.classList.contains('gg-back')||a.classList.contains('gg-shop'))gtag('event','shop_click',{link_url:h});else if(a.classList.contains('gg-guidehome'))gtag('event','guide_home_click',{link_url:h});else if(h.indexOf('lin.ee')>-1)gtag('event','line_click',{link_url:h});else if(h.indexOf('tel:')===0)gtag('event','call_click',{link_url:h});else if(h.indexOf('mailto:')===0)gtag('event','mail_click',{link_url:h});else if(h.indexOf('maps.')>-1)gtag('event','map_click',{link_url:h})},true);</script>`

/* ── 官方聯絡資料（只出現在導外版）────────────────────────────── */
const C = {
  line:  'https://lin.ee/TOSchgh',
  lineId:'@guoguo.tw',
  tel:   '0906-536-833',
  email: 'superior.ipad.tw@gmail.com',
  map:   'https://maps.app.goo.gl/kWKVVK7V8JtQ4vHa9',
  addr:  '11685 臺北市文山區景興路23巷6弄11號4樓',
  shop:  'https://www.guoguo.tw/shop',
  fb:    'https://www.facebook.com/profile.php?id=100070652028382',
  stock: 'https://www.guoguostock.com/',
  hours: '平日 11:00–18:00',
}

addEventListener('fetch', event => event.respondWith(handle(event.request)))

async function handle(request) {
  const url = new URL(request.url)
  const p = url.pathname

  if (p !== '/guide' && !p.startsWith('/guide/')) return fetch(request)      // 放行官網
  if (p === '/guide') return Response.redirect(url.origin + '/guide/', 301)   // 補斜線

  let sub = p.slice(6)                          // 去掉 '/guide'
  if (sub === '' || sub === '/') sub = '/index.html'

  // T7：舊文章網址 /guide/<slug>/<檔>.html → 301 轉到乾淨網址 /guide/<slug>/
  //     只命中「兩層、結尾 .html、且非 index.html」且 slug 是真文章；首頁(/index.html 單層)與其他資源不受影響
  const oldUrl = sub.match(/^\/([^/]+)\/([^/]+)\.html$/)
  if (oldUrl && oldUrl[2] !== 'index') {
    const { articles } = await getShopData()
    if (articles && articles.some(a => a && a.slug === oldUrl[1])) {
      return Response.redirect(url.origin + '/guide/' + oldUrl[1] + '/', 301)
    }
  }

  const res = await fetchWithFallback(sub)
  const ct = res.headers.get('content-type') || ''
  if (!ct.includes('text/html')) return res                                   // 非 HTML 原樣回

  const isHome = /(^|\/)index\.html$/.test(sub)                                 // 教學總覽首頁
  const slug = sub.split('/').filter(Boolean)[0] || ''      // 文章 slug（對應 guide-map.json）
  const promo = isHome ? '' : await buildPromo(slug)         // 導購版位 HTML（無對應則空字串）
  // 首頁的 OG/canonical 已由 build-homepage.py 寫進 index.html；文章頁在這裡注入（無對應 slug 則空）
  const headMeta = isHome ? '' : await buildArticleHead(slug)
  const tags = isHome ? '' : await buildTags(slug)           // 文章頁尾「相關主題」標籤（連回首頁篩選；取代手動延伸閱讀）
  const rw = new HTMLRewriter()
    .on('head', { element(el) { el.prepend(ANALYTICS, { html: true }); el.append(CHROME_CSS + headMeta, { html: true }) } })
    .on('body', { element(el) { el.append(FLOATING, { html: true }) } })        // 右下浮動鈕（fixed）

  if (isHome) {
    // 首頁沒有 <main>、有自己的頁首頁尾 → 用 header tag（最穩）把「回賣場」麵包屑插在 masthead 之前
    rw.on('header', { element(el) { el.before('<span id="gg-top"></span>' + TOPBAR_HOME, { html: true }) } })
  } else {
    // 一般文章：注入完整麵包屑（賣場 › 教學 › 本篇）＋頁尾
    rw.on('main', {
      element(el) {
        el.prepend('<span id="gg-top"></span>' + TOPBAR, { html: true })         // 頂部麵包屑
        el.append(tags + promo + FOOTER, { html: true })                                 // 相關主題標籤 › 導購 › 頁尾
      }
    })
  }
  return rw.transform(res)
}

/* ── 導購版位：讀 products.json + guide-map.json 組商品卡（只在導外版；
   資料全在 JSON，破百篇 Worker 不用改；含 UTM 供 GA4 追蹤導購）── */
let _shopCache = { at: 0, products: null, map: null, articles: null }
async function getShopData() {
  if (_shopCache.products && Date.now() - _shopCache.at < 300000) return _shopCache   // 快取 5 分鐘
  try {
    const [products, map, articles] = await Promise.all([
      fetch(ORIGIN + '/products.json').then(r => r.ok ? r.json() : null),
      fetch(ORIGIN + '/guide-map.json').then(r => r.ok ? r.json() : null),
      fetch(ORIGIN + '/articles.json').then(r => r.ok ? r.json() : null),
    ])
    if (products && map) _shopCache = { at: Date.now(), products, map, articles }
  } catch (e) { /* 抓失敗沿用舊快取 */ }
  return _shopCache
}

/* ── 文章頁 <head> 注入：canonical + OG/Twitter + BreadcrumbList JSON-LD（只導外版，做 SEO / LINE 分享）
   標題與描述取自 articles.json；canonical 一律指向該篇的正式 url（-navy/原版等替代檔也會收斂到正式版）。
   找不到該 slug 就回空字串、不硬塞。── */
const OG_IMAGE = 'https://www.guoguo.tw/guide/assets/og/guoguo-ipad-tutorial-home-cover.png'  // 文章沒設 ogImage 時的站台預設分享圖
async function buildArticleHead(slug) {
  const { articles } = await getShopData()
  if (!articles) return ''
  const a = articles.find(x => x && x.slug === slug)
  if (!a) return ''
  const canonical = 'https://www.guoguo.tw/guide/' + a.url
  const ogimg = a.ogImage ? 'https://www.guoguo.tw/guide/' + a.ogImage : OG_IMAGE  // 逐篇首圖，沒有就用站台預設
  const title = esc(a.title || '')
  const desc = esc(a.summary || '')
  const ld = JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'iPad 使用教學', item: 'https://www.guoguo.tw/guide/' },
      { '@type': 'ListItem', position: 2, name: a.title || '' },
    ],
  }).replace(/</g, '\\u003c')
  return `<link rel="canonical" href="${esc(canonical)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="果果國際">
<meta property="og:title" content="${title}">
<meta property="og:description" content="${desc}">
<meta property="og:url" content="${esc(canonical)}">
<meta property="og:image" content="${ogimg}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${title}">
<meta name="twitter:description" content="${desc}">
<meta name="twitter:image" content="${ogimg}">
<script type="application/ld+json">${ld}</script>`
}

/* ── 文章頁尾「相關主題」標籤：讀 articles.json 的 tags，做成可點膠囊 →
   連回教學總覽首頁並帶 #tag=，首頁會自動篩出同標籤文章（取代手動維護的「延伸閱讀」）。
   找不到 slug 或沒 tags 就回空字串、不硬塞。── */
async function buildTags(slug) {
  const { articles } = await getShopData()
  if (!articles) return ''
  const a = articles.find(x => x && x.slug === slug)
  if (!a || !a.tags || !a.tags.length) return ''
  const chips = a.tags
    .filter(Boolean)
    .map(t => `<a class="gg-tag" href="/guide/#tag=${encodeURIComponent(t)}">${esc(t)}</a>`)
    .join('')
  if (!chips) return ''
  return `<nav class="gg-tags" aria-label="相關主題標籤">
  <div class="gg-tags-h">想看更多同主題的教學？點標籤逛逛 👇</div>
  <div class="gg-tags-list">${chips}</div>
</nav>`
}
async function buildPromo(slug) {
  const { products, map } = await getShopData()
  if (!products || !map) return ''
  const entry = map[slug]
  if (!entry || !entry.products || !entry.products.length) return ''
  const byId = {}; products.forEach(p => { byId[p.id] = p })
  const cards = entry.products.map(id => byId[id]).filter(Boolean).map(cardHTML).join('')
  if (!cards) return ''
  return `<section class="gg-promo" aria-label="果果精選商品">
  <div class="gg-promo-head"><span class="gg-promo-tag">果果嚴選</span><h3>${esc(entry.heading || '這篇的相關好物')}</h3></div>
  <div class="gg-promo-grid">${cards}</div>
  <a class="gg-promo-more gg-shop" href="${C.shop}?utm_source=guide&utm_medium=promo&utm_campaign=${encodeURIComponent(slug)}" target="_blank" rel="noopener">看更多果果好物 →</a>
</section>`
}
function cardHTML(p) {
  const nt = n => 'NT$' + Number(n).toLocaleString('en-US')
  const price = p.price ? nt(p.price) : ''
  const was = (p.compare_at_price && p.compare_at_price > p.price) ? ` <span class="gg-was"><s>${nt(p.compare_at_price)}</s></span>` : ''
  const url = p.url + (p.url.includes('?') ? '&' : '?') + 'utm_source=guide&utm_medium=promo'
  return `<a class="gg-pcard gg-shop" href="${url}" target="_blank" rel="noopener">
  <span class="gg-pcard-img"><img src="${p.image}" alt="${esc(p.title)}" loading="lazy"></span>
  <span class="gg-pcard-body"><span class="gg-pcard-title">${esc(p.title)}</span><span class="gg-pcard-price">${price}${was}</span><span class="gg-pcard-btn">進來逛逛</span></span>
</a>`
}
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])) }

/* ── .html 容錯：依序試多種可能路徑 ──────────────────────────── */
async function fetchWithFallback(sub) {
  const hasExt = /\.[a-z0-9]+$/i.test(sub)
  let tries
  if (hasExt) {
    tries = [sub]
  } else if (sub.endsWith('/')) {
    const base = sub.slice(0, -1)
    const seg = base.split('/').filter(Boolean).pop() || 'index'
    tries = [sub + 'index.html', base + '/' + seg + '.html']
  } else {
    const seg = sub.split('/').filter(Boolean).pop()
    tries = [sub, sub + '.html', sub + '/index.html', sub + '/' + seg + '.html']
  }
  for (const t of tries) {
    const r = await fetch(ORIGIN + t)
    if (r.ok) return r
  }
  return fetch(ORIGIN + tries[0])
}

/* ══ 以下為「共用 chrome」，改這裡＝全站導外版一起變 ══════════════ */

const LOGO = '<svg viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="11" fill="#17345f"/><circle cx="15.5" cy="24.5" r="7" fill="#fff"/><circle cx="24.5" cy="24.5" r="7" fill="#fff" opacity=".85"/><path d="M20 7.8c3.3-2.1 7.6-1.3 8.4 1.8-2.9 2.5-7.1 1.6-8.4-1.8z" fill="#3fbf6f"/><rect x="19.1" y="8.2" width="1.8" height="6.6" rx=".9" fill="#3fbf6f"/></svg>'

/* 小型線性 icon（頁尾用，16px、吃 currentColor） */
const I = {
  chat: '<svg class="gg-i" viewBox="0 0 24 24"><path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.8-.8L3 21l1.9-4.1A8.4 8.4 0 1 1 21 11.5z"/></svg>',
  phone:'<svg class="gg-i" viewBox="0 0 24 24"><path d="M22 16.9v2.6a2 2 0 0 1-2.2 2 19.6 19.6 0 0 1-8.5-3 19.3 19.3 0 0 1-6-6 19.6 19.6 0 0 1-3-8.5A2 2 0 0 1 4.7 2h2.6a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.6a2 2 0 0 1-.5 2.1L8.3 9.8a16 16 0 0 0 6 6l1.4-1.2a2 2 0 0 1 2.1-.4c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2z"/></svg>',
  mail: '<svg class="gg-i" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5 12 12l8.5-5.5"/></svg>',
  pin:  '<svg class="gg-i" viewBox="0 0 24 24"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="2.8"/></svg>',
  clock:'<svg class="gg-i" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 1.8"/></svg>',
  box:  '<svg class="gg-i" viewBox="0 0 24 24"><path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/></svg>',
  fb:   '<svg class="gg-i" viewBox="0 0 24 24"><path d="M17 2h-3a4.5 4.5 0 0 0-4.5 4.5V10H7v4h2.5v8h4v-8H16l.8-4h-3.3V6.6c0-.7.4-1.1 1.1-1.1H17z"/></svg>',
}

const CHROME_CSS = `<style>
/* ── 頂部麵包屑：果果賣場 › iPad 使用教學 › 本篇（可點膠囊、明顯可按；sticky 置頂、捲動不消失）── */
.gg-crumb{position:sticky;top:0;z-index:50;display:flex;align-items:center;flex-wrap:wrap;gap:5px 7px;font-family:var(--sans);font-size:.94rem;color:var(--muted,#8590a6);padding:11px 0 12px;margin:0;border-bottom:1px solid var(--line,#e2e8f0);background:var(--bg,#f6f8fb)}
.gg-crumb a.gg-cr{display:inline-flex;align-items:center;gap:7px;color:var(--navy,#17345f);text-decoration:none;font-weight:700;padding:8px 16px;border:1px solid #cfdaec;border-radius:999px;background:#fff;box-shadow:0 1px 2px rgba(20,39,68,.05);transition:.14s;cursor:pointer}
.gg-crumb a.gg-cr:hover{border-color:var(--navy,#17345f);background:#f2f7fd;box-shadow:0 4px 12px rgba(20,39,68,.13);transform:translateY(-1px)}
.gg-crumb a.gg-cr:active{transform:translateY(0)}
.gg-crumb a.gg-cr svg{width:18px;height:18px;flex:none;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
.gg-crumb .gg-sep{color:#b8c3d4;font-size:1.05rem;line-height:1;margin:0 1px}
.gg-crumb .gg-cur{color:var(--body,#45506a);font-weight:700;padding:0 6px;font-size:.94rem}

/* ── 右下浮動鈕 ── */
.gg-fab{position:fixed;right:18px;bottom:22px;display:flex;flex-direction:column;gap:14px;z-index:60}
.gg-fab a{width:50px;height:50px;border-radius:50%;background:#fff;box-shadow:0 2px 8px rgba(20,39,68,.12),0 10px 26px rgba(20,39,68,.10);display:grid;place-items:center;text-decoration:none;transition:transform .16s cubic-bezier(.34,1.56,.64,1),box-shadow .16s}
.gg-fab a:hover{transform:translateY(-3px) scale(1.04);box-shadow:0 5px 14px rgba(20,39,68,.18),0 16px 34px rgba(20,39,68,.16)}
.gg-fab a:active{transform:translateY(-1px) scale(.98)}
.gg-fab a svg{display:block}
.gg-fab .gg-lbl{position:absolute;right:60px;top:50%;transform:translateY(-50%);background:#16223a;color:#fff;font-family:var(--sans);font-size:.74rem;font-weight:600;padding:4px 10px;border-radius:7px;white-space:nowrap;opacity:0;pointer-events:none;transition:.16s}
.gg-fab a{position:relative}
.gg-fab a:hover .gg-lbl{opacity:.96;right:62px}

/* ── 頁尾 ── */
.gg-foot{margin:64px 0 0;background:linear-gradient(180deg,#fcfdff 0%,#f2f6fc 100%);border:1px solid #e4ebf4;border-top:3px solid var(--navy,#17345f);border-radius:18px;padding:28px 32px 24px;font-family:var(--sans);box-shadow:0 8px 30px rgba(20,39,68,.05)}
.gg-foot .gg-top{display:flex;align-items:center;justify-content:space-between;gap:22px;flex-wrap:wrap;padding-bottom:20px;border-bottom:1px solid #e6ecf5}
.gg-foot .gg-brand{display:flex;align-items:center;gap:14px}
.gg-foot .gg-brand svg{width:46px;height:46px;flex:none}
.gg-foot .gg-brand b{display:block;color:var(--ink,#16223a);font-size:1.08rem;font-weight:800;line-height:1.2}
.gg-foot .gg-brand small{color:var(--muted,#8590a6);font-size:.79rem}
.gg-foot a.gg-shop{display:inline-flex;align-items:center;gap:9px;background:var(--navy,#17345f);color:#fff;text-decoration:none;font-weight:800;font-size:.95rem;padding:13px 26px;border-radius:12px;box-shadow:0 5px 16px rgba(23,52,95,.28);transition:.16s}
.gg-foot a.gg-shop:hover{background:var(--navy-deep,#0f2547);transform:translateY(-2px);box-shadow:0 9px 24px rgba(23,52,95,.34)}
.gg-foot a.gg-shop svg{width:19px;height:19px;stroke:#fff;stroke-width:1.9;fill:none;stroke-linecap:round;stroke-linejoin:round}
.gg-foot .gg-trust{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 4px}
.gg-foot .gg-trust span{font-size:.75rem;color:var(--navy,#17345f);background:#fff;border:1px solid #e2e8f0;border-radius:999px;padding:5px 14px}
.gg-foot .gg-trust span b{color:var(--green-deep,#237a43);font-weight:800}
.gg-foot .gg-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(196px,1fr));gap:18px 30px;margin-top:18px}
.gg-foot .gg-col h5{font-size:.66rem;font-family:var(--mono);letter-spacing:.1em;color:var(--muted,#8590a6);margin:0 0 10px;font-weight:700}
.gg-foot .gg-col a,.gg-foot .gg-col .gg-line2{display:flex;align-items:center;gap:9px;color:var(--body,#45506a);text-decoration:none;font-size:.88rem;padding:4px 0;line-height:1.5;transition:.13s}
.gg-foot .gg-col a:hover{color:var(--navy,#17345f)}
.gg-foot .gg-i{width:16px;height:16px;flex:none;stroke:var(--navy,#17345f);stroke-width:1.8;fill:none;stroke-linecap:round;stroke-linejoin:round;opacity:.72}
.gg-foot .gg-col a:hover .gg-i{opacity:1}
.gg-foot .gg-copy{margin-top:22px;padding-top:15px;border-top:1px solid #e6ecf5;font-size:.76rem;color:var(--muted,#8590a6);display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}
@media(max-width:860px){.gg-foot{padding:22px 18px}.gg-foot .gg-top{flex-direction:column;align-items:flex-start;gap:14px}.gg-fab a{width:46px;height:46px}}

/* ── 文章頁尾「相關主題」標籤（連回首頁 #tag= 篩選）── */
nav.gg-tags{display:block!important;width:auto!important;min-width:0!important;position:static!important;height:auto!important;overflow:visible;margin:52px 0 0;padding:22px 26px;background:linear-gradient(180deg,#ffffff,#f4f8fd);border:1px solid #e4ebf4;border-top:3px solid var(--teal,#1c8a9a);border-radius:18px;font-family:var(--sans);box-shadow:0 8px 30px rgba(20,39,68,.05)}
nav.gg-tags .gg-tags-h{font-size:.98rem;font-weight:800;color:var(--ink,#16223a);margin:0 0 14px}
nav.gg-tags .gg-tags-list{display:flex!important;flex-direction:row!important;flex-wrap:wrap!important;align-items:center;gap:9px}
nav.gg-tags a.gg-tag{display:inline-flex!important;width:auto!important;align-items:center;text-decoration:none;font-size:.9rem;font-weight:700;color:var(--navy,#17345f);background:#fff;border:1px solid #cfdaec;border-radius:999px;padding:8px 16px;transition:.14s}
nav.gg-tags a.gg-tag::before{content:'#';color:var(--teal,#1c8a9a);margin-right:5px;font-weight:800}
nav.gg-tags a.gg-tag:hover{border-color:var(--navy,#17345f);background:#f2f7fd;transform:translateY(-1px);box-shadow:0 4px 12px rgba(20,39,68,.13)}
@media(max-width:520px){nav.gg-tags{padding:18px 16px}nav.gg-tags .gg-tags-list{gap:8px}nav.gg-tags a.gg-tag{padding:7px 13px;font-size:.86rem}}

/* ── 導購版位（商品卡）── */
.gg-promo{margin:56px 0 0;padding:26px 28px 24px;background:linear-gradient(180deg,#ffffff,#f4f8fd);border:1px solid #e4ebf4;border-top:3px solid var(--green,#2f9e57);border-radius:18px;font-family:var(--sans);box-shadow:0 8px 30px rgba(20,39,68,.05)}
.gg-promo-head{display:flex;align-items:center;gap:11px;flex-wrap:wrap}
.gg-promo-tag{font-family:var(--mono);font-size:.64rem;letter-spacing:.14em;color:var(--green-deep,#237a43);background:var(--green-bg,#eaf5ee);border:1px solid #cbe6d5;padding:4px 10px;border-radius:999px;font-weight:700}
.gg-promo-head h3{font-size:1.1rem;font-weight:800;color:var(--ink,#16223a);margin:0;line-height:1.35}
.gg-promo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px;margin:18px 0 4px}
.gg-pcard{display:flex;flex-direction:column;background:#fff;border:1px solid var(--line,#e2e8f0);border-radius:14px;overflow:hidden;text-decoration:none;box-shadow:0 2px 10px rgba(20,39,68,.04);transition:transform .16s,box-shadow .16s,border-color .16s}
.gg-pcard:hover{transform:translateY(-3px);box-shadow:0 12px 30px rgba(20,39,68,.13);border-color:#cfdaec}
.gg-pcard-img{display:block;aspect-ratio:1/1;background:#f6f8fb;padding:12px}
.gg-pcard-img img{width:100%;height:100%;object-fit:contain;display:block}
.gg-pcard-body{display:flex;flex-direction:column;gap:8px;padding:13px 15px 15px;flex:1}
.gg-pcard-title{font-size:.86rem;line-height:1.45;color:var(--body,#45506a);font-weight:600;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.5em}
.gg-pcard-price{font-size:1.02rem;font-weight:800;color:var(--navy,#17345f);margin-top:auto}
.gg-pcard-price .gg-was{font-size:.78rem;font-weight:500;color:var(--muted,#8590a6);margin-left:5px}
.gg-pcard-btn{display:flex;align-items:center;justify-content:center;background:var(--navy,#17345f);color:#fff;font-size:.82rem;font-weight:700;padding:8px 0;border-radius:9px;margin-top:3px;transition:background .15s}
.gg-pcard:hover .gg-pcard-btn{background:var(--navy-deep,#0f2547)}
.gg-promo-more{display:inline-block;margin-top:14px;font-size:.85rem;font-weight:700;color:var(--navy,#17345f);text-decoration:none;font-family:var(--mono)}
.gg-promo-more:hover{color:var(--navy-deep,#0f2547);text-decoration:underline}
@media(max-width:560px){.gg-promo{padding:20px 16px}.gg-promo-grid{grid-template-columns:1fr 1fr;gap:11px}.gg-pcard-body{padding:10px 11px 12px}.gg-pcard-title{font-size:.8rem}}
</style>`

/* ── 頂部麵包屑：果果賣場 › iPad 使用教學 › 本篇（購物袋圖示=賣場、書本圖示=教學首頁，靠圖示與層級區分）── */
const TOPBAR = `<div class="gg-crumb" aria-label="麵包屑導覽">
  <a class="gg-cr gg-shop" href="${C.shop}" target="_blank" rel="noopener" aria-label="前往果果賣場">
    <svg viewBox="0 0 24 24"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>果果賣場
  </a>
  <span class="gg-sep" aria-hidden="true">›</span>
  <a class="gg-cr gg-guidehome" href="/guide/" aria-label="回 iPad 使用教學總覽首頁">
    <svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>iPad 使用教學
  </a>
  <span class="gg-sep" aria-hidden="true">›</span>
  <span class="gg-cur">本篇教學</span>
</div>`

/* ── 首頁專用麵包屑：果果賣場 › iPad 使用教學（教學＝目前位置，只給「回賣場」入口）── */
const TOPBAR_HOME = `<div class="gg-crumb" aria-label="麵包屑導覽">
  <a class="gg-cr gg-shop" href="${C.shop}" target="_blank" rel="noopener" aria-label="回果果賣場首頁">
    <svg viewBox="0 0 24 24"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>果果賣場
  </a>
  <span class="gg-sep" aria-hidden="true">›</span>
  <span class="gg-cur">iPad 使用教學</span>
</div>`

/* ── 右下浮動鈕：回頂 / LINE / Map / 電話（正規 SVG，純連結、無 JS 也可點）── */
const FLOATING = `<div class="gg-fab" aria-label="快速聯絡">
  <a href="#gg-top" aria-label="回到頂端"><span class="gg-lbl">回到頂端</span>
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#17345f" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V6"/><path d="M6 11l6-6 6 6"/></svg></a>
  <a href="${C.line}" target="_blank" rel="noopener" aria-label="官方 LINE"><span class="gg-lbl">官方 LINE ${C.lineId}</span>
    <svg width="30" height="30" viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="#06C755"/><text x="16" y="20.4" font-family="Arial,Helvetica,sans-serif" font-size="8.6" font-weight="800" fill="#fff" text-anchor="middle" letter-spacing=".4">LINE</text></svg></a>
  <a href="${C.map}" target="_blank" rel="noopener" aria-label="門市地圖"><span class="gg-lbl">門市地圖</span>
    <svg width="24" height="26" viewBox="0 0 24 26"><path d="M12 1C6.9 1 3 5 3 9.9c0 1.8.6 3.4 1.4 4.8L12 25l7.6-10.3c.8-1.4 1.4-3 1.4-4.8C21 5 17.1 1 12 1z" fill="#EA4335"/><circle cx="12" cy="9.9" r="3.4" fill="#fff"/></svg></a>
  <a href="tel:${C.tel.replace(/-/g,'')}" aria-label="客服電話 ${C.tel}"><span class="gg-lbl">客服 ${C.tel}</span>
    <svg width="21" height="21" viewBox="0 0 24 24" fill="#17345f"><path d="M6.6 10.8c1.4 2.8 3.8 5.2 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.5.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.2.2 2.4.6 3.5.1.4 0 .8-.2 1z"/></svg></a>
</div>`

/* ── 頁尾：品牌 + 回賣場 CTA + 信賴條 + 聯絡三欄 ── */
const FOOTER = `<footer class="gg-foot">
  <div class="gg-top">
    <div class="gg-brand">${LOGO}<div><b>果果國際 GUOGUO</b><small>台灣專業 Apple 福利機供應商</small></div></div>
    <a class="gg-shop" href="${C.shop}" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24"><path d="M3 4h2l2.3 11.4a1.6 1.6 0 0 0 1.6 1.3h8.3a1.6 1.6 0 0 0 1.6-1.3L20.5 7H6.2"/><circle cx="9.5" cy="20" r="1.2"/><circle cx="17.5" cy="20" r="1.2"/></svg>回果果賣場逛逛
    </a>
  </div>
  <div class="gg-trust"><span><b>40</b> 道專業檢測</span><span>資訊透明・缺點揭露</span><span>最長 <b>1 年</b> 保固</span><span>買機 <b>教你用</b>・終身售後</span></div>
  <div class="gg-cols">
    <div class="gg-col"><h5>聯絡我們</h5>
      <a href="${C.line}" target="_blank" rel="noopener">${I.chat} LINE ${C.lineId}</a>
      <a href="tel:${C.tel.replace(/-/g,'')}">${I.phone} ${C.tel}</a>
      <a href="mailto:${C.email}">${I.mail} ${C.email}</a>
    </div>
    <div class="gg-col"><h5>門市・時間</h5>
      <a href="${C.map}" target="_blank" rel="noopener">${I.pin} 台北文山・景興路23巷6弄11號4樓</a>
      <span class="gg-line2">${I.clock} 客服時間 ${C.hours}</span>
    </div>
    <div class="gg-col"><h5>更多</h5>
      <a href="${C.stock}" target="_blank" rel="noopener">${I.box} 查即時庫存</a>
      <a href="${C.fb}" target="_blank" rel="noopener">${I.fb} Facebook 粉專</a>
    </div>
  </div>
  <div class="gg-copy"><span>© 果果國際 GUOGUO INTERNATIONAL</span><span>讓消費者安心網購二手 3C，是我們的使命</span></div>
</footer>`
