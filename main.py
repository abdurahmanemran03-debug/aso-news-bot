import os
import requests
import feedparser
from google import genai

# ==============================
# ASO NEWS
# RSS → Gemini → Facebook
# ==============================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"

RSS_URL = "https://feeds.bbci.co.uk/news/rss.xml"

client = genai.Client(api_key=GEMINI_API_KEY)


# ==============================
# Get news
# ==============================

feed = feedparser.parse(RSS_URL)

if not feed.entries:
    print("❌ هیچ هەواڵێک نەدۆزرایەوە")
    exit()

news = feed.entries[0]

title = news.get("title", "")
summary = news.get("summary", "")

print("📰 هەواڵ دۆزرایەوە:")
print(title)


# ==============================
# Gemini
# ==============================

prompt = f"""
تۆ دەستکارێکی هەواڵی پیشەیی بۆ ASO NEWS ـیت.

ئەم هەواڵە بە کوردی سۆرانییەکی ڕوون و پیشەیی بنووسە.

یاساکانی گرنگ:
- هیچ زانیارییەکی نوێ زیاد مەکە.
- ژمارەکان مەگۆڕە.
- ناوی کەس مەگۆڕە.
- ناوی شار و وڵات مەگۆڕە.
- ڕووداوەکە مەگۆڕە.
- شیکاری سیاسی مەکە.
- تەنها زانیاریی سەرچاوە بەکاربهێنە.

سەردێڕ:
{title}

پوختە:
{summary}

تەنها ئەم فۆرماتە بەکاربهێنە:

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

print("\n" + "=" * 60)
print("📰 ASO NEWS — پۆستی ئامادەکراو")
print("=" * 60)
print(post)


# ==============================
# Facebook
# ==============================

url = f"https://graph.facebook.com/{PAGE_ID}/feed"

facebook_response = requests.post(
    url,
    data={
        "message": post,
        "access_token": FACEBOOK_PAGE_ACCESS_TOKEN
    }
)

print("\n" + "=" * 60)
print("📘 FACEBOOK")
print("=" * 60)
print("Status:", facebook_response.status_code)
print(facebook_response.text)

if facebook_response.status_code == 200:
    print("✅ پۆستەکە بە سەرکەوتوویی بڵاوکرایەوە.")
else:
    print("❌ هەڵە لە Facebook ڕوویدا.")
