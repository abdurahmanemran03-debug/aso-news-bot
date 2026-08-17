import os
import json
import hashlib
import base64
import re
import html
import time
from urllib.parse import quote, urljoin
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import feedparser

from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageOps, ImageFilter
from google import genai

try:
    from huggingface_hub import InferenceClient
except Exception:
    InferenceClient = None


# ============================================================
# 🇮🇶 ASO NEWS — AUTO PUBLISHER v10
# ============================================================

print("=" * 64)
print("🇮🇶 ASO NEWS — AUTO PUBLISHER v10")
print("=" * 64)


# ============================================================
# 🔐 ENVIRONMENT
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ.get(
    "FACEBOOK_PAGE_ACCESS_TOKEN"
)
POLLINATIONS_API_KEY = os.environ.get(
    "POLLINATIONS_API_KEY"
)
HF_TOKEN = os.environ.get("HF_TOKEN")

if not GEMINI_API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY نەدۆزرایەوە.")

if not FACEBOOK_PAGE_ACCESS_TOKEN:
    raise RuntimeError(
        "❌ FACEBOOK_PAGE_ACCESS_TOKEN نەدۆزرایەوە."
    )


# ============================================================
# ⚙️ CONFIG
# ============================================================

PAGE_ID = "1128027710403407"

GRAPH_VERSION = os.environ.get(
    "FACEBOOK_GRAPH_VERSION",
    "v23.0"
)

HISTORY_FILE = "posted_news.json"
LOGO_FILE = "logo.png"
IMAGE_FILE = "news_image.jpg"
FALLBACK_BACKGROUND_FILE = os.environ.get("FALLBACK_BACKGROUND_FILE", "background.png")

MAX_HISTORY = 2000
MAX_CANDIDATES = 30
MAX_AGE_HOURS = 48
MIN_NEWS_SCORE = 8

ENABLE_FIRST_COMMENT = True

FACEBOOK_PHOTO_URL = (
    f"https://graph.facebook.com/"
    f"{GRAPH_VERSION}/{PAGE_ID}/photos"
)

FACEBOOK_VIDEO_URL = (
    f"https://graph.facebook.com/"
    f"{GRAPH_VERSION}/{PAGE_ID}/videos"
)


# ============================================================
# 🤖 GEMINI
# ============================================================

GEMINI_TEXT_MODEL = os.environ.get(
    "GEMINI_TEXT_MODEL",
    os.environ.get(
        "GEMINI_MODEL",
        "gemini-3.5-flash"
    )
)

GEMINI_IMAGE_MODEL = os.environ.get(
    "GEMINI_IMAGE_MODEL",
    "gemini-3-pro-image"
)

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# 🌐 HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})


# ============================================================
# 📰 SOURCES
# ============================================================

RSS_SOURCES = [
    {
        "name": "Rudaw",
        "priority": 55,
        "query":
            "site:rudaw.net "
            "Kurdistan OR Iraq OR Erbil OR "
            "Sulaymaniyah OR Duhok"
    },
    {
        "name": "Kurdistan24",
        "priority": 54,
        "query":
            "site:kurdistan24.net "
            "Kurdistan OR Iraq OR Erbil OR "
            "Sulaymaniyah OR Duhok"
    },
    {
        "name": "NRT",
        "priority": 53,
        "query":
            "site:nrt-news.com "
            "Kurdistan OR Iraq"
    },
    {
        "name": "BasNews",
        "priority": 52,
        "query":
            "site:basnews.com "
            "Kurdistan OR Iraq"
    },
    {
        "name": "Shafaq News",
        "priority": 51,
        "query":
            "site:shafaq.com "
            "Iraq OR Kurdistan"
    },
    {
        "name": "Iraqi News",
        "priority": 48,
        "query":
            "site:iraqinews.com "
            "Iraq OR Kurdistan"
    },
    {
        "name": "Iraq News",
        "priority": 47,
        "query":
            "Iraq latest news "
            "Kurdistan Baghdad Erbil"
    },
    {
        "name": "Al Jazeera",
        "priority": 30,
        "query":
            "site:aljazeera.com "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "Reuters",
        "priority": 29,
        "query":
            "site:reuters.com "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "AP News",
        "priority": 28,
        "query":
            "site:apnews.com "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "BBC News",
        "priority": 22,
        "query":
            "site:bbc.com/news "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "DW",
        "priority": 20,
        "query":
            "site:dw.com "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "France 24",
        "priority": 20,
        "query":
            "site:france24.com "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "VOA",
        "priority": 18,
        "query":
            "site:voanews.com "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "Anadolu Agency",
        "priority": 18,
        "query":
            "site:aa.com.tr "
            "Iraq OR Kurdistan OR Middle East"
    },
    {
        "name": "The Guardian",
        "priority": 12,
        "query":
            "site:theguardian.com "
            "Iraq OR Kurdistan OR Middle East"
    },
]


# ============================================================
# 🔗 GOOGLE NEWS RSS
# ============================================================

def build_google_news_rss(query):
    return (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}"
        "&hl=en-US&gl=US&ceid=US:en"
    )


# ============================================================
# 📚 HISTORY
# ============================================================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        return data if isinstance(data, list) else []

    except Exception as e:
        print(f"⚠️ history error: {e}")
        return []


def save_history(history):
    try:
        history = history[-MAX_HISTORY:]

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                history,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(
            f"💾 history پاشەکەوت کرا: "
            f"{len(history)}"
        )

    except Exception as e:
        print(
            f"⚠️ history save error: {e}"
        )


posted_news = load_history()


# ============================================================
# 🧹 TEXT
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def create_news_id(title, link):
    title = clean_text(title)

    normalized_title = re.sub(
        r"\s+",
        " ",
        title.lower()
    ).strip()

    link = (link or "").strip()
    base = link or normalized_title

    return hashlib.sha256(
        (
            base
            + "|"
            + normalized_title
        ).encode("utf-8")
    ).hexdigest()


def is_already_posted(news_id):
    for item in posted_news:
        if isinstance(item, str):
            if item == news_id:
                return True

        if isinstance(item, dict):
            if item.get("id") == news_id:
                return True

    return False


# ============================================================
# 🕐 DATE
# ============================================================

def get_entry_time(entry):
    try:
        if entry.get("published_parsed"):
            return time.mktime(
                entry.published_parsed
            )

        if entry.get("updated_parsed"):
            return time.mktime(
                entry.updated_parsed
            )

    except Exception:
        pass

    return time.time()


