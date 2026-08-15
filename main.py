import os
import json
import hashlib
import re
import html
from urllib.parse import urljoin
from datetime import datetime, timezone

import requests
import feedparser
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from google import genai


# =========================================================
# ASO NEWS — AUTO PUBLISHER
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"

HISTORY_FILE = "posted_news.json"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

MAX_HISTORY = 1000
MAX_CANDIDATES = 12

# The ASO NEWS watermark file in GitHub.
LOGO_FILE = "logo.png"

FACEBOOK_PHOTO_URL = f"https://graph.facebook.com/{PAGE_ID}/photos"
FACEBOOK_VIDEO_URL = f"https://graph.facebook.com/{PAGE_ID}/videos"


# =========================================================
# NEWS SOURCES
# =========================================================
# ASO NEWS priority:
# 1) Kurdistan
# 2) Iraq
# 3) Middle East / World
#
# We use Google News RSS with site: filters for sources that do not
# provide a stable public RSS feed. This also keeps the source name
# attached to each article.
# =========================================================

RSS_SOURCES = [
    # -----------------------------------------------------
    # 🇹🇯 KURDISTAN — HIGHEST PRIORITY
    # -----------------------------------------------------
    {
        "name": "Rudaw",
        "region": "kurdistan",
        "priority": 100,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Arudaw.net+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Kurdistan24",
        "region": "kurdistan",
        "priority": 100,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Akurdistan24.net+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "NRT",
        "region": "kurdistan",
        "priority": 98,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Anrt-news.com+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "BasNews",
        "region": "kurdistan",
        "priority": 98,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Abasnews.com+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Xendan",
        "region": "kurdistan",
        "priority": 96,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Axendan.org+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "PUKmedia",
        "region": "kurdistan",
        "priority": 94,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Apukmedia.com+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Shafaq News",
        "region": "kurdistan",
        "priority": 92,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Ashafaq.com+Kurdistan+OR+Iraq+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },

    # -----------------------------------------------------
    # 🇮🇶 IRAQ — SECOND PRIORITY
    # -----------------------------------------------------
    {
        "name": "Alsumaria News",
        "region": "iraq",
        "priority": 82,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Aalsumaria.tv+Iraq+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Iraqi News",
        "region": "iraq",
        "priority": 78,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Airaqinews.com+Iraq+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Iraq News",
        "region": "iraq",
        "priority": 76,
        "url": (
            "https://news.google.com/rss/search?"
            "q=Iraq+latest+news+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },

    # -----------------------------------------------------
    # 🌍 INTERNATIONAL — LOWER PRIORITY
    # -----------------------------------------------------
    {
        "name": "Reuters",
        "region": "world",
        "priority": 48,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Areuters.com+Iraq+OR+Middle+East+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Associated Press",
        "region": "world",
        "priority": 45,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Aapnews.com+Iraq+OR+Middle+East+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Al Jazeera",
        "region": "world",
        "priority": 43,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Aaljazeera.com+Iraq+OR+Kurdistan+OR+Middle+East+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "BBC News",
        "region": "world",
        "priority": 35,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Abbc.com+Iraq+OR+Kurdistan+OR+Middle+East+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "DW",
        "region": "world",
        "priority": 32,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Adw.com+Iraq+OR+Kurdistan+OR+Middle+East+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "France 24",
        "region": "world",
        "priority": 30,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Afrance24.com+Iraq+OR+Kurdistan+OR+Middle+East+when%3A2d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
]


# =========================================================
# HTTP + GEMINI
# =========================================================

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
    )
})

client = genai.Client(api_key=GEMINI_API_KEY)


# =========================================================
# HISTORY
# =========================================================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, list) else []

    except Exception as e:
        print(f"⚠️ کێشە لە history: {e}")
        return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            history[-MAX_HISTORY:],
            f,
            ensure_ascii=False,
            indent=2
        )


posted_news = load_history()


# =========================================================
# TEXT + IDS
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def create_news_id(title, link):
    title = re.sub(r"\s+", " ", title.lower().strip())
    base = link.strip() if link.strip() else title

    return hashlib.sha256(
        f"{base}|{title}".encode("utf-8")
    ).hexdigest()


