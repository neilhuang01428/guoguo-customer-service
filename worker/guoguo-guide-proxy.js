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

  const res = await fetchWithFallback(sub)
  const ct = res.headers.get('content-type') || ''
  if (!ct.includes('text/html')) return res                                   // 非 HTML 原樣回

  return new HTMLRewriter()
    .on('head', { element(el) { el.prepend(ANALYTICS, { html: true }); el.append(CHROME_CSS, { html: true }) } })
    .on('main', {
      element(el) {
        el.prepend('<span id="gg-top"></span>' + TOPBAR, { html: true })       // 頂部回賣場麵包屑
        el.append(FOOTER, { html: true })                                       // 頁尾
      }
    })
    .on('body', { element(el) { el.append(FLOATING, { html: true }) } })        // 右下浮動鈕（fixed）
    .transform(res)
}

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
/* ── 頂部麵包屑：果果賣場 › iPad 使用教學 › 本篇（用 div，避免吃到側欄 nav 樣式）── */
.gg-crumb{display:flex;align-items:center;flex-wrap:wrap;gap:3px 5px;font-family:var(--sans);font-size:.82rem;color:var(--muted,#8590a6);padding:12px 0 13px;margin:0 0 2px;border-bottom:1px solid var(--line,#e2e8f0)}
.gg-crumb a.gg-cr{display:inline-flex;align-items:center;gap:6px;color:var(--navy,#17345f);text-decoration:none;font-weight:700;padding:4px 10px;border-radius:8px;transition:.14s}
.gg-crumb a.gg-cr:hover{background:#eef2f8;color:var(--navy-deep,#0f2547)}
.gg-crumb a.gg-cr svg{width:15px;height:15px;flex:none;stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
.gg-crumb .gg-sep{color:#c3ccda;font-size:.92rem;line-height:1}
.gg-crumb .gg-cur{color:var(--body,#45506a);font-weight:600;padding:0 4px}

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