# ============================================================
# 🖼️ RSS MEDIA
# ============================================================

def get_rss_image(entry):
    try:
        for media in (
            entry.get("media_content", [])
            or []
        ):
            url = media.get("url")
            if url:
                return url

        for media in (
            entry.get("media_thumbnail", [])
            or []
        ):
            url = media.get("url")
            if url:
                return url

        for enclosure in (
            entry.get("enclosures", [])
            or []
        ):
            url = (
                enclosure.get("href")
                or enclosure.get("url")
            )

            if (
                url
                and "image"
                in enclosure.get(
                    "type",
                    ""
                ).lower()
            ):
                return url

        raw = (
            str(entry.get("summary", ""))
            + " "
            + str(entry.get("description", ""))
        )

        for content in (
            entry.get("content", [])
            or []
        ):
            raw += " " + str(
                content.get("value", "")
            )

        matches = re.findall(
            r'<img[^>]+src=["\']([^"\']+)',
            raw,
            re.IGNORECASE
        )

        return (
            matches[0]
            if matches
            else None
        )

    except Exception:
        return None


def get_video_url(entry):
    try:
        for media in (
            entry.get("media_content", [])
            or []
        ):
            url = media.get("url")
            media_type = media.get(
                "type",
                ""
            ).lower()

            if url and (
                "video" in media_type
                or url.lower().endswith(
                    (
                        ".mp4",
                        ".mov",
                        ".webm",
                        ".m4v"
                    )
                )
            ):
                return url

        for enclosure in (
            entry.get("enclosures", [])
            or []
        ):
            url = (
                enclosure.get("href")
                or enclosure.get("url")
            )

            media_type = enclosure.get(
                "type",
                ""
            ).lower()

            if (
                url
                and "video" in media_type
            ):
                return url

    except Exception:
        pass

    return None


# ============================================================
# 📰 FETCH SOURCE
# ============================================================

def fetch_source(source):
    print("=" * 64)
    print(
        f"🔎 سەرچاوە: "
        f"{source['name']}"
    )

    rss_url = build_google_news_rss(
        source["query"]
    )

    try:
        response = session.get(
            rss_url,
            timeout=25
        )

        if response.status_code != 200:
            print(
                f"⚠️ RSS status: "
                f"{response.status_code}"
            )
            return []

        feed = feedparser.parse(
            response.content
        )

        items = []

        for entry in feed.entries:
            title = clean_text(
                entry.get(
                    "title",
                    ""
                )
            )

            link = (
                entry.get(
                    "link",
                    ""
                )
                or ""
            ).strip()

            summary = clean_text(
                entry.get(
                    "summary",
                    ""
                )
            )

            if not title or not link:
                continue

            published_time = get_entry_time(
                entry
            )

            age_hours = (
                time.time()
                - published_time
            ) / 3600

            if age_hours > MAX_AGE_HOURS:
                continue

            news_id = create_news_id(
                title,
                link
            )

            if is_already_posted(news_id):
                continue

            items.append({
                "id": news_id,
                "title": title,
                "link": link,
                "summary": summary,
                "source": source["name"],
                "priority": source["priority"],
                "published_time": published_time,
                "age_hours": age_hours,
                "image_url": get_rss_image(entry),
                "video_url": get_video_url(entry),
            })

        print(
            f"📰 {len(items)} "
            f"هەواڵ دۆزرایەوە"
        )

        return items

    except Exception as e:
        print(
            f"❌ RSS error: {e}"
        )
        return []


# ============================================================
# 🧠 SCORING
# ============================================================

def calculate_news_score(news):
    text = (
        news.get("title", "")
        + " "
        + news.get("summary", "")
    ).lower()

    score = float(
        news.get("priority", 0)
    )

    iraq_keywords = [
        "iraq",
        "baghdad",
        "mosul",
        "basra",
        "kirkuk",
        "najaf",
        "karbala",
        "anbar",
        "erbil",
        "sulaymaniyah",
        "sulaimani",
        "duhok",
        "halabja",
        "kurdistan",
        "kurdish",
        "هەولێر",
        "سلێمانی",
        "دهۆک",
        "کوردستان",
        "عێراق",
        "بغداد",
        "کەرکووک",
        "کرکوک"
    ]

    breaking_keywords = [
        "breaking",
        "urgent",
        "attack",
        "strike",
        "explosion",
        "drone",
        "missile",
        "killed",
        "dies",
        "death",
        "war",
        "earthquake",
        "fire",
        "crisis",
        "election",
        "president",
        "government",
        "security",
        "هێرش",
        "تەقینەوە",
        "درۆن",
        "مووشەک",
        "کوژراو",
        "مردن",
        "جەنگ",
        "هەڵبژاردن",
        "حکومەت",
        "ئاسایش",
        "فۆری"
    ]

    for keyword in iraq_keywords:
        if keyword in text:
            score += 22

    for keyword in breaking_keywords:
        if keyword in text:
            score += 8

    age = news.get(
        "age_hours",
        24
    )

    if age < 2:
        score += 18
    elif age < 6:
        score += 12
    elif age < 12:
        score += 7
    elif age < 24:
        score += 3

    if news.get("image_url"):
        score += 8

    if news.get("video_url"):
        score += 10

    preferred = {
        "Rudaw",
        "Kurdistan24",
        "NRT",
        "BasNews",
        "Shafaq News",
        "Iraqi News",
        "Iraq News"
    }

    if news.get("source") in preferred:
        score += 12

    return score


def deduplicate_news(items):
    unique = {}

    for item in items:
        normalized = re.sub(
            r"[^a-zA-Z0-9\u0600-\u06FF]+",
            " ",
            item["title"].lower()
        ).strip()

        key = normalized[:180]

        if key not in unique:
            unique[key] = item
        else:
            if (
                calculate_news_score(item)
                >
                calculate_news_score(
                    unique[key]
                )
            ):
                unique[key] = item

    return list(unique.values())


def collect_news():
    all_news = []

    for source in RSS_SOURCES:
        all_news.extend(
            fetch_source(source)
        )
        time.sleep(0.35)

    print("=" * 64)
    print(
        f"✅ کۆی هەواڵی نوێ: "
        f"{len(all_news)}"
    )

    all_news = deduplicate_news(
        all_news
    )

    for item in all_news:
        item["score"] = calculate_news_score(
            item
        )

    all_news.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    candidates = all_news[:MAX_CANDIDATES]

    print("\n📊 هەواڵە بەرزترینەکان:")

    for i, item in enumerate(
        candidates[:15],
        1
    ):
        print(
            f"{i}. "
            f"[{item['source']}] "
            f"{item['title']} "
            f"| score="
            f"{item['score']:.1f}"
        )

    return candidates


