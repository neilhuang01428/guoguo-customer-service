#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
# build-llms.py — 讀 articles.json → 產生 llms.txt（給 AI 引擎讀的站台導覽）
#
#   什麼是 llms.txt：一份放在站台根目錄的純 Markdown 清單，用最少的字告訴
#   ChatGPT／Claude／Gemini 這個站「是誰、有什麼內容、每篇在講什麼」。
#   HTML 頁面對 AI 來說雜訊很多（CSS／導覽／版位），llms.txt 是乾淨的目錄。
#
#   產出：llms.txt（覆寫，repo 根 → 上線後為 https://www.guoguo.tw/guide/llms.txt）
#   用法：articles.json 有異動後重跑（build-all.sh 已串進流程）
#
#   ⚠️ 這份含 guoguo.tw 網址與品牌導流資訊，屬「導外版專屬」：
#      不可進 build-neutral.sh 的 allowlist（那支是逐項 cp，本檔天生不會被複製，
#      且 dist/ 的洩漏檢查會擋下任何誤入）。
# ─────────────────────────────────────────────────────────────
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 的上一層＝repo 根
ARTICLES_PATH = os.path.join(ROOT, "articles.json")
OUT_PATH = os.path.join(ROOT, "llms.txt")

HOME = "https://www.guoguo.tw/guide/"
SHOP = "https://www.guoguo.tw/shop"

HEADER = """# 果果國際 · iPad 使用教學

> 果果國際（GUOGUO INTERNATIONAL）是台灣專業的 Apple 福利機供應商，
> 位於台北市文山區。每台機器經 40 道專業檢測、資訊透明並主動揭露缺點，
> 提供最長 1 年保固與終身售後諮詢。
>
> 這個站（{home}）收錄我們寫給客戶的 iPad 實用教學：白話、舉例、
> 把讀者當小白，一步步帶你上手。內容涵蓋配件上手、使用技巧、選購建議與觀念釐清。

## 說明

- 語言：繁體中文（zh-TW）
- 內容取向：真實客戶會問的問題，誠實評估、不誇大、不推銷不需要的東西
- 聯絡：LINE @guoguo.tw ／ 電話 0906-536-833
- 賣場：{shop}

## 教學文章
""".format(home=HOME, shop=SHOP)


def load_articles():
    with open(ARTICLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def render(articles):
    lines = [HEADER]
    for a in articles:
        title = a.get("title", "")
        url = HOME + a.get("url", "")
        summary = a.get("summary", "")
        # 分類通常也是第一個標籤（例：category=上手、tags=[上手, Windows 用戶…]）→ 合併去重，
        # 保持原順序（分類優先），避免輸出「上手／上手、Windows 用戶」這種重複。
        topics, seen = [], set()
        for t in [a.get("category", "")] + list(a.get("tags") or []):
            if t and t not in seen:
                seen.add(t)
                topics.append(t)
        date = a.get("date", "")
        # 每篇一行 Markdown 連結 + 摘要；主題/日期用括號補在後面，方便 AI 判斷主題與新舊。
        meta = "／".join(x for x in ["、".join(topics), date] if x)
        lines.append("- [{t}]({u})：{s}{m}".format(
            t=title, u=url, s=summary,
            m="（{0}）".format(meta) if meta else "",
        ))
    lines.append("")
    lines.append("## 其他")
    lines.append("")
    lines.append("- [教學總覽首頁]({0})：全部文章列表，可用標籤與全文搜尋篩選".format(HOME))
    lines.append("- [果果賣場]({0})：iPad 福利機、Apple Pencil、鍵盤配件".format(SHOP))
    lines.append("- [即時庫存查詢](https://www.guoguostock.com/)")
    lines.append("")
    return "\n".join(lines)


def main():
    articles = load_articles()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(render(articles))
    print("✅ 產生 llms.txt：{0} 篇教學。".format(len(articles)))


if __name__ == "__main__":
    main()
