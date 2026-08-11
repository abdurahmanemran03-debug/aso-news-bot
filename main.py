import os
import json
import hashlib
import requests
import feedparser
from google import genai

# =========================================================
# ASO NEWS — Auto Publisher
# RSS → Gemini → Duplicate Check → Facebook
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"
RSS_URL = "https://feeds.bbci.co.uk/news/rss.xml"

HISTORY_FILE = "posted_news.json"

client = genai.Client(api_key=GEMINI_API_KEY)


# =========================================================
# Read previously posted news
# =========================================================

if os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            posted_news = json.load(f)
    except Exception:
        posted_news = []
else:
    posted_news = []


# =========================================================
# Get RSS news
# =========================================================

feed = feedparser.parse(RSS_URL)

if not feed.entries:
    print("❌ هیچ هەواڵێک نەدۆزرایەوە")
    exit()

print(f"📰 {len(feed.entries)} هەواڵ دۆزرایەوە")


# =========================================================
# Find a NEW news item
# =========================================================

selected_news = None
selected_id = None

for news in feed.entries:

    title = news.get("title", "").strip()
    link = news.get("link", "").strip()

    if not title:
        continue

    # Use RSS link as unique ID
    unique_text = link if link else title

    news_id = hashlib.sha256(
        unique_text.encode("utf-8")
    ).hexdigest()

    if news_id not in posted_news:
        selected_news = news
        selected_id = news_id
        break


# =========================================================
# No new news
# =========================================================

if selected_news is None:
    print("ℹ️ هیچ هەواڵێکی نوێ نییە.")
    exit()


title = selected_news.get("title", "")
summary = selected_news.get("summary", "")
link = selected_news.get("link", "")

print("\n✅ هەواڵی نوێ دۆزرایەوە:")
print(title)


# =========================================================
# Gemini
# =========================================================

prompt = f"""
تۆ دەستکارێکی هەواڵی پیشەیی بۆ پەیجی ASO NEWS ـیت.

ئەم هەواڵە بە کوردی سۆرانییەکی ڕوون و پیشەیی بنووسە.

یاساکانی زۆر گرنگ:

- هیچ زانیارییەکی نوێ زیاد مەکە.
- ژمارەکان مەگۆڕە.
- ناوی کەس مەگۆڕە.
- ناوی شار و وڵات مەگۆڕە.
- ڕێکەوت مەگۆڕە.
- ڕووداوەکە مەگۆڕە.
- شیکاری سیاسی مەکە.
- تەنها زانیارییەکانی سەرچاوە بەکاربهێنە.
- هەواڵەکە کورت و ڕوون بێت.
- سەردێڕێکی ڕوون بنووسە.

سەردێڕی سەرچاوە:
{title}

پوختەی سەرچاوە:
{summary}

فۆرماتی کۆتایی:

📰 سەردێڕ

دەقی هەواڵ

#ASONEWS #هاشتاگ #هاشتاگ

سەرچاوە: BBC News
"""


response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents=prompt
)

post = response.text.strip()


# =========================================================
# Show final post
# =========================================================

print("\n" + "=" * 60)
print("📰 ASO NEWS — پۆستی نوێ")
print("=" * 60)
print(post)
print("=" * 60)


# =========================================================
# Publish to Facebook
# =========================================================

facebook_url = f"https://graph.facebook.com/{PAGE_ID}/feed"

facebook_response = requests.post(
    facebook_url,
    data={
        "message": post,
        "access_token": FACEBOOK_PAGE_ACCESS_TOKEN
    }
)

print("\n📘 FACEBOOK")
print("Status:", facebook_response.status_code)
print(facebook_response.text)


# =========================================================
# Save news as posted ONLY after successful Facebook post
# =========================================================

if facebook_response.status_code == 200:

    posted_news.append(selected_id)

    # Keep only the latest 500 news IDs
    posted_news = posted_news[-500:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            posted_news,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("\n✅ پۆستەکە بڵاوکرایەوە.")
    print("🔐 هەمان هەواڵ لە داهاتوودا دووبارە بڵاوناکرێتەوە.")

else:

    print("\n❌ پۆستکردن لە Facebook سەرکەوتوو نەبوو.")
    print("⚠️ هەواڵەکە لە لیستی پۆستکراوەکان تۆمار نەکرا.")
