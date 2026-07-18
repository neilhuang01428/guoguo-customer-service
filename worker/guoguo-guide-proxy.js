/* ══════════════════════════════════════════════════════════════════
   果果 GUIDE · Cloudflare Worker
   反向代理 GitHub Pages → www.guoguo.tw/guide/
   ＋ .html 容錯（有無 .html 都能開）
   ＋ 導外版共用 chrome 注入（footer / 浮動鈕 / 聯絡）

   ▸ 部署：Cloudflare 後台 → Workers & Pages → 貼上此檔 → Deploy
   ▸ Route：*guoguo.tw/guide/*  和  guoguo.tw/guide/*
   ▸ 改「chrome」= 改這一支 = 全站導外版一起變（免 rebuild）
   ▸ 無導外版走中性網域、不經這支 Worker，所以天生沒有導外資訊
   ══════════════════════════════════════════════════════════════════ */

const ORIGIN = 'https://neilhuang01428.github.io/guoguo-customer-service'

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

  // 只接管 /guide 與 /guide/*；其餘放行給 SaaS 官網
  if (p !== '/guide' && !p.startsWith('/guide/')) return fetch(request)

  // /guide 沒斜線 → 補斜線
  if (p === '/guide') return Response.redirect(url.origin + '/guide/', 301)

  let sub = p.slice(6)                 // 去掉 '/guide'（6 個字）
  if (sub === '' || sub === '/') sub = '/index.html'

  const res = await fetchWithFallback(sub)

  // 只對 HTML 頁面注入 chrome（css/圖/xml 原樣回）
  const ct = res.headers.get('content-type') || ''
  if (!ct.includes('text/html')) return res

  return new HTMLRewriter()
    .on('head', { element(el) { el.append(CHROME_CSS, { html: true }) } })
    // footer 注入到 <main> 內（避免動到 body 的 flex 版面）；順便放回頂錨點
    .on('main', {
      element(el) {
        el.prepend('<span id="gg-top"></span>', { html: true })
        el.append(FOOTER, { html: true })
      }
    })
    // 浮動鈕 fixed 定位，append 到 body 不影響 flex
    .on('body', { element(el) { el.append(FLOATING, { html: true }) } })
    .transform(res)
}

/* ── .html 容錯：依序試多種可能路徑 ──────────────────────────── */
async function fetchWithFallback(sub) {
  const hasExt = /\.[a-z0-9]+$/i.test(sub)
  let tries
  if (hasExt) {
    tries = [sub]                                       // 已含副檔名（含現有 4 篇）
  } else if (sub.endsWith('/')) {
    const base = sub.slice(0, -1)
    const seg = base.split('/').filter(Boolean).pop() || 'index'
    tries = [sub + 'index.html', base + '/' + seg + '.html'] // 新式 slug/ 或 舊式 資料夾/同名.html
  } else {
    const seg = sub.split('/').filter(Boolean).pop()
    tries = [sub, sub + '.html', sub + '/index.html', sub + '/' + seg + '.html']
  }
  for (const t of tries) {
    const r = await fetch(ORIGIN + t)
    if (r.ok) return r
  }
  return fetch(ORIGIN + tries[0])                        // 都失敗 → 回第一個讓它 404
}

/* ── 共用 chrome：CSS（用 style.css 已定義的設計 tokens）────────── */
const CHROME_CSS = `<style>
/* 果果 GUIDE 導外版共用 chrome（Worker 注入） */
.gg-fab{position:fixed;right:16px;bottom:20px;display:flex;flex-direction:column;gap:12px;z-index:60}
.gg-fab a{width:52px;height:52px;border-radius:50%;background:#fff;box-shadow:0 4px 14px rgba(20,39,68,.22);display:grid;place-items:center;font-size:1.35rem;text-decoration:none;border:1px solid var(--line,#e2e8f0);transition:.15s;color:var(--navy,#17345f)}
.gg-fab a:hover{transform:translateY(-2px);box-shadow:0 9px 22px rgba(20,39,68,.28)}
.gg-fab a.gg-line{background:#06C755;border-color:#06C755}
.gg-foot{margin:56px 0 0;background:var(--navy-bg,#eef2f8);border:1px solid #dfe7f2;border-radius:16px;padding:24px 26px;font-family:var(--sans,'Noto Sans TC',sans-serif)}
.gg-foot .gg-cta{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding-bottom:16px;border-bottom:1px solid #dfe7f2}
.gg-foot .gg-cta b{display:block;color:var(--navy,#17345f);font-size:1.05rem;font-weight:800}
.gg-foot .gg-cta small{color:var(--body,#45506a);font-size:.84rem}
.gg-foot a.gg-shop{background:var(--navy,#17345f);color:#fff;text-decoration:none;font-weight:800;font-size:.95rem;padding:12px 22px;border-radius:10px;white-space:nowrap}
.gg-foot a.gg-shop:hover{background:var(--navy-deep,#0f2547)}
.gg-foot .gg-links{display:flex;flex-wrap:wrap;gap:10px 18px;margin:16px 0 12px}
.gg-foot .gg-links a{color:var(--navy,#17345f);text-decoration:none;font-size:.9rem;font-weight:600;border-bottom:1px dotted #9fb2ce}
.gg-foot .gg-links a:hover{color:var(--green-deep,#237a43)}
.gg-foot .gg-meta{color:var(--muted,#8590a6);font-size:.8rem;line-height:1.7}
@media(max-width:860px){.gg-foot .gg-cta{flex-direction:column;align-items:flex-start}.gg-fab a{width:46px;height:46px;font-size:1.2rem}}
</style>`

/* ── 浮動鈕：回頂 / LINE / Map / 電話（純連結，無 JS 也可點）──── */
const FLOATING = `<div class="gg-fab" aria-label="快速聯絡">
  <a href="#gg-top" title="回到頂端" aria-label="回到頂端">↑</a>
  <a class="gg-line" href="${C.line}" target="_blank" rel="noopener" title="官方 LINE ${C.lineId}" aria-label="官方 LINE">💬</a>
  <a href="${C.map}" target="_blank" rel="noopener" title="門市地圖" aria-label="門市 Google 地圖">📍</a>
  <a href="tel:${C.tel.replace(/-/g,'')}" title="客服電話 ${C.tel}" aria-label="打電話給客服">📞</a>
</div>`

/* ── 頁尾：回賣場 CTA ＋ 聯絡資訊 ────────────────────────────── */
const FOOTER = `<footer class="gg-foot">
  <div class="gg-cta">
    <div><b>想找 iPad？回果果賣場逛逛</b><small>40 道專業檢測・資訊透明・缺點揭露・最長一年保固</small></div>
    <a class="gg-shop" href="${C.shop}" target="_blank" rel="noopener">🛒 回果果賣場</a>
  </div>
  <div class="gg-links">
    <a href="${C.line}" target="_blank" rel="noopener">💬 LINE ${C.lineId}</a>
    <a href="tel:${C.tel.replace(/-/g,'')}">📞 ${C.tel}</a>
    <a href="mailto:${C.email}">✉ ${C.email}</a>
    <a href="${C.map}" target="_blank" rel="noopener">📍 台北文山門市</a>
    <a href="${C.stock}" target="_blank" rel="noopener">📦 查即時庫存</a>
    <a href="${C.fb}" target="_blank" rel="noopener">Facebook 粉專</a>
  </div>
  <div class="gg-meta">客服時間 ${C.hours}｜地址：${C.addr}<br>© 果果國際 GUOGUO INTERNATIONAL</div>
</footer>`
