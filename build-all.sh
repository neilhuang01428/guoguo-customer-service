#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# build-all.sh — 一鍵 build + verify：push 前的本機自檢
#   把散落的建置腳本串成一支，依序跑完並自檢，不用再靠記憶。
#
#   步驟（依序，任一步失敗即中止 — set -e）：
#     1) build-products.py  — 只有 data/products-export.csv 存在才跑
#                             （CSV 是 gitignored 內部檔，可能不存在 → 略過）
#     2) build-homepage.py  — articles.json → index.html（導外版）＋ index.neutral.html（中性版）
#     3) build-sitemap.py   — articles.json → sitemap.xml（導外版）
#     4) build-neutral.sh   — 產 dist/（allowlist＋麵包屑/標籤注入＋noindex＋洩漏檢查守門）
#
#   用法：
#     bash build-all.sh          只建置＋自檢，不起預覽 server
#     bash build-all.sh serve    建置後起本機預覽（http://127.0.0.1:8899，服務 dist/）
#
#   可重複執行（idempotent）：各腳本皆為覆寫/重生，dist/ 每次砍掉重建。
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

echo "▸ [1/4] build-products"
if [ -f data/products-export.csv ]; then
  python3 build-products.py
  echo "  ✅ products.json 已更新"
else
  echo "  （略過：無 products-export.csv）"
fi

echo "▸ [2/4] build-homepage（index.html ＋ index.neutral.html）"
python3 build-homepage.py
echo "  ✅ 首頁已重生"

echo "▸ [3/4] build-sitemap（sitemap.xml）"
python3 build-sitemap.py
echo "  ✅ sitemap.xml 已更新"

echo "▸ [4/4] build-neutral（dist/ ＋ 洩漏檢查守門）"
bash build-neutral.sh
echo "  ✅ dist/ 已建置"

echo ""
echo "✅ 全部建置完成"

if [ "${1:-}" = "serve" ]; then
  echo "▸ 起本機預覽：http://127.0.0.1:8899 （服務 dist/，Ctrl-C 結束）"
  python3 -m http.server 8899 --bind 127.0.0.1 -d dist
else
  echo "預覽：bash build-all.sh serve（或 python3 -m http.server 8899 -d dist）"
fi
