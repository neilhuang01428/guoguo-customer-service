#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
# build-products.py — 把後台匯出的 CSV 轉成給導購版位用的 products.json
#   來源：data/products-export.csv（gitignored，內部檔）
#   產出：products.json（給 Worker 抓、組成商品卡；只在導外版出現）
#   用法：python3 build-products.py   （商品更新後重跑一次即可）
#
#   Worker 抓這支產出的 products.json + 一份 guide-map.json（文章→商品id），
#   在文章結尾注入商品卡。破百篇也只是 JSON 多幾列，Worker 不用改。
# ─────────────────────────────────────────────────────────────
import csv, json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "products-export.csv")
OUT = os.path.join(ROOT, "products.json")


def norm(s):
    return (s or "").lower().replace("_", "-").replace(" ", "-").strip()


def to_int(s):
    s = (s or "").strip().replace(",", "")
    try:
        return int(float(s)) if s else None
    except ValueError:
        return None


with open(SRC, encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

cols = list(rows[0].keys()) if rows else []
col = {norm(c): c for c in cols}


def g(r, key):
    return (r.get(col.get(key, ""), "") or "").strip()


products = []
for r in rows:
    if norm(g(r, "field-type")) != "product":
        continue
    if g(r, "status").upper() != "ACTIVE":          # 只收上架中
        continue
    img = g(r, "product-image-url").split(";")[0].strip()  # 欄位含多張圖，取第一張
    if not img:                                      # 沒圖沒法做卡片
        continue
    products.append({
        "id":              g(r, "url-handle"),        # 穩定 id，給 map 對應
        "title":           g(r, "title"),
        "image":           img,
        "url":             g(r, "full-seo-url"),      # 賣場商品連結（導購目的地）
        "price":           to_int(g(r, "price")),
        "compare_at_price": to_int(g(r, "compare-at-price")),  # 原價（可算折扣）
        "category":        g(r, "category"),          # 可用來配對文章
        "inventory":       g(r, "inventory"),
    })

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=1)

print("✅ 產生 %s：%d 個商品（field-type=product、ACTIVE、有圖）" % (OUT, len(products)))