# ============================================================
# 🧩 GEMINI TEXT FALLBACK
# ============================================================

def build_local_fallback_news(
    candidates
):
    """
    ئەگەر Gemini Text بەهۆی 503/429 یان
    هەر هۆکارێکی تر کار نەکات، هەواڵ
    لە زانیاری سەرچاوەکە خۆی دروست دەکات.
    """

    if not candidates:
        return None

    selected = candidates[0].copy()

    original_title = clean_text(
        selected.get("title", "")
    )

    summary = clean_text(
        selected.get("summary", "")
    )

    source = clean_text(
        selected.get("source", "")
    )

    # بۆ ئەوەی هەرگیز بەبێ دەق نەبێت
    if not summary:
        summary = (
            "ئەم هەواڵە لەلایەن "
            f"{source} ـەوە بڵاوکراوەتەوە."
        )

    selected["kur_title"] = original_title
    selected["body"] = summary[:600]
    selected["full_body"] = summary[:1200]
    selected["hashtags"] = (
        "#ASONEWS #کوردستان #عێراق"
    )

    print(
        "🆘 LOCAL NEWS FALLBACK "
        "چالاک کرا."
    )

    return selected


def is_retryable_gemini_error(error):
    text = str(error).lower()

    retry_words = [
        "503",
        "unavailable",
        "high demand",
        "429",
        "rate limit",
        "resource exhausted",
        "quota"
    ]

    return any(
        word in text
        for word in retry_words
    )


# ============================================================
# 🤖 GEMINI TEXT
# ============================================================

def generate_kurdish_news(
    candidates
):
    if not candidates:
        return None

    candidate_text = ""

    for i, item in enumerate(
        candidates,
        1
    ):
        candidate_text += (
            f"\n\nSOURCE_NUMBER: {i}\n"
            f"SOURCE: {item['source']}\n"
            f"TITLE: {item['title']}\n"
            f"SUMMARY: {item['summary'][:1400]}\n"
            f"URL: {item['link']}\n"
        )

    prompt = f"""
تۆ نووسەر و هەڵبژێری هەواڵی
پەیجی ASO NEWS ـیت.

یاساکانی هەڵبژاردن:

1. هەواڵی تازە و گرنگ هەڵبژێرە.
2. هەواڵی کوردستان پێش هەواڵی جیهانیە.
3. دوای کوردستان، هەواڵی عێراق پێش
هەواڵی ناوچەیی و جیهانیە.
4. هیچ زانیارییەکی لە سەرچاوەکەدا
نییە زیاد مەکە.
5. شیکاری سیاسی، پێشبینی و بۆچوون
زیاد مەکە.
6. ناوی کەس و شوێن بە دروستی بنووسە.
7. هەواڵەکە بە کوردی سۆرانییەکی
پاک و پیشەیی بنووسە.

OUTPUT تەنها:

SOURCE_NUMBER: 1

TITLE:
ناونیشانی کوردی

BODY:
2 تا 4 ڕستەی کورت و ڕوون.

FULL_BODY:
2 تا 5 پاراگرافی کورت بۆ درێژەی هەواڵ.

HASHTAGS:
#ASONEWS #کوردستان #عێراق

SOURCE:
ناوی سەرچاوە

هەواڵەکان:
{candidate_text}
"""

    max_attempts = 3

    for attempt in range(
        1,
        max_attempts + 1
    ):
        try:
            print("\n" + "=" * 64)
            print(
                f"🤖 GEMINI TEXT "
                f"— ATTEMPT {attempt}/{max_attempts}"
            )
            print(
                f"🤖 MODEL: "
                f"{GEMINI_TEXT_MODEL}"
            )

            response = client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=prompt
            )

            text = (
                response.text
                or ""
            ).strip()

            if not text:
                raise RuntimeError(
                    "Gemini response بەتاڵ بوو."
                )

            print(text)

            match = re.search(
                r"SOURCE_NUMBER\s*:\s*(\d+)",
                text,
                re.IGNORECASE
            )

            source_number = (
                int(match.group(1))
                if match
                else 1
            )

            if not (
                1 <= source_number <= len(candidates)
            ):
                source_number = 1

            selected = candidates[
                source_number - 1
            ].copy()

            title_match = re.search(
                r"TITLE\s*:\s*(.*?)(?=\n\s*BODY\s*:)",
                text,
                re.IGNORECASE | re.DOTALL
            )

            body_match = re.search(
                r"BODY\s*:\s*(.*?)(?=\n\s*FULL_BODY\s*:)",
                text,
                re.IGNORECASE | re.DOTALL
            )

            full_body_match = re.search(
                r"FULL_BODY\s*:\s*(.*?)(?=\n\s*HASHTAGS\s*:)",
                text,
                re.IGNORECASE | re.DOTALL
            )

            hashtags_match = re.search(
                r"HASHTAGS\s*:\s*(.*?)(?=\n\s*SOURCE\s*:)",
                text,
                re.IGNORECASE | re.DOTALL
            )

            selected["kur_title"] = (
                clean_text(
                    title_match.group(1)
                )
                if title_match
                else clean_text(
                    selected["title"]
                )
            )

            selected["body"] = (
                clean_text(
                    body_match.group(1)
                )
                if body_match
                else clean_text(
                    selected["summary"]
                )
            )

            selected["full_body"] = (
                clean_text(
                    full_body_match.group(1)
                )
                if full_body_match
                else selected["body"]
            )

            selected["hashtags"] = (
                clean_text(
                    hashtags_match.group(1)
                )
                if hashtags_match
                else "#ASONEWS #کوردستان #عێراق"
            )

            if "#ASONEWS" not in selected["hashtags"]:
                selected["hashtags"] += " #ASONEWS"

            if (
                "کوردستان" not in selected["hashtags"]
                and
                "Kurdistan" not in selected["hashtags"]
            ):
                selected["hashtags"] += " #کوردستان"

            if (
                "عێراق" not in selected["hashtags"]
                and
                "Iraq" not in selected["hashtags"]
            ):
                selected["hashtags"] += " #عێراق"

            return selected

        except Exception as e:
            print(
                f"❌ Gemini error: {e}"
            )

            if (
                attempt < max_attempts
                and
                is_retryable_gemini_error(e)
            ):
                wait_seconds = 4 * attempt

                print(
                    f"⏳ Gemini retry "
                    f"دوای {wait_seconds} چرکە..."
                )

                time.sleep(
                    wait_seconds
                )
                continue

            break

    print(
        "⚠️ Gemini Text بەردەست نییە."
    )

    print(
        "↪️ دەچینە Local News Fallback."
    )

    return build_local_fallback_news(
        candidates
    )