def entry_date(entry):
    try:
        if entry.get("published_parsed"):
            return datetime(
                *entry.published_parsed[:6],
                tzinfo=timezone.utc
            )

        if entry.get("updated_parsed"):
            return datetime(
                *entry.updated_parsed[:6],
                tzinfo=timezone.utc
            )
    except Exception:
        pass

    return datetime(1970, 1, 1, tzinfo=timezone.utc)


# =========================================================
# MEDIA URLS
# =========================================================

def get_rss_image(entry):
    for media in entry.get("media_content", []):
        if media.get("url"):
            return media["url"]

    for media in entry.get("media_thumbnail", []):
        if media.get("url"):
            return media["url"]

    for enclosure in entry.get("enclosures", []):
        url = enclosure.get("href") or enclosure.get("url")
        if url and "image" in enclosure.get("type", "").lower():
            return url

    raw = (
        entry.get("summary", "")
        + " "
        + entry.get("description", "")
    )

    matches = re.findall(
        r'<img[^>]+src=["\']([^"\']+)',
        raw,
        re.IGNORECASE
    )

    return matches[0] if matches else None


def get_rss_video(entry):
    for enclosure in entry.get("enclosures", []):
        url = enclosure.get("href") or enclosure.get("url")
        media_type = enclosure.get("type", "").lower()

        if url and (
            "video" in media_type
            or url.lower().split("?")[0].endswith(
                (".mp4", ".mov", ".webm", ".m4v")
            )
        ):
            return url

    return None


def get_article_media(article_url):
    if not article_url:
        return [], []

    try:
        response = session.get(
            article_url,
            timeout=25,
            allow_redirects=True
        )

        if response.status_code != 200:
            return [], []

        page = response.text
        images = []
        videos = []

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        ]

        for pattern in patterns:
            for match in re.findall(pattern, page, re.IGNORECASE):
                url = urljoin(
                    response.url,
                    html.unescape(match.strip())
                )

                if url.startswith("http") and url not in images:
                    images.append(url)

        for match in re.findall(
            r'<img[^>]+(?:src|data-src)=["\']([^"\']+)',
            page,
            re.IGNORECASE
        ):
            url = urljoin(
                response.url,
                html.unescape(match.strip())
            )

            if url.startswith("http") and url not in images:
                images.append(url)

        for match in re.findall(
            r'<(?:video|source)[^>]+src=["\']([^"\']+)',
            page,
            re.IGNORECASE
        ):
            url = urljoin(
                response.url,
                html.unescape(match.strip())
            )

            if (
                url.startswith("http")
                and url.lower().split("?")[0].endswith(
                    (".mp4", ".mov", ".webm", ".m4v")
                )
                and url not in videos
            ):
                videos.append(url)

        return images[:20], videos[:10]

    except Exception as e:
        print(f"⚠️ کێشە لە پشکنینی پەڕەی هەواڵ: {e}")
        return [], []


# =========================================================
# IMAGE DOWNLOAD
# =========================================================

def download_best_image(candidates):
    best = None

    for image_url in candidates:
        try:
            print(f"🔎 پشکنینی وێنە: {image_url}")

            response = session.get(
                image_url,
                timeout=25
            )

            if response.status_code != 200:
                continue

            if "image" not in response.headers.get(
                "content-type", ""
            ).lower():
                continue

            data = response.content

            if len(data) < 30000:
                continue

            image = Image.open(BytesIO(data))
            width, height = image.size

            print(f"📐 {width}x{height}")

            if width < 800 or height < 450:
                continue

            score = width * height + len(data) / 100

            if best is None or score > best["score"]:
                best = {
                    "data": data,
                    "score": score,
                    "width": width,
                    "height": height
                }

        except Exception as e:
            print(f"⚠️ نەتوانرا وێنەکە پشکنرێت: {e}")

    if best is None:
        return None

    try:
        image = Image.open(
            BytesIO(best["data"])
        ).convert("RGB")

        image.save(
            "news_image.jpg",
            "JPEG",
            quality=95,
            optimize=True
        )

        return "news_image.jpg"

    except Exception as e:
        print(f"❌ هەڵە لە پاشەکەوتکردنی وێنە: {e}")
        return None


# =========================================================
# FALLBACK IMAGE
# =========================================================

