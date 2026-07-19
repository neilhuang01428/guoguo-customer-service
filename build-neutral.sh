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

# 1) allowlist：只複製「乾淨內容」——絕不含 worker/(有全部聯絡資料)、sitemap.xml(有 guoguo 網址)、內部文件
#    首頁 index.html 不在這裡：F 方案首頁含常駐商品側欄，商品卡連結 www.guoguo.tw/product/…、
#    CTA 連回 www.guoguo.tw/shop——本來就是導購頁，不該放上「零導外」的中性網域（蝦皮買家用）。
#    蝦皮/中性網域只給單篇文章教學，首頁導覽留在 www.guoguo.tw/guide/ 正式站即可。
cp -R assets "$OUT"/
for d in ipad-appstore-china-guide ipad-jailbreak-guide ipad-jianying-pencil-guide ipad-magic-keyboard-guide; do
  cp -R "$d" "$OUT"/
done

# 2) noindex 整個中性網域（與導外版 www.guoguo.tw/guide 同內容，避免 Google 重複內容懲罰）
printf 'User-agent: *\nDisallow: /\n' > "$OUT"/robots.txt

# 3) 洩漏檢查守門：dist/ 內若出現任何「果果導流資訊」就中止部署
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