# ============================================================
# 📝 FACEBOOK TEXT
# ============================================================

def build_post(news):
    title = clean_text(
        news.get(
            "kur_title",
            news.get(
                "title",
                ""
            )
        )
    )

    body = clean_text(
        news.get(
            "body",
            ""
        )
    )

    hashtags = clean_text(
        news.get(
            "hashtags",
            "#ASONEWS #کوردستان #عێراق"
        )
    )

    source = clean_text(
        news.get(
            "source",
            ""
        )
    )

    return (
        f"📰 {title}\n\n"
        f"{body}\n\n"
        f"{hashtags}\n\n"
        f"سەرچاوە: {source}"
    )


def build_first_comment(news):
    full_body = clean_text(
        news.get(
            "full_body",
            news.get(
                "body",
                ""
            )
        )
    )

    source = clean_text(
        news.get(
            "source",
            ""
        )
    )

    link = clean_text(
        news.get(
            "link",
            ""
        )
    )

    if not full_body:
        full_body = clean_text(
            news.get(
                "body",
                ""
            )
        )

    comment = (
        "📌 درێژەی هەواڵ:\n\n"
        f"{full_body}\n\n"
        f"سەرچاوە: {source}"
    )

    if (
        link
        and link.startswith("http")
    ):
        comment += (
            f"\n🔗 {link}"
        )

    return comment


# ============================================================
# 🌐 ARTICLE IMAGES
# ============================================================

def get_article_images(article_url):
    if not article_url:
        return []

    images = []
    page = ""
    final_url = article_url

    try:
        response = session.get(
            article_url,
            timeout=25,
            allow_redirects=True,
            headers={
                "Accept":
                    "text/html,"
                    "application/xhtml+xml"
            }
        )

        if response.status_code == 200:
            page = response.text
            final_url = (
                response.url
                or article_url
            )

    except Exception as e:
        print(
            f"⚠️ article error: {e}"
        )

    if not page:
        return []

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:
        for match in re.findall(
            pattern,
            page,
            re.IGNORECASE
        ):
            image_url = urljoin(
                final_url,
                html.unescape(
                    match.strip()
                )
            )

            if (
                image_url.startswith("http")
                and image_url not in images
            ):
                images.append(
                    image_url
                )

    try:
        html_images = re.findall(
            r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)',
            page,
            re.IGNORECASE
        )

        for image_url in html_images:
            image_url = urljoin(
                final_url,
                html.unescape(
                    image_url.strip()
                )
            )

            if (
                image_url.startswith("http")
                and image_url not in images
            ):
                images.append(
                    image_url
                )

    except Exception:
        pass

    return images[:80]


# ============================================================
# 📥 DOWNLOAD REAL IMAGES
# ============================================================

def download_image_candidates(candidates):
    best = None
    checked = set()

    bad_words = (
        "logo",
        "icon",
        "avatar",
        "favicon",
        "placeholder",
        "default",
        "sprite",
        "profile",
        "blank",
        "dailyfeed"
    )

    for image_url in candidates:
        if (
            not image_url
            or image_url in checked
        ):
            continue

        checked.add(image_url)

        try:
            print(
                f"🔎 پشکنینی وێنە: "
                f"{image_url}"
            )

            low_url = image_url.lower()

            if any(
                word in low_url
                for word in bad_words
            ):
                print(
                    "↪️ وێنەکە "
                    "ڕەتکرایەوە."
                )
                continue

            response = session.get(
                image_url,
                timeout=25,
                allow_redirects=True,
                headers={
                    "Accept":
                        "image/avif,"
                        "image/webp,"
                        "image/jpeg,"
                        "image/png,"
                        "*/*"
                }
            )

            if response.status_code != 200:
                continue

            content_type = (
                response.headers
                .get(
                    "content-type",
                    ""
                )
                .lower()
            )

            if "image" not in content_type:
                continue

            data = response.content

            if len(data) < 30_000:
                continue

            image = Image.open(
                BytesIO(data)
            ).convert("RGB")

            width, height = image.size

            if (
                width < 800
                or height < 450
            ):
                continue

            aspect = width / height

            if (
                aspect < 1.15
                or aspect > 2.40
            ):
                continue

            score = (
                width * height
                + len(data) * 3
            )

            if (
                1.45 <= aspect <= 2.05
            ):
                score += 500_000

            if (
                best is None
                or score > best["score"]
            ):
                best = {
                    "data": data,
                    "url": image_url,
                    "width": width,
                    "height": height,
                    "score": score,
                }

        except Exception as e:
            print(
                f"⚠️ image error: {e}"
            )

    return best


# ============================================================
# 🖋️ FONT + DATE
# ============================================================

FONT_BOLD_FILE = os.environ.get(
    "ASO_FONT_BOLD",
    "/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf"
)

FONT_REGULAR_FILE = os.environ.get(
    "ASO_FONT_REGULAR",
    "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf"
)


def format_kurdish_date():
    """Return today's Baghdad date in a compact Kurdish format."""
    now = datetime.now(ZoneInfo("Asia/Baghdad"))
    months = {
        1: "کانوونی دووەم",
        2: "شوبات",
        3: "ئازار",
        4: "نیسان",
        5: "ئایار",
        6: "حوزەیران",
        7: "تەمموز",
        8: "ئاب",
        9: "ئەیلول",
        10: "تشرینی یەکەم",
        11: "تشرینی دووەم",
        12: "کانوونی یەکەم",
    }
    return f"{now.day}ی {months[now.month]} {now.year}"


def shape_text(text):
    # Pillow's RAQM support handles Kurdish/Arabic shaping and RTL layout.
    return clean_text(text)


# ============================================================
# 🖋️ FONT
# ============================================================