def create_fallback_image(title):
    """دروستکردنی وێنەیەکی fallback ئەگەر هیچ وێنەی سەرچاوەیەک نەدۆزرایەوە."""
    try:
        width, height = 1200, 675
        image = Image.new("RGB", (width, height), (18, 18, 22))
        draw = ImageDraw.Draw(image)
        # Simple red brand bars
        draw.rectangle((0, 0, width, 12), fill=(220, 30, 45))
        draw.rectangle((0, height - 12, width, height), fill=(220, 30, 45))

        font = None
        for path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, 52)
                    break
                except Exception:
                    pass

        if font is None:
            font = ImageFont.load_default()

        draw.text((70, 70), "ASO NEWS", fill=(255, 255, 255), font=font)
        draw.text((70, 145), "KURDISTAN • IRAQ • WORLD", fill=(220, 30, 45), font=font)
        draw.rounded_rectangle((70, 230, width - 70, 500), radius=24, fill=(30, 30, 36), outline=(220, 30, 45), width=3)

        # Keep the title short so long headlines do not break the image.
        title = clean_text(title)[:95]
        draw.text((105, 315), "هەواڵی نوێ", fill=(255, 255, 255), font=font)
        draw.text((105, 400), title or "ASO NEWS", fill=(220, 30, 45), font=font)

        image.save("news_image.jpg", "JPEG", quality=95, optimize=True)
        print("✅ fallback image دروست کرا.")
        return "news_image.jpg"
    except Exception as e:
        print(f"⚠️ fallback image error: {e}")
        return None


# =========================================================
# ASO NEWS WATERMARK
# =========================================================

def add_aso_logo(image_path):
    if not os.path.exists(LOGO_FILE):
        print(
            "⚠️ logo.png نەدۆزرایەوە؛ "
            "پۆستەکە بەبێ watermark دەچێت."
        )
        return image_path

    try:
        base = Image.open(image_path).convert("RGBA")
        logo = Image.open(LOGO_FILE).convert("RGBA")

        target_width = max(
            120,
            int(base.width * 0.16)
        )

        ratio = target_width / logo.width

        logo = logo.resize(
            (
                target_width,
                max(1, int(logo.height * ratio))
            ),
            Image.LANCZOS
        )

        # 92% opacity.
        alpha = logo.getchannel("A")
        alpha = alpha.point(lambda p: int(p * 0.92))
        logo.putalpha(alpha)

        margin = max(
            18,
            int(base.width * 0.025)
        )

        x = base.width - logo.width - margin
        y = base.height - logo.height - margin

        base.alpha_composite(
            logo,
            (x, y)
        )

        base.convert("RGB").save(
            "news_image_branded.jpg",
            "JPEG",
            quality=95,
            optimize=True
        )

        print("✅ لۆگۆی ASO NEWS زیاد کرا.")

        return "news_image_branded.jpg"

    except Exception as e:
        print(f"⚠️ watermark نەکرا: {e}")
        return image_path


# =========================================================
# FIND MEDIA
# =========================================================

def find_media(entry):
    images = []
    videos = []

    image = get_rss_image(entry)
    video = get_rss_video(entry)

    if image:
        images.append(image)

    if video:
        videos.append(video)

    link = entry.get("link", "").strip()

    if link:
        article_images, article_videos = get_article_media(link)
        images.extend(article_images)
        videos.extend(article_videos)

    return (
        list(dict.fromkeys(images)),
        list(dict.fromkeys(videos))
    )


# =========================================================
# NEWS PRIORITY / REGION CLASSIFICATION
# =========================================================

KURDISTAN_KEYWORDS = [
    "kurdistan", "kurdish", "erbil", "erbīl", "irbil",
    "sulaymaniyah", "sulaimani", "slemany", "duhok", "duhok",
    "halabja", "kirkuk", "koysinjaq", "shaqlawa",
    "hewler", "hawler",
    "هەولێر", "هولێر", "سلێمانی", "دهۆک", "دهوک",
    "هەڵەبجە", "کەرکووک", "کرکوک", "کوردستان",
    "پەرلەمانی کوردستان", "حکومەتی هەرێم", "هەرێمی کوردستان",
]

IRAQ_KEYWORDS = [
    "iraq", "iraqi", "baghdad", "basra", "mosul", "najaf",
    "karbala", "anbar", "diyala", "wasit", "maysan",
    "dhi qar", "diwaniyah", "samarra",
    "عێراق", "عراقی", "بغداد", "بەسرە", "بەغدا", "مووسڵ",
    "نجەف", "کەربەلا", "ئەنبار", "دیالە", "واسط", "میسان",
]


