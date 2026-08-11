import os
import json
import hashlib
import requests
import feedparser
from google import genai

# =========================================================
# ASO NEWS — Multi Source Auto Publisher
# BBC + Rudaw + Kurdistan24
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"

HISTORY_FILE = "posted_news.json"

RSS_SOURCES = [
    {
        "name": "BBC News",
        "url": "https://feeds.bbci.co.uk/news/rss.xml"
    },
    {
        "name": "Rudaw",
        "url": "https://news.google.com/rss/search?q=site%3Arudaw.net+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"
    },
    {
        "name": "Kurdistan24",
        "url": "https://news.google.com/rss/search?q=site%3Akurdistan24.net+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"
    }
]

client = genai.Client(api_key=GEMINI_API_KEY)


# =========================================================
# Read history
# =========================================================

if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            posted_news = json.load(f)

        if not isinstance(posted_news, list):
            posted_news = []

    except Exception:
        posted_news = []
else:
    posted_news = []


# =========================================================
# Collect news from all sources
# =========================================================

all_news = []

for source in RSS_SOURCES:

    print("\n" + "=" * 60)
    print(f"🔎 سەرچاوە: {source['name']}")
    print("=" * 60)

    try:
        feed = feedparser.parse(source["url"])

        print(f"📰 {len(feed.entries)} هەواڵ دۆزرایەوە")

        for item in feed.entries:

            title = item.get("title", "").strip()
            summary = item.get("summary", "").strip()
            link = item.get("link", "").strip()

            if not title:
                continue

            unique_text = link if link else title

            news_id = hashlib.sha256(
                unique_text.encode("utf-8")
            ).hexdigest()

            if news_id in posted_news:
                continue

            all_news.append({
                "id": news_id,
                "source": source["name"],
                "title": title,
                "summary": summary,
                "link": link
            })

    except Exception as e:
        print(f"⚠️ کێشە لە {source['name']}: {e}")


# =========================================================
# No new news
# =========================================================

if not all_news:
    print("\nℹ️ هیچ هەواڵێکی نوێ نەدۆزرایەوە.")
    exit()


print("\n" + "=" * 60)
print(f"✅ کۆی هەواڵە نوێکان: {len(all_news)}")
print("=" * 60)


# =========================================================
# Take the newest few candidates
# =========================================================

candidates = all_news[:10]


# =========================================================
# Ask Gemini to select ONE important news
# =========================================================

news_text = ""

for i, item in enumerate(candidates, start=1):

    news_text += f"""
[{i}]
سەرچاوە: {item['source']}
سەردێڕ: {item['title']}
پوختە: {item['summary']}
لینک: {item['link']}
"""


prompt = f"""
تۆ دەستکارێکی هەواڵی پیشەیی بۆ ASO NEWS ـیت.

لە نێوان هەواڵەکانی خوارەوە تەنها یەک هەواڵ هەڵبژێرە کە
گرنگترین و گونجاوترین هەواڵە بۆ پەیجی هەواڵیی ASO NEWS.

پێش هەموو شتێک:
- هەواڵی ڕووداوێکی گرنگ هەڵبژێرە.
- هەواڵی بێ گرنگی و تەنها کۆمەڵایەتی مەهێنە.
- هیچ زانیارییەکی خۆت زیاد مەکە.
- ژمارەکان مەگۆڕە.
- ناوی کەس و شوێن مەگۆڕە.
- شیکاری سیاسی مەکە.
- تەنها ئەو زانیارییە بەکاربهێنە کە لە سەرچاوەکەدا هەیە.
- ئەگەر هەواڵەکان لەسەر هەمان ڕووداون، تەنها یەکێکیان هەڵبژێرە.

هەواڵەکان:

{news_text}

لە وەڵامدا تەنها ئەم فۆرماتە بەکاربهێنە:

SOURCE_NUMBER: ژمارەی هەواڵ

📰 سەردێڕ

دەقی هەواڵ

#ASONEWS #هاشتاگ #هاشتاگ

سەرچاوە: ناوی سەرچاوە
"""


response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents=prompt
)

result = response.text.strip()

print("\n" + "=" * 60)
print("🤖 GEMINI")
print("=" * 60)
print(result)


# =========================================================
# Find selected source
# =========================================================

selected_index = None

for line in result.splitlines():

    line = line.strip()

    if line.startswith("SOURCE_NUMBER:"):

        try:
            selected_index = int(
                line.split(":", 1)[1].strip()
            )
        except ValueError:
            selected_index = None

        break


if selected_index is None:
    print("❌ Gemini نەیتوانی هەواڵەکە هەڵبژێرێت.")
    exit()


if selected_index < 1 or selected_index > len(candidates):
    print("❌ ژمارەی هەڵبژێردراو نادروستە.")
    exit()


selected_news = candidates[selected_index - 1]


# =========================================================
# Clean Gemini output
# =========================================================

post_lines = []

for line in result.splitlines():

    if line.strip().startswith("SOURCE_NUMBER:"):
        continue

    post_lines.append(line)

post = "\n".join(post_lines).strip()


# =========================================================
# Show final post
# =========================================================

print("\n" + "=" * 60)
print("📰 ASO NEWS — پۆستی کۆتایی")
print("=" * 60)
print(post)
print("=" * 60)

print(f"📌 سەرچاوە: {selected_news['source']}")
print(f"🔗 {selected_news['link']}")


# =========================================================
# Publish to Facebook
# =========================================================

facebook_url = f"https://graph.facebook.com/{PAGE_ID}/feed"

facebook_response = requests.post(
    facebook_url,
    data={
        "message": post,
        "access_token": FACEBOOK_PAGE_ACCESS_TOKEN
    },
    timeout=30
)


print("\n" + "=" * 60)
print("📘 FACEBOOK")
print("=" * 60)
print("Status:", facebook_response.status_code)
print(facebook_response.text)


# =========================================================
# Save only after successful Facebook post
# =========================================================

if facebook_response.status_code == 200:

    posted_news.append(selected_news["id"])

    # Keep latest 500 IDs
    posted_news = posted_news[-500:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:

        json.dump(
            posted_news,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("\n✅ پۆستەکە بە سەرکەوتوویی بڵاوکرایەوە.")
    print("🔐 هەواڵەکە وەک پۆستکراو تۆمار کرا.")

else:

    print("\n❌ Facebook پۆستەکەی قبوڵ نەکرد.")
    print("⚠️ هەواڵەکە وەک پۆستکراو تۆمار نەکرا.")