def find_font(size, bold=False):
    preferred = FONT_BOLD_FILE if bold else FONT_REGULAR_FILE

    paths = [
        preferred,
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# 🖼️ IMAGE HELPERS
# ============================================================

def fit_cover(image, size):
    target_w, target_h = size
    src_w, src_h = image.size

    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_w = int(
            src_h * target_ratio
        )

        left = (
            src_w - new_w
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_w,
                src_h
            )
        )

    else:
        new_h = int(
            src_w / target_ratio
        )

        top = (
            src_h - new_h
        ) // 2

        image = image.crop(
            (
                0,
                top,
                src_w,
                top + new_h
            )
        )

    return image.resize(
        (target_w, target_h),
        Image.LANCZOS
    )


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word
        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
            direction="rtl",
            language="ku",
        )

        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


# ============================================================
# 🎨 PROFESSIONAL OVERLAY
# ============================================================
def draw_rtl_text(draw, xy, text, font, fill, anchor="ra", stroke_width=0, stroke_fill=None):
    kwargs = {
        "font": font,
        "fill": fill,
        "anchor": anchor,
        "direction": "rtl",
        "language": "ku",
        "stroke_width": stroke_width,
    }
    if stroke_fill is not None:
        kwargs["stroke_fill"] = stroke_fill
    draw.text(xy, shape_text(text), **kwargs)



def add_professional_overlay(
    image_file,
    title,
    output_file=IMAGE_FILE
):
    try:
        image = Image.open(
            image_file
        ).convert("RGB")

        image = fit_background_full(
            image,
            (1200, 675)
        )

        image = ImageEnhance.Contrast(
            image
        ).enhance(1.05)

        image = ImageEnhance.Color(
            image
        ).enhance(1.05)

        overlay = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(
            overlay
        )

        width, height = image.size
        gradient_height = 290

        for y in range(
            height - gradient_height,
            height
        ):
            relative = (
                y
                - (
                    height
                    - gradient_height
                )
            ) / gradient_height

            alpha = int(
                20
                + 205 * relative
            )

            draw.line(
                [
                    (0, y),
                    (width, y)
                ],
                fill=(
                    0,
                    0,
                    0,
                    alpha
                )
            )

        draw.rectangle(
            [0, 0, width, 10],
            fill=(
                220,
                30,
                45,
                255
            )
        )

        title_font = find_font(
            46,
            bold=True
        )

        title = clean_text(title)

        lines = wrap_text(
            draw,
            title,
            title_font,
            width - 110
        )

        lines = lines[:4]
        line_height = 60

        box_height = (
            len(lines)
            * line_height
            + 90
        )

        box_top = (
            height
            - box_height
            - 35
        )

        draw.rounded_rectangle(
            [
                35,
                box_top,
                width - 35,
                height - 25
            ],
            radius=22,
            fill=(
                12,
                12,
                16,
                175
            ),
            outline=(
                220,
                30,
                45,
                230
            ),
            width=3
        )

        y = box_top + 35

        for line in lines:
            draw_rtl_text(
                draw,
                (width - 60, y),
                line,
                title_font,
                (255, 255, 255, 255),
                anchor="ra",
                stroke_width=1,
                stroke_fill=(0, 0, 0, 220),
            )

            y += line_height

        date_font = find_font(22, bold=True)
        draw.rounded_rectangle(
            [40, 25, 310, 70],
            radius=16,
            fill=(210, 25, 43, 225),
        )
        draw_rtl_text(
            draw,
            (295, 47),
            format_kurdish_date(),
            date_font,
            (255, 255, 255, 255),
            anchor="rm",
        )

        result = Image.alpha_composite(
            image.convert("RGBA"),
            overlay
        ).convert("RGB")

        result.save(
            output_file,
            "JPEG",
            quality=94,
            optimize=True
        )

        print(
            "✅ وێنەی پڕۆفیشنالی "
            "ASO NEWS ئامادە کرا."
        )

        return output_file

    except Exception as e:
        print(
            f"⚠️ overlay error: {e}"
        )

        return image_file


# ============================================================
# 🆘 FALLBACK BACKGROUND
# ============================================================

def fit_background_full(image, size):
    """Show the whole background without cropping it."""
    target_w, target_h = size
    image = image.convert("RGB")

    # Create a softly blurred copy as the full-frame backdrop.
    blurred = ImageOps.fit(image, size, method=Image.LANCZOS).filter(
        ImageFilter.GaussianBlur(18)
    )
    blurred = ImageEnhance.Brightness(blurred).enhance(0.72)

    # Fit the original image inside the frame, preserving all of it.
    contained = ImageOps.contain(image, size, method=Image.LANCZOS)
    x = (target_w - contained.width) // 2
    y = (target_h - contained.height) // 2
    blurred.paste(contained, (x, y))
    return blurred