def text_contains_keyword(text, keywords):
    text = clean_text(text).lower()
    return any(keyword.lower() in text for keyword in keywords)


def classify_news_region(news):
    text = (
        news.get("title", "")
        + " "
        + news.get("summary", "")
    ).lower()

    if text_contains_keyword(text, KURDISTAN_KEYWORDS):
        return "kurdistan"

    if text_contains_keyword(text, IRAQ_KEYWORDS):
        return "iraq"

    return news.get("region", "world")


def news_priority_score(news):
    source_priority = float(news.get("priority", 0))
    region = classify_news_region(news)

    # Strong editorial preference: Kurdistan > Iraq > World.
    region_bonus = {
        "kurdistan": 60,
        "iraq": 32,
        "world": 0,
    }.get(region, 0)

    age_hours = max(0.0, news.get("age_hours", 48.0))
    if age_hours < 2:
        freshness = 28
    elif age_hours < 6:
        freshness = 22
    elif age_hours < 12:
        freshness = 16
    elif age_hours < 24:
        freshness = 9
    elif age_hours < 48:
        freshness = 3
    else:
        freshness = 0

    important_words = [
        "breaking", "urgent", "attack", "strike", "explosion",
        "drone", "missile", "killed", "war", "election",
        "president", "government", "security", "crisis",
        "هێرش", "تەقینەوە", "درۆن", "مووشەک", "کوژراو",
        "جەنگ", "هەڵبژاردن", "سەرۆک", "حکومەت", "ئاسایش",
        "فۆری", "قەیران",
    ]

    importance = 12 if text_contains_keyword(
        news.get("title", "") + " " + news.get("summary", ""),
        important_words
    ) else 0

    return source_priority + region_bonus + freshness + importance


# =========================================================
# NEWS COLLECTION
# =========================================================