def create_fallback_background(news, output_file=IMAGE_FILE):
    """Create the ASO NEWS branded fallback image with full background + date."""
    fallback_candidates = [
        FALLBACK_BACKGROUND_FILE,
        "background.png",
        "fallback_background.jpg",
        "fallback_background.jpeg",
        "fallback_background.png",
    ]

    background_file = next(
        (path for path in fallback_candidates if path and os.path.exists(path)),
        None,
    )

    if not background_file:
        print("❌ هیچ fallback background ـێک نەدۆزرایەوە.")
        return None

    try:
        print("\n" + "=" * 64)
        print("🆘 ASO NEWS — BACKGROUND FALLBACK v11")

        background = Image.open(background_file).convert("RGB")
        background = fit_background_full(background, (1200, 675))
        width, height = background.size

        title = shape_text(
            news.get("kur_title", news.get("title", "ASO NEWS"))
        )
        date_text = format_kurdish_date()

        overlay = Image.new("RGBA", background.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # A subtle top veil keeps the date readable without hiding the background.
        draw.rectangle([0, 0, width, 78], fill=(7, 18, 31, 115))

        # Date badge.
        date_font = find_font(25, bold=True)
        date_box_w = 315
        date_box_h = 50
        date_x1 = 42
        date_y1 = 18
        draw.rounded_rectangle(
            [date_x1, date_y1, date_x1 + date_box_w, date_y1 + date_box_h],
            radius=18,
            fill=(210, 25, 43, 235),
        )
        draw_rtl_text(
            draw,
            (date_x1 + date_box_w - 16, date_y1 + date_box_h // 2),
            date_text,
            date_font,
            (255, 255, 255, 255),
            anchor="rm",
        )

        # Small ASO NEWS label.
        brand_font = find_font(27, bold=True)
        draw_rtl_text(
            draw,
            (width - 42, 43),
            "ASO NEWS",
            brand_font,
            (255, 255, 255, 255),
            anchor="rm",
        )

        title_font = find_font(48, bold=True)
        max_width = width - 190
        lines = wrap_text(draw, title, title_font, max_width)[:4]

        line_height = 61
        padding_x = 42
        padding_y = 28
        box_height = len(lines) * line_height + padding_y * 2 + 52
        box_top = int((height - box_height) / 2 + 24)
        box_bottom = box_top + box_height

        # More transparent card so the whole background remains visible.
        draw.rounded_rectangle(
            [padding_x, box_top, width - padding_x, box_bottom],
            radius=28,
            fill=(255, 255, 255, 218),
            outline=(10, 28, 48, 245),
            width=4,
        )

        # Red accent line.
        draw.rounded_rectangle(
            [padding_x + 22, box_top + 18, width - padding_x - 22, box_top + 24],
            radius=3,
            fill=(210, 25, 43, 255),
        )

        y = box_top + padding_y + 34
        for line in lines:
            draw_rtl_text(
                draw,
                (width // 2, y),
                line,
                title_font,
                (8, 25, 43, 255),
                anchor="ma",
                stroke_width=0,
            )
            y += line_height

        # Date also appears below the headline as a news-card metadata line.
        meta_font = find_font(23, bold=False)
        draw_rtl_text(
            draw,
            (width // 2, box_bottom - 25),
            date_text,
            meta_font,
            (80, 90, 105, 255),
            anchor="ms",
        )

        result = Image.alpha_composite(
            background.convert("RGBA"), overlay
        ).convert("RGB")

        result.save(output_file, "JPEG", quality=95, optimize=True)
        print("✅ Fallback background v11 ئامادە کرا — background تەواو دیارە + تاریخ زیادکرا.")
        return output_file

    except Exception as e:
        print(f"❌ fallback background error: {e}")
        return None


# ============================================================
# 🖼️ WATERMARK
# ============================================================

def add_watermark(image_file):
    if not os.path.exists(LOGO_FILE):
        print(
            "⚠️ logo.png نەدۆزرایەوە."
        )
        return image_file

    try:
        image = Image.open(
            image_file
        ).convert("RGBA")

        logo = Image.open(
            LOGO_FILE
        ).convert("RGBA")

        max_logo_width = int(
            image.width * 0.15
        )

        max_logo_height = int(
            image.height * 0.15
        )

        logo.thumbnail(
            (
                max_logo_width,
                max_logo_height
            ),
            Image.LANCZOS
        )

        alpha = logo.getchannel("A")

        alpha = ImageEnhance.Contrast(
            alpha
        ).enhance(1.20)

        alpha = alpha.point(
            lambda p:
                min(
                    255,
                    int(p * 0.90)
                )
        )

        logo.putalpha(alpha)

        margin = 24

        x = (
            image.width
            - logo.width
            - margin
        )

        y = (
            image.height
            - logo.height
            - margin
        )

        image.alpha_composite(
            logo,
            (x, y)
        )

        image.convert(
            "RGB"
        ).save(
            image_file,
            "JPEG",
            quality=95,
            optimize=True
        )

        print(
            "✅ لۆگۆی ASO NEWS زیاد کرا."
        )

        return image_file

    except Exception as e:
        print(
            f"⚠️ watermark error: {e}"
        )

        return image_file


# ============================================================
# 🤖 AI IMAGE PROMPT
# ============================================================

def build_ai_image_prompt(news):
    title = clean_text(
        news.get(
            "kur_title",
            news.get(
                "title",
                "NEWS"
            )
        )
    )

    body = clean_text(
        news.get(
            "body",
            news.get(
                "summary",
                ""
            )
        )
    )

    source = clean_text(
        news.get(
            "source",
            ""
        )
    )

    return f"""
Create a premium photorealistic
editorial-news image for ASO NEWS.

HEADLINE:
{title}

SUMMARY:
{body}

SOURCE:
{source}

Create one coherent 16:9
landscape composition.

The image should look like a
real professional newsroom photograph.

Represent the specific event,
people, location or situation
described by the news.

Use realistic anatomy,
architecture, vehicles,
natural lighting and documentary
photography.

Use realistic proportions,
professional lens depth,
sharp main subject and subtle
cinematic color grading.

Do NOT create a poster.
Do NOT create a collage.
Do NOT create social-media graphics.
Do NOT include readable text.
Do NOT include headlines.
Do NOT include logos.
Do NOT include watermarks.
Do NOT include UI elements.
Do NOT include borders.
Do NOT include fake captions.
Do not put ASO NEWS branding
inside the image.

Branding is added separately
by the program.

Create a polished 16:9
editorial news photograph.
""".strip()


# ============================================================
# 💾 SAVE GENERATED IMAGE
# ============================================================

def _save_generated_image(
    image_data,
    filename
):
    try:
        if isinstance(
            image_data,
            str
        ):
            image_data = base64.b64decode(
                image_data
            )

        if (
            not image_data
            or len(image_data) < 20_000
        ):
            return False

        with Image.open(
            BytesIO(image_data)
        ) as generated:

            generated = generated.convert(
                "RGB"
            )

            generated = fit_cover(
                generated,
                (1200, 675)
            )

            generated.save(
                filename,
                "JPEG",
                quality=96,
                optimize=True
            )

        with Image.open(
            filename
        ) as check:
            check.verify()

        return True

    except Exception as e:
        print(
            f"⚠️ generated image "
            f"validation error: {e}"
        )
        return False


def is_quota_error(error):
    text = str(error).lower()

    quota_words = [
        "429",
        "quota",
        "quota exceeded",
        "rate limit",
        "resource exhausted",
        "limit: 0",
        "too_many_requests"
    ]

    return any(
        word in text
        for word in quota_words
    )


# ============================================================
# 🎨 GEMINI IMAGE
# ============================================================

def try_gemini_image(
    prompt,
    filename
):
    print("\n" + "=" * 64)
    print("🎨 GEMINI IMAGE")
    print(
        f"🎨 MODEL: "
        f"{GEMINI_IMAGE_MODEL}"
    )

    try:
        interaction = client.interactions.create(
            model=GEMINI_IMAGE_MODEL,
            input=prompt,
            tools=[
                {
                    "type": "google_search"
                }
            ],
            response_format={
                "type": "image",
                "aspect_ratio": "16:9",
                "image_size": "2K",
            },
        )

        output_image = getattr(
            interaction,
            "output_image",
            None
        )

        image_data = getattr(
            output_image,
            "data",
            None
        )

        if (
            image_data
            and _save_generated_image(
                image_data,
                filename
            )
        ):
            print(
                "✅ Gemini image "
                "سەرکەوتوو بوو."
            )
            return filename

        print(
            "⚠️ Gemini هیچ "
            "وێنەیەکی دروستی "
            "نەگەڕاندەوە."
        )

    except Exception as e:
        if is_quota_error(e):
            print(
                "⚠️ Gemini Image "
                "quota بەردەست نییە."
            )
        else:
            print(
                f"⚠️ Gemini Image "
                f"error: {e}"
            )

    return None


# ============================================================
# 🎨 HUGGING FACE IMAGE
# ============================================================

def try_huggingface_image(
    prompt,
    filename
):
    if not HF_TOKEN:
        print(
            "⚠️ HF_TOKEN نەدۆزرایەوە."
        )
        return None

    if InferenceClient is None:
        print(
            "⚠️ huggingface_hub "
            "دانەمەزراوە."
        )
        return None

    print("\n" + "=" * 64)
    print(
        "🎨 HUGGING FACE "
        "— IMAGE FALLBACK"
    )

    try:
        hf_client = InferenceClient(
            provider="fal-ai",
            api_key=HF_TOKEN,
            timeout=180
        )

        image = hf_client.text_to_image(
            prompt=prompt,
            model=(
                "black-forest-labs/"
                "FLUX.1-schnell"
            )
        )

        if not image:
            return None

        image = image.convert("RGB")
        image = fit_cover(
            image,
            (1200, 675)
        )

        image.save(
            filename,
            "JPEG",
            quality=95,
            optimize=True
        )

        print(
            "✅ Hugging Face "
            "وێنەی دروست کرد."
        )

        return filename

    except Exception as e:
        text = str(e)

        print(
            f"⚠️ Hugging Face "
            f"error: {text}"
        )

        if "403" in text:
            print(
                "ℹ️ HF_TOKEN permission "
                "کێشەی هەیە."
            )

        return None


# ============================================================
# 🎨 POLLINATIONS
# ============================================================

def try_pollinations_image(
    prompt,
    filename
):
    if not POLLINATIONS_API_KEY:
        print(
            "⚠️ POLLINATIONS_API_KEY "
            "نەدۆزرایەوە."
        )
        return None

    print("\n" + "=" * 64)
    print(
        "🎨 POLLINATIONS "
        "— OPTIONAL FALLBACK"
    )

    model_name = os.environ.get(
        "POLLINATIONS_IMAGE_MODEL",
        "flux"
    )

    try:
        encoded_prompt = quote(
            prompt,
            safe=""
        )

        url = (
            "https://gen.pollinations.ai/"
            f"image/{encoded_prompt}"
        )

        response = session.get(
            url,
            params={
                "model": model_name,
                "width": 1536,
                "height": 864,
                "quality": "high",
                "safe": "true"
            },
            headers={
                "Authorization":
                    f"Bearer "
                    f"{POLLINATIONS_API_KEY}",
                "Accept":
                    "image/jpeg,"
                    "image/png,*/*"
            },
            timeout=180
        )

        print(
            f"Pollinations status: "
            f"{response.status_code}"
        )

        if (
            response.status_code == 200
            and _save_generated_image(
                response.content,
                filename
            )
        ):
            print(
                "✅ Pollinations "
                "وێنەی دروست کرد."
            )
            return filename

        if response.status_code == 402:
            print(
                "⚠️ Pollinations "
                "balance بەردەست نییە."
            )
            return None

        print(
            f"⚠️ Pollinations "
            f"error: "
            f"{response.text[:300]}"
        )

    except Exception as e:
        print(
            f"⚠️ Pollinations "
            f"exception: {e}"
        )

    return None


# ============================================================
# 🖼️ AI IMAGE PIPELINE
# ============================================================

def create_ai_news_image(
    news,
    filename=IMAGE_FILE
):
    prompt = build_ai_image_prompt(
        news
    )

    result = try_gemini_image(
        prompt,
        filename
    )

    if result:
        return result

    result = try_huggingface_image(
        prompt,
        filename
    )

    if result:
        return result

    result = try_pollinations_image(
        prompt,
        filename
    )

    if result:
        return result

    print(
        "❌ هەموو AI image "
        "provider ـەکان شکستیان هێنا."
    )

    return None


# ============================================================
# 📸 PREPARE IMAGE
# ============================================================

def prepare_image(news):
    candidates = []

    if news.get("image_url"):
        candidates.append(
            news["image_url"]
        )

    article_url = news.get("link")

    if article_url:
        try:
            candidates.extend(
                get_article_images(
                    article_url
                )
            )
        except Exception:
            pass

    candidates = list(
        dict.fromkeys(candidates)
    )

    print("\n" + "=" * 64)
    print(
        "📸 بەدوای وێنەی "
        "ڕاستەقینەدا دەگەڕێین..."
    )

    best = download_image_candidates(
        candidates
    )

    if best:
        try:
            with open(
                IMAGE_FILE,
                "wb"
            ) as f:
                f.write(
                    best["data"]
                )

            print(
                f"📐 وێنە: "
                f"{best['width']}x"
                f"{best['height']}"
            )

            image_file = (
                add_professional_overlay(
                    IMAGE_FILE,
                    news.get(
                        "kur_title",
                        news.get(
                            "title",
                            "ASO NEWS"
                        )
                    )
                )
            )

        except Exception as e:
            print(
                f"⚠️ image error: {e}"
            )
            image_file = None

    else:
        print(
            "⚠️ وێنەی ڕاستەقینە "
            "نەدۆزرایەوە."
        )

        image_file = create_ai_news_image(
            news
        )

        if not image_file:
            print(
                "⚠️ AI image "
                "نەدروست بوو."
            )

            image_file = (
                create_fallback_background(
                    news
                )
            )

    if image_file:
        image_file = add_watermark(
            image_file
        )

    return image_file


# ============================================================
# 📤 FACEBOOK PHOTO
# ============================================================

def publish_photo(
    message,
    image_file
):
    if (
        not image_file
        or not os.path.exists(
            image_file
        )
    ):
        print(
            "❌ image file "
            "نەدۆزرایەوە."
        )
        return None

    print("\n" + "=" * 64)
    print("📘 FACEBOOK PHOTO POST")

    try:
        with open(
            image_file,
            "rb"
        ) as image:

            response = session.post(
                FACEBOOK_PHOTO_URL,
                data={
                    "access_token":
                        FACEBOOK_PAGE_ACCESS_TOKEN,
                    "message":
                        message,
                },
                files={
                    "source": (
                        os.path.basename(
                            image_file
                        ),
                        image,
                        "image/jpeg"
                    )
                },
                timeout=60
            )

        print(
            f"Status: "
            f"{response.status_code}"
        )

        print(response.text)

        if response.status_code != 200:
            return None

        try:
            data = response.json()
        except Exception:
            data = {}

        post_id = (
            data.get("post_id")
            or data.get("id")
        )

        if post_id:
            print(
                f"✅ Facebook "
                f"photo success: "
                f"{post_id}"
            )
            return post_id

    except Exception as e:
        print(
            f"❌ Facebook "
            f"photo error: {e}"
        )

    return None


# ============================================================
# 🎥 FACEBOOK VIDEO
# ============================================================

def publish_video(
    message,
    video_url
):
    if not video_url:
        return None

    print("\n" + "=" * 64)
    print("🎥 VIDEO FOUND")
    print(video_url)

    try:
        response = session.post(
            FACEBOOK_VIDEO_URL,
            data={
                "access_token":
                    FACEBOOK_PAGE_ACCESS_TOKEN,
                "file_url":
                    video_url,
                "description":
                    message
            },
            timeout=90
        )

        print(
            f"Status: "
            f"{response.status_code}"
        )

        print(response.text)

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception:
                data = {}

            return (
                data.get("id")
                or data.get("post_id")
            )

    except Exception as e:
        print(
            f"⚠️ Facebook "
            f"video error: {e}"
        )

    return None


# ============================================================
# 💬 FIRST COMMENT
# ============================================================

def publish_first_comment(
    post_id,
    comment
):
    if (
        not post_id
        or not comment
    ):
        return False

    print("\n" + "=" * 64)
    print("💬 FIRST COMMENT")

    post_ids = [
        str(post_id).strip()
    ]

    if "_" not in str(post_id):
        post_ids.append(
            f"{PAGE_ID}_{post_id}"
        )

    for current_id in dict.fromkeys(
        post_ids
    ):
        url = (
            "https://graph.facebook.com/"
            f"{GRAPH_VERSION}/"
            f"{current_id}/comments"
        )

        try:
            response = session.post(
                url,
                data={
                    "access_token":
                        FACEBOOK_PAGE_ACCESS_TOKEN,
                    "message":
                        comment
                },
                timeout=40
            )

            print(
                f"Comment target: "
                f"{current_id}"
            )

            print(
                f"Comment status: "
                f"{response.status_code}"
            )

            print(response.text)

            if response.status_code == 200:
                print(
                    "✅ First comment "
                    "سەرکەوتوو بوو."
                )
                return True

        except Exception as e:
            print(
                f"⚠️ comment error: "
                f"{e}"
            )

    print(
        "⚠️ First comment "
        "نەکرا."
    )

    return False


# ============================================================
# 💾 RECORD POST
# ============================================================

def record_post(
    news,
    post_id
):
    posted_news.append({
        "id":
            news.get("id"),
        "title":
            news.get(
                "title",
                ""
            ),
        "kur_title":
            news.get(
                "kur_title",
                ""
            ),
        "source":
            news.get(
                "source",
                ""
            ),
        "link":
            news.get(
                "link",
                ""
            ),
        "post_id":
            post_id,
        "timestamp":
            int(time.time())
    })

    save_history(
        posted_news
    )


# ============================================================
# 🧹 REMOVE OLD IMAGE
# ============================================================

def remove_old_image():
    try:
        if os.path.exists(
            IMAGE_FILE
        ):
            os.remove(
                IMAGE_FILE
            )
    except Exception:
        pass


# ============================================================
# 🚀 MAIN
# ============================================================

def main():
    print("\n" + "=" * 64)
    print(
        "🇮🇶 ASO NEWS — "
        "AUTO PUBLISHER v10"
    )
    print("=" * 64)

    candidates = collect_news()

    if not candidates:
        print(
            "⚠️ هیچ هەواڵێکی "
            "نوێ نەدۆزرایەوە."
        )
        return

    good_candidates = [
        item
        for item in candidates
        if item.get(
            "score",
            0
        ) >= MIN_NEWS_SCORE
    ]

    if not good_candidates:
        good_candidates = candidates

    news = generate_kurdish_news(
        good_candidates
    )

    if not news:
        print(
            "❌ هیچ هەواڵێکی "
            "دروست نەکرا."
        )
        return

    final_post = build_post(
        news
    )

    first_comment = build_first_comment(
        news
    )

    print("\n" + "=" * 64)
    print(
        "📰 ASO NEWS — FINAL POST"
    )
    print("=" * 64)
    print(final_post)

    print("\n" + "=" * 64)
    print("💬 FIRST COMMENT")
    print("=" * 64)
    print(first_comment)

    remove_old_image()

    image_file = prepare_image(
        news
    )

    # ========================================================
    # 🆘 FINAL IMAGE SAFETY FALLBACK
    # ========================================================

    if (
        not image_file
        and not news.get("video_url")
    ):
        print(
            "⚠️ هیچ وێنەیەک "
            "بەردەست نییە."
        )

        print(
            "↪️ دووبارە fallback "
            "background تاقی دەکەینەوە."
        )

        image_file = (
            create_fallback_background(
                news
            )
        )

        if image_file:
            image_file = add_watermark(
                image_file
            )

    # ========================================================
    # 📤 PUBLISH
    # ========================================================

    video_url = news.get(
        "video_url"
    )

    post_id = None

    if video_url:
        post_id = publish_video(
            final_post,
            video_url
        )

    if not post_id:
        post_id = publish_photo(
            final_post,
            image_file
        )

    if not post_id:
        print(
            "\n❌ پۆست نەکرا."
        )
        return

    print(
        f"\n✅ پۆست کرا: "
        f"{post_id}"
    )

    time.sleep(2)

    if ENABLE_FIRST_COMMENT:
        publish_first_comment(
            post_id,
            first_comment
        )

    record_post(
        news,
        post_id
    )

    print("\n" + "=" * 64)
    print(
        "✅ ASO NEWS تەواو بوو."
    )

    print(
        f"🆔 POST ID: "
        f"{post_id}"
    )

    print(
        f"📰 SOURCE: "
        f"{news.get('source', '')}"
    )

    print("=" * 64)


# ============================================================
# ▶️ RUN
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as e:
        print("\n" + "=" * 64)
        print("❌ FATAL ERROR")
        print(str(e))
        print("=" * 64)
        raise