def collect_news():
    all_news = []

    for source in RSS_SOURCES:
        print("\n" + "=" * 60)
        print(f"🔎 سەرچاوە: {source['name']}")
        print("=" * 60)

        try:
            feed = feedparser.parse(source["url"])

            print(
                f"📰 {len(feed.entries)} هەواڵ دۆزرایەوە"
            )

            for item in feed.entries:
                title = clean_text(
                    item.get("title", "")
                )

                summary = clean_text(
                    item.get("summary", "")
                )

                link = item.get(
                    "link",
                    ""
                ).strip()

                if not title:
                    continue

                news_id = create_news_id(
                    title,
                    link
                )

                if any(
                    (item == news_id)
                    or (isinstance(item, dict) and item.get("id") == news_id)
                    for item in posted_news
                ):
                    continue

                published = entry_date(item)
                now = datetime.now(timezone.utc)
                age_hours = (now - published).total_seconds() / 3600

                # Ignore very old Google News results.
                if published.year > 1971 and age_hours > 48:
                    continue

                news = {
                    "id": news_id,
                    "source": source["name"],
                    "region": source.get("region", "world"),
                    "priority": source.get("priority", 0),
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "entry": item,
                    "date": published,
                    "age_hours": age_hours,
                }

                news["region"] = classify_news_region(news)
                news["score"] = news_priority_score(news)
                all_news.append(news)

        except Exception as e:
            print(
                f"⚠️ کێشە لە {source['name']}: {e}"
            )

    all_news.sort(
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    return all_news


# =========================================================
# SOURCE DIVERSITY
# =========================================================

def diverse_candidates(all_news):
    """
    Build a candidate pool that strongly protects ASO NEWS identity:
    Kurdistan first, Iraq second, international third.
    """
    kurdistan = [x for x in all_news if x.get("region") == "kurdistan"]
    iraq = [x for x in all_news if x.get("region") == "iraq"]
    world = [x for x in all_news if x.get("region") == "world"]

    kurdistan.sort(key=lambda x: x.get("score", 0), reverse=True)
    iraq.sort(key=lambda x: x.get("score", 0), reverse=True)
    world.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Target mix: up to 6 Kurdistan + 4 Iraq + 2 world.
    # If one category is empty, its slots are automatically filled by the next.
    selected = []
    selected.extend(kurdistan[:6])
    selected.extend(iraq[:4])
    selected.extend(world[:2])

    used_ids = {x["id"] for x in selected}

    if len(selected) < MAX_CANDIDATES:
        remaining = [
            x for x in all_news
            if x["id"] not in used_ids
        ]
        remaining.sort(
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        selected.extend(remaining[:MAX_CANDIDATES - len(selected)])

    return selected[:MAX_CANDIDATES]


# =========================================================
# GEMINI WRITER
# =========================================================

def generate_news_post(selected_news):
    """
    Gemini only writes the already-selected article.
    Article selection is deterministic: Kurdistan > Iraq > World.
    This prevents Gemini from accidentally choosing an international
    story when a suitable Kurdistan/Iraq story exists.
    """
    prompt = f"""
تۆ دەستکارێکی هەواڵی پیشەیی بۆ ASO NEWS ـیت.

ئەم هەواڵە بۆ بڵاوکردنەوە هەڵبژێردراوە:

سەرچاوە: {selected_news['source']}
ناوچە: {selected_news['region']}
سەردێڕ: {selected_news['title']}
پوختە: {selected_news['summary']}
لینک: {selected_news['link']}

ئەرک:
هەمان هەواڵ بە زمانی کوردی سۆرانییەکی ڕوون و پیشەیی بنووسە.
هیچ زانیارییەکی نوێ لە خۆتەوە زیاد مەکە.
ژمارە، ناو، شوێن و بەروار مەگۆڕە.
شیکاری سیاسی یان پێشبینی مەکە.

پۆستی سەرەکی دەبێت کورت بێت: 2 تا 3 ڕستە.
FULL_BODY دەبێت درێژەی هەمان هەواڵ بێت: 2 تا 4 پاراگرافی کورت.
FULL_BODY نابێت هیچ شتێکی لە سەرچاوەکەدا نییە زیاد بکات.

تەنها ئەم فۆرماتە بەکاربهێنە:

TITLE:
سەردێڕی کوردی

BODY:
2 تا 3 ڕستەی کورت

FULL_BODY:
وردەکارییەکانی هەمان هەواڵ لە 2 تا 4 پاراگرافی کورت

HASHTAGS:
#ASONEWS #هەواڵ #کوردستان

SOURCE:
{selected_news['source']}

هیچ دەقێکی تر زیاد مەکە.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        return response.text.strip() if response and response.text else None

    except Exception as e:
        print(f"❌ کێشە لە Gemini: {e}")
        return None


# =========================================================
# PARSE GEMINI
# =========================================================

def parse_gemini_result(result):
    if not result:
        return None

    title_match = re.search(
        r"TITLE\s*:\s*(.*?)(?=\n\s*BODY\s*:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    body_match = re.search(
        r"BODY\s*:\s*(.*?)(?=\n\s*FULL_BODY\s*:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    full_body_match = re.search(
        r"FULL_BODY\s*:\s*(.*?)(?=\n\s*HASHTAGS\s*:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    hashtags_match = re.search(
        r"HASHTAGS\s*:\s*(.*?)(?=\n\s*SOURCE\s*:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    source_match = re.search(
        r"SOURCE\s*:\s*(.+)",
        result,
        re.IGNORECASE
    )

    title = clean_text(title_match.group(1)) if title_match else ""
    body = clean_text(body_match.group(1)) if body_match else ""
    full_body = clean_text(full_body_match.group(1)) if full_body_match else ""
    hashtags = clean_text(hashtags_match.group(1)) if hashtags_match else "#ASONEWS #هەواڵ #کوردستان"
    source_name = clean_text(source_match.group(1)) if source_match else ""

    if not title or not body:
        return None

    if not full_body:
        full_body = body

    if "#ASONEWS" not in hashtags:
        hashtags += " #ASONEWS"
    if "کوردستان" not in hashtags and "Kurdistan" not in hashtags:
        hashtags += " #کوردستان"
    if "عێراق" not in hashtags and "Iraq" not in hashtags:
        hashtags += " #عێراق"

    return {
        "title": title,
        "body": body,
        "full_body": full_body,
        "hashtags": hashtags,
        "source_name": source_name,
    }


def build_post(parsed):
    return (
        f"📰 {parsed['title']}\n\n"
        f"{parsed['body']}\n\n"
        f"{parsed['hashtags']}\n\n"
        f"سەرچاوە: {parsed['source_name']}"
    )


def build_first_comment(parsed):
    return (
        "📌 درێژەی هەواڵ:\n\n"
        f"{parsed['full_body']}\n\n"
        f"سەرچاوە: {parsed['source_name']}"
    )


# =========================================================
# FACEBOOK FIRST COMMENT
# =========================================================

def publish_first_comment(post_id, comment):
    if not post_id:
        return False

    print("\n" + "=" * 60)
    print("💬 FIRST COMMENT")
    print("=" * 60)

    try:
        url = f"https://graph.facebook.com/{post_id}/comments"

        response = session.post(
            url,
            data={
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
                "message": comment,
            },
            timeout=60
        )

        print(f"Status: {response.status_code}")
        print(response.text)

        if response.status_code == 200:
            print("✅ First comment posted.")
            return True

        print("⚠️ پۆست کرا، بەڵام کۆمێنتی یەکەم نەکرا.")
        return False

    except Exception as e:
        print(f"⚠️ کێشەی کۆمێنت: {e}")
        return False


# =========================================================
# FACEBOOK PHOTO
# =========================================================

def publish_photo(image_path, message):
    try:
        with open(
            image_path,
            "rb"
        ) as image_file:

            response = requests.post(
                FACEBOOK_PHOTO_URL,
                files={
                    "source": (
                        "ASO_NEWS.jpg",
                        image_file,
                        "image/jpeg"
                    )
                },
                data={
                    "message": message,
                    "access_token":
                        FACEBOOK_PAGE_ACCESS_TOKEN
                },
                timeout=90
            )

        print(
            "📘 Facebook photo:",
            response.status_code
        )

        print(response.text)

        return response

    except Exception as e:
        print(
            f"❌ کێشە لە Facebook photo: {e}"
        )

        return None


# =========================================================
# VIDEO
# =========================================================

def download_video(
    video_url,
    filename="news_video.mp4"
):
    try:
        print(
            f"🎥 هەوڵی داگرتنی ڤیدیۆ: {video_url}"
        )

        response = session.get(
            video_url,
            timeout=120,
            stream=True
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        is_direct_file = video_url.lower().split("?")[0].endswith(
            (".mp4", ".mov", ".webm", ".m4v")
        )

        if "video" not in content_type and not is_direct_file:
            return None

        total = 0

        with open(
            filename,
            "wb"
        ) as f:

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if not chunk:
                    continue

                total += len(chunk)

                # Maximum 100 MB.
                if total > 100 * 1024 * 1024:
                    return None

                f.write(chunk)

        if total < 50000:
            return None

        print(
            f"✅ ڤیدیۆ داگیرا: "
            f"{total / 1024 / 1024:.1f} MB"
        )

        return filename

    except Exception as e:
        print(
            f"⚠️ کێشە لە ڤیدیۆ: {e}"
        )

        return None


def publish_video(video_path, message):
    try:
        with open(
            video_path,
            "rb"
        ) as video_file:

            response = requests.post(
                FACEBOOK_VIDEO_URL,
                files={
                    "source": (
                        "ASO_NEWS.mp4",
                        video_file,
                        "video/mp4"
                    )
                },
                data={
                    "description": message,
                    "access_token":
                        FACEBOOK_PAGE_ACCESS_TOKEN
                },
                timeout=180
            )

        print(
            "🎥 Facebook video:",
            response.status_code
        )

        print(response.text)

        return response

    except Exception as e:
        print(
            f"❌ کێشە لە Facebook video: {e}"
        )

        return None


# =========================================================
# MAIN
# =========================================================

def choose_news(all_news):
    """
    Deterministic editorial order:
    1) Kurdistan
    2) Iraq
    3) World

    Within each region, the highest scoring and freshest story wins.
    """
    for region in ("kurdistan", "iraq", "world"):
        pool = [x for x in all_news if x.get("region") == region]
        if pool:
            pool.sort(key=lambda x: x.get("score", 0), reverse=True)
            return pool[0]

    return None


def main():
    print("\n" + "=" * 60)
    print("🇹🇯 ASO NEWS — AUTO PUBLISHER v5")
    print("=" * 60)
    print("📌 Editorial priority: KURDISTAN > IRAQ > WORLD")

    all_news = collect_news()

    if not all_news:
        print("ℹ️ هیچ هەواڵێکی نوێ نییە.")
        return

    print(f"✅ {len(all_news)} هەواڵی نوێ دۆزرایەوە.")

    selected_news = choose_news(all_news)

    if not selected_news:
        print("❌ هیچ هەواڵێک بۆ بڵاوکردنەوە هەڵنەبژێردرا.")
        return

    print("\n🎯 هەواڵی هەڵبژێردراو:")
    print(
        f"[{selected_news['region']}] "
        f"[{selected_news['source']}] "
        f"score={selected_news.get('score', 0):.1f}\n"
        f"{selected_news['title']}"
    )

    # Gemini only writes the selected article.
    result = generate_news_post(selected_news)

    if not result:
        print("❌ Gemini هیچ دەقێکی نەگەڕاندەوە.")
        return

    print("\n" + "=" * 60)
    print("🤖 GEMINI")
    print("=" * 60)
    print(result)

    parsed = parse_gemini_result(result)

    if not parsed:
        print("❌ Gemini result نادروستە.")
        return

    post = build_post(parsed)
    first_comment = build_first_comment(parsed)

    print("\n" + "=" * 60)
    print("📰 ASO NEWS — FINAL POST")
    print("=" * 60)
    print(post)

    print("\n" + "=" * 60)
    print("💬 FIRST COMMENT — PREVIEW")
    print("=" * 60)
    print(first_comment)

    # -----------------------------------------------------
    # Find media
    # -----------------------------------------------------
    print("\n📸/🎥 بەدوای میدیادا دەگەڕێین...")

    image_candidates, video_candidates = find_media(
        selected_news["entry"]
    )

    facebook_response = None

    # Prefer a direct video if available.
    if video_candidates:
        video_path = download_video(video_candidates[0])
        if video_path:
            facebook_response = publish_video(
                video_path,
                post
            )

    # Otherwise use branded photo.
    if facebook_response is None:
        image_path = download_best_image(image_candidates)

        if not image_path:
            print("⚠️ وێنەی کوالێتی باش نەدۆزرایەوە؛ fallback بەکاردێت.")
            image_path = create_fallback_image(parsed["title"])

        if not image_path:
            print("❌ نەتوانرا وێنەیەک دروست بکرێت.")
            return

        branded_image = add_aso_logo(image_path)

        facebook_response = publish_photo(
            branded_image,
            post
        )

    # -----------------------------------------------------
    # Facebook post success
    # -----------------------------------------------------
    if not (
        facebook_response
        and facebook_response.status_code == 200
    ):
        print("\n❌ Facebook پۆستەکەی قبوڵ نەکرد.")
        return

    # Extract post ID from Facebook response.
    try:
        facebook_data = facebook_response.json()
    except Exception:
        facebook_data = {}

    post_id = (
        facebook_data.get("post_id")
        or facebook_data.get("id")
    )

    if not post_id:
        print("⚠️ پۆست کرا، بەڵام post_id نەدۆزرایەوە؛ کۆمێنت ناتوانرێت بنێردرێت.")
    else:
        print(f"✅ Facebook post ID: {post_id}")

        # -------------------------------------------------
        # First comment with FULL_BODY
        # -------------------------------------------------
        comment_ok = publish_first_comment(
            post_id,
            first_comment
        )

        if not comment_ok:
            print("⚠️ هەواڵەکە پۆست کرا، بەڵام کۆمێنتی یەکەم سەرکەوتوو نەبوو.")

    # -----------------------------------------------------
    # History: save only after the Facebook post succeeds.
    # -----------------------------------------------------
    posted_news.append({
        "id": selected_news["id"],
        "title": selected_news["title"],
        "source": selected_news["source"],
        "region": selected_news["region"],
        "link": selected_news["link"],
        "post_id": post_id,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    })

    save_history(posted_news)

    print("\n" + "=" * 60)
    print("✅ پۆست بە سەرکەوتوویی بڵاوکرایەوە.")
    if post_id:
        print(f"🆔 POST ID: {post_id}")
    print(f"📰 SOURCE: {selected_news['source']}")
    print(f"📍 REGION: {selected_news['region']}")
    print("=" * 60)

    # Cleanup temporary files.
    for filename in [
        "news_image.jpg",
        "news_image_branded.jpg",
        "news_video.mp4"
    ]:
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception:
            pass


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
