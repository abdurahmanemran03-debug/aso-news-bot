import os
import json
import hashlib
import base64
import re
import html
import time
from urllib.parse import quote, urljoin
from io import BytesIO

import requests
import feedparser

from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageFilter
from google import genai


# ============================================================
# 🇮🇶 ASO NEWS — AUTO PUBLISHER v8
# ============================================================
# Main improvements:
# 1) Kurdistan/Iraq sources have higher priority.
# 2) More sources are searched through Google News RSS.
# 3) Real article images are preferred.
# 4) A professional ASO NEWS graphic is placed over the real image.
# 5) If no real image is available, Gemini creates an event-specific editorial illustration.
# 6) First comment is attempted after publishing; permission errors are diagnosed clearly.
# 7) History prevents duplicate posts.
# 8) One post per workflow run.
# ============================================================

print("=" * 64)
print("🇮🇶 ASO NEWS — AUTO PUBLISHER v8")
print("=" * 64)


# ============================================================
# 🔐 ENVIRONMENT
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")

if not GEMINI_API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY نەدۆزرایەوە.")

if not FACEBOOK_PAGE_ACCESS_TOKEN:
    raise RuntimeError("❌ FACEBOOK_PAGE_ACCESS_TOKEN نەدۆزرایەوە.")


# ============================================================
# ⚙️ CONFIG
# ============================================================

PAGE_ID = "1128027710403407"

GRAPH_VERSION = os.environ.get("FACEBOOK_GRAPH_VERSION", "v23.0")

HISTORY_FILE = "posted_news.json"
LOGO_FILE = "logo.png"
IMAGE_FILE = "news_image.jpg"

MAX_HISTORY = 2000
MAX_CANDIDATES = 30
MAX_AGE_HOURS = 48
MIN_NEWS_SCORE = 8

# One Facebook post per GitHub Actions run.
POST_ONE_NEWS_PER_RUN = True

# If true, put the full article continuation in the first comment.
ENABLE_FIRST_COMMENT = True

FACEBOOK_PHOTO_URL = (
    f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/photos"
)

FACEBOOK_VIDEO_URL = (
    f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/videos"
)


# ============================================================
# 🤖 GEMINI
# ============================================================

GEMINI_TEXT_MODEL = os.environ.get(
    "GEMINI_TEXT_MODEL",
    os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
)

# Gemini 3.5 Flash is for text. Professional image generation uses
# Gemini 3 Pro Image (Nano Banana Pro).
GEMINI_IMAGE_MODEL = os.environ.get(
    "GEMINI_IMAGE_MODEL",
    "gemini-3-pro-image"
)

client = genai.Client(api_key=GEMINI_API_KEY)


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
# Kurdistan/Iraq intentionally have much higher priority.
# ============================================================

RSS_SOURCES = [

    # 🇮🇶 KURDISTAN / IRAQ
    {"name": "Rudaw", "priority": 55,
     "query": "site:rudaw.net Kurdistan OR Iraq OR Erbil OR Sulaymaniyah OR Duhok"},

    {"name": "Kurdistan24", "priority": 54,
     "query": "site:kurdistan24.net Kurdistan OR Iraq OR Erbil OR Sulaymaniyah OR Duhok"},

    {"name": "NRT", "priority": 53,
     "query": "site:nrt-news.com Kurdistan OR Iraq"},

    {"name": "BasNews", "priority": 52,
     "query": "site:basnews.com Kurdistan OR Iraq"},

    {"name": "Shafaq News", "priority": 51,
     "query": "site:shafaq.com Iraq OR Kurdistan"},

    {"name": "Iraqi News", "priority": 48,
     "query": "site:iraqinews.com Iraq OR Kurdistan"},

    {"name": "Iraq News", "priority": 47,
     "query": "Iraq latest news Kurdistan Baghdad Erbil"},

    # 🌍 REGIONAL
    {"name": "Al Jazeera", "priority": 30,
     "query": "site:aljazeera.com Iraq OR Kurdistan OR Middle East"},

    {"name": "Reuters", "priority": 29,
     "query": "site:reuters.com Iraq OR Kurdistan OR Middle East"},

    {"name": "AP News", "priority": 28,
     "query": "site:apnews.com Iraq OR Kurdistan OR Middle East"},

    {"name": "BBC News", "priority": 22,
     "query": "site:bbc.com/news Iraq OR Kurdistan OR Middle East"},

    {"name": "DW", "priority": 20,
     "query": "site:dw.com Iraq OR Kurdistan OR Middle East"},

    {"name": "France 24", "priority": 20,
     "query": "site:france24.com Iraq OR Kurdistan OR Middle East"},

    {"name": "VOA", "priority": 18,
     "query": "site:voanews.com Iraq OR Kurdistan OR Middle East"},

    {"name": "Anadolu Agency", "priority": 18,
     "query": "site:aa.com.tr Iraq OR Kurdistan OR Middle East"},

    {"name": "The Guardian", "priority": 12,
     "query": "site:theguardian.com Iraq OR Kurdistan OR Middle East"},
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
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, list) else []

    except Exception as e:
        print(f"⚠️ history error: {e}")
        return []


def save_history(history):
    try:
        history = history[-MAX_HISTORY:]

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(
                history,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(f"💾 history پاشەکەوت کرا: {len(history)}")

    except Exception as e:
        print(f"⚠️ history save error: {e}")


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
        (base + "|" + normalized_title).encode("utf-8")
    ).hexdigest()


def is_already_posted(news_id):
    for item in posted_news:
        if isinstance(item, str) and item == news_id:
            return True

        if isinstance(item, dict) and item.get("id") == news_id:
            return True

    return False


# ============================================================
# 🕐 DATE
# ============================================================

def get_entry_time(entry):
    try:
        if entry.get("published_parsed"):
            return time.mktime(entry.published_parsed)

        if entry.get("updated_parsed"):
            return time.mktime(entry.updated_parsed)

    except Exception:
        pass

    return time.time()


# ============================================================
# 🖼️ RSS MEDIA
# ============================================================

def get_rss_image(entry):
    try:
        for media in entry.get("media_content", []) or []:
            url = media.get("url")
            if url:
                return url

        for media in entry.get("media_thumbnail", []) or []:
            url = media.get("url")
            if url:
                return url

        for enclosure in entry.get("enclosures", []) or []:
            url = enclosure.get("href") or enclosure.get("url")
            if url and "image" in enclosure.get("type", "").lower():
                return url

        raw = (
            str(entry.get("summary", ""))
            + " "
            + str(entry.get("description", ""))
        )

        for content in entry.get("content", []) or []:
            raw += " " + str(content.get("value", ""))

        matches = re.findall(
            r'<img[^>]+src=["\']([^"\']+)',
            raw,
            re.IGNORECASE
        )

        return matches[0] if matches else None

    except Exception:
        return None


def get_video_url(entry):
    try:
        for media in entry.get("media_content", []) or []:
            url = media.get("url")
            media_type = media.get("type", "").lower()

            if url and (
                "video" in media_type
                or url.lower().endswith(
                    (".mp4", ".mov", ".webm", ".m4v")
                )
            ):
                return url

        for enclosure in entry.get("enclosures", []) or []:
            url = enclosure.get("href") or enclosure.get("url")
            media_type = enclosure.get("type", "").lower()

            if url and "video" in media_type:
                return url

    except Exception:
        pass

    return None


# ============================================================
# 📰 FETCH SOURCE
# ============================================================

def fetch_source(source):
    print("=" * 64)
    print(f"🔎 سەرچاوە: {source['name']}")

    rss_url = build_google_news_rss(source["query"])

    try:
        response = session.get(rss_url, timeout=25)

        if response.status_code != 200:
            print(f"⚠️ RSS status: {response.status_code}")
            return []

        feed = feedparser.parse(response.content)
        items = []

        for entry in feed.entries:
            title = clean_text(entry.get("title", ""))
            link = (entry.get("link", "") or "").strip()
            summary = clean_text(entry.get("summary", ""))

            if not title or not link:
                continue

            published_time = get_entry_time(entry)

            age_hours = (
                time.time() - published_time
            ) / 3600

            if age_hours > MAX_AGE_HOURS:
                continue

            news_id = create_news_id(title, link)

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

        print(f"📰 {len(items)} هەواڵ دۆزرایەوە")
        return items

    except Exception as e:
        print(f"❌ RSS error: {e}")
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

    score = float(news.get("priority", 0))

    iraq_keywords = [
        "iraq", "baghdad", "mosul", "basra", "kirkuk",
        "najaf", "karbala", "anbar", "erbil",
        "sulaymaniyah", "sulaimani", "duhok", "halabja",
        "kurdistan", "kurdish",
        "هەولێر", "سلێمانی", "دهۆک", "کوردستان",
        "عێراق", "بغداد", "کەرکووک", "کرکوک"
    ]

    breaking_keywords = [
        "breaking", "urgent", "attack", "strike", "explosion",
        "drone", "missile", "killed", "dies", "death", "war",
        "earthquake", "fire", "crisis", "election", "president",
        "government", "security", "هێرش", "تەقینەوە", "درۆن",
        "مووشەک", "کوژراو", "مردن", "جەنگ", "هەڵبژاردن",
        "حکومەت", "ئاسایش", "فۆری"
    ]

    for keyword in iraq_keywords:
        if keyword in text:
            score += 22

    for keyword in breaking_keywords:
        if keyword in text:
            score += 8

    age = news.get("age_hours", 24)

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
        "Rudaw", "Kurdistan24", "NRT", "BasNews",
        "Shafaq News", "Iraqi News", "Iraq News"
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
            if calculate_news_score(item) > calculate_news_score(unique[key]):
                unique[key] = item

    return list(unique.values())


def collect_news():
    all_news = []

    for source in RSS_SOURCES:
        all_news.extend(fetch_source(source))
        time.sleep(0.35)

    print("=" * 64)
    print(f"✅ کۆی هەواڵی نوێ: {len(all_news)}")

    all_news = deduplicate_news(all_news)

    for item in all_news:
        item["score"] = calculate_news_score(item)

    all_news.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    candidates = all_news[:MAX_CANDIDATES]

    print("\n📊 هەواڵە بەرزترینەکان:")

    for i, item in enumerate(candidates[:15], 1):
        print(
            f"{i}. [{item['source']}] "
            f"{item['title']} | score={item['score']:.1f}"
        )

    return candidates


# ============================================================
# 🤖 GEMINI
# ============================================================

def generate_kurdish_news(candidates):
    if not candidates:
        return None

    candidate_text = ""

    for i, item in enumerate(candidates, 1):
        candidate_text += (
            f"\n\nSOURCE_NUMBER: {i}\n"
            f"SOURCE: {item['source']}\n"
            f"TITLE: {item['title']}\n"
            f"SUMMARY: {item['summary'][:1400]}\n"
            f"URL: {item['link']}\n"
        )

    prompt = f"""
تۆ نووسەر و هەڵبژێری هەواڵی پەیجی ASO NEWS ـیت.

یاساکانی هەڵبژاردن:
1. هەواڵی تازە و گرنگ هەڵبژێرە.
2. هەواڵی کوردستان پێش هەواڵی جیهانیە.
3. دوای کوردستان، هەواڵی عێراق پێش هەواڵی ناوچەیی و جیهانیە.
4. هەواڵی جیهانی تەنها کاتێک هەڵبژێرە کە هەواڵی گرنگی کوردستان/عێراق نەبێت.
5. هیچ زانیارییەکی لە سەرچاوەکەدا نییە زیاد مەکە.
6. شیکاری سیاسی، پێشبینی و بۆچوون زیاد مەکە.
7. ناوی کەس و شوێن بە دروستی بنووسە.
8. هەواڵەکە بە کوردی سۆرانییەکی پاک و پیشەیی بنووسە.

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

    try:
        print("\n" + "=" * 64)
        print("🤖 GEMINI")

        response = client.models.generate_content(
            model=GEMINI_TEXT_MODEL,
            contents=prompt
        )

        text = (response.text or "").strip()

        if not text:
            print("❌ Gemini هیچ وەڵامێکی نەدا.")
            return None

        print(text)

        match = re.search(
            r"SOURCE_NUMBER\s*:\s*(\d+)",
            text,
            re.IGNORECASE
        )

        source_number = int(match.group(1)) if match else 1

        if not 1 <= source_number <= len(candidates):
            source_number = 1

        selected = candidates[source_number - 1].copy()

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
            clean_text(title_match.group(1))
            if title_match
            else clean_text(selected["title"])
        )

        selected["body"] = (
            clean_text(body_match.group(1))
            if body_match
            else clean_text(selected["summary"])
        )

        selected["full_body"] = (
            clean_text(full_body_match.group(1))
            if full_body_match
            else selected["body"]
        )

        selected["hashtags"] = (
            clean_text(hashtags_match.group(1))
            if hashtags_match
            else "#ASONEWS #کوردستان #عێراق"
        )

        if "#ASONEWS" not in selected["hashtags"]:
            selected["hashtags"] += " #ASONEWS"

        if "کوردستان" not in selected["hashtags"] and "Kurdistan" not in selected["hashtags"]:
            selected["hashtags"] += " #کوردستان"

        if "عێراق" not in selected["hashtags"] and "Iraq" not in selected["hashtags"]:
            selected["hashtags"] += " #عێراق"

        return selected

    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return None


# ============================================================
# 📝 FACEBOOK TEXT
# ============================================================

def build_post(news):
    title = clean_text(news.get("kur_title", news.get("title", "")))
    body = clean_text(news.get("body", ""))
    hashtags = clean_text(
        news.get("hashtags", "#ASONEWS #کوردستان #عێراق")
    )
    source = clean_text(news.get("source", ""))

    return (
        f"📰 {title}\n\n"
        f"{body}\n\n"
        f"{hashtags}\n\n"
        f"سەرچاوە: {source}"
    )


def build_first_comment(news):
    full_body = clean_text(
        news.get("full_body", news.get("body", ""))
    )
    source = clean_text(news.get("source", ""))
    link = clean_text(news.get("link", ""))

    if not full_body:
        full_body = clean_text(news.get("body", ""))

    comment = (
        "📌 درێژەی هەواڵ:\n\n"
        f"{full_body}\n\n"
        f"سەرچاوە: {source}"
    )
    if link and link.startswith("http"):
        comment += f"\n🔗 {link}"
    return comment


# ============================================================
# 🌐 ARTICLE PAGE
# ============================================================

def get_article_page(url):
    if not url:
        return ""

    try:
        response = session.get(
            url,
            timeout=25,
            allow_redirects=True,
            headers={"Accept": "text/html,application/xhtml+xml"}
        )

        if response.status_code != 200:
            return ""

        return response.text

    except Exception as e:
        print(f"⚠️ article page error: {e}")
        return ""

def get_article_images(article_url):
    """Collect likely article images, including the final redirected article URL."""
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
            headers={"Accept": "text/html,application/xhtml+xml"}
        )
        if response.status_code == 200:
            page = response.text
            final_url = response.url or article_url
    except Exception as e:
        print(f"⚠️ redirect/article error: {e}")

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
        for match in re.findall(pattern, page, re.IGNORECASE):
            image_url = urljoin(final_url, html.unescape(match.strip()))
            if image_url.startswith("http") and image_url not in images:
                images.append(image_url)

    try:
        html_images = re.findall(
            r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)',
            page,
            re.IGNORECASE
        )
        for image_url in html_images:
            image_url = urljoin(final_url, html.unescape(image_url.strip()))
            if image_url.startswith("http") and image_url not in images:
                images.append(image_url)
    except Exception:
        pass

    return images[:80]

def download_image_candidates(candidates):
    """Download images and reject icons, placeholders and tiny/irrelevant assets."""
    best = None
    checked = set()
    bad_words = (
        "logo", "icon", "avatar", "favicon", "placeholder",
        "default", "sprite", "profile", "blank", "dailyfeed"
    )

    for image_url in candidates:
        if not image_url or image_url in checked:
            continue
        checked.add(image_url)

        try:
            print(f"🔎 پشکنینی وێنە: {image_url}")
            low_url = image_url.lower()
            if any(word in low_url for word in bad_words):
                print("↪️ وێنەکە وەک logo/icon/placeholder ڕەتکرایەوە.")
                continue

            response = session.get(
                image_url,
                timeout=25,
                allow_redirects=True,
                headers={"Accept": "image/avif,image/webp,image/jpeg,image/png,*/*"}
            )
            if response.status_code != 200:
                continue

            content_type = response.headers.get("content-type", "").lower()
            if "image" not in content_type:
                continue

            data = response.content
            if len(data) < 30_000:
                continue

            image = Image.open(BytesIO(data)).convert("RGB")
            width, height = image.size
            if width < 800 or height < 450:
                continue

            aspect = width / height
            # Strongly prefer normal news photos; reject obvious banners/square assets.
            if aspect < 1.15 or aspect > 2.40:
                continue

            # Reject almost-empty images by checking simple variance.
            small = image.resize((32, 32))
            pixels = list(small.getdata())
            avg = tuple(sum(p[i] for p in pixels) / len(pixels) for i in range(3))
            variance = sum(
                (sum(abs(p[i] - avg[i]) for i in range(3)) / 3)
                for p in pixels
            ) / len(pixels)
            if variance < 5:
                continue

            score = (width * height) + (len(data) * 3) + (500_000 if 1.45 <= aspect <= 2.05 else 0)

            if best is None or score > best["score"]:
                best = {
                    "data": data,
                    "url": image_url,
                    "width": width,
                    "height": height,
                    "score": score,
                }

        except Exception as e:
            print(f"⚠️ image error: {e}")

    return best

def find_font(size, bold=False):
    bold_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]

    regular_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    paths = bold_paths if bold else regular_paths

    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# 🖼️ PROFESSIONAL ASO GRAPHIC
# ============================================================

def fit_cover(image, size):
    target_w, target_h = size
    src_w, src_h = image.size

    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        # Crop left/right.
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        image = image.crop(
            (left, 0, left + new_w, src_h)
        )
    else:
        # Crop top/bottom.
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        image = image.crop(
            (0, top, src_w, top + new_h)
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
            font=font
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


def add_professional_overlay(
    image_file,
    title,
    output_file=IMAGE_FILE
):
    try:
        image = Image.open(image_file).convert("RGB")
        image = fit_cover(image, (1200, 675))

        # Slight enhancement.
        image = ImageEnhance.Contrast(image).enhance(1.05)
        image = ImageEnhance.Color(image).enhance(1.05)

        overlay = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(overlay)

        width, height = image.size

        # Bottom dark gradient.
        gradient_height = 290

        for y in range(height - gradient_height, height):
            relative = (
                y - (height - gradient_height)
            ) / gradient_height

            alpha = int(20 + 205 * relative)

            draw.line(
                [(0, y), (width, y)],
                fill=(0, 0, 0, alpha)
            )

        # Thin ASO red line.
        draw.rectangle(
            [0, 0, width, 10],
            fill=(220, 30, 45, 255)
        )

        title_font = find_font(46, bold=True)
        brand_font = find_font(28, bold=True)

        title = clean_text(title)

        # Keep the title readable without covering the whole image.
        lines = wrap_text(
            draw,
            title,
            title_font,
            width - 110
        )

        lines = lines[:4]

        # Title box.
        line_height = 60
        box_height = (
            len(lines) * line_height
            + 90
        )

        box_top = height - box_height - 35

        draw.rounded_rectangle(
            [
                35,
                box_top,
                width - 35,
                height - 25
            ],
            radius=22,
            fill=(12, 12, 16, 175),
            outline=(220, 30, 45, 230),
            width=3
        )

        # Title.
        y = box_top + 35

        for line in lines:
            draw.text(
                (width - 60, y),
                line,
                font=title_font,
                fill=(255, 255, 255, 255),
                anchor="ra",
                stroke_width=1,
                stroke_fill=(0, 0, 0, 220)
            )

            y += line_height

        # Brand.
        draw.text(
            (55, height - 58),
            "ASO NEWS",
            font=brand_font,
            fill=(220, 30, 45, 255),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 180)
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

        print("✅ وێنەی پڕۆفیشنالی ASO NEWS ئامادە کرا.")
        return output_file

    except Exception as e:
        print(f"⚠️ professional graphic error: {e}")
        return image_file


# ============================================================
# 🖼️ WATERMARK
# ============================================================

def add_watermark(image_file):
    if not os.path.exists(LOGO_FILE):
        print("⚠️ logo.png نەدۆزرایەوە.")
        return image_file

    try:
        image = Image.open(image_file).convert("RGBA")
        logo = Image.open(LOGO_FILE).convert("RGBA")

        max_logo_width = int(image.width * 0.15)
        max_logo_height = int(image.height * 0.15)

        logo.thumbnail(
            (max_logo_width, max_logo_height),
            Image.LANCZOS
        )

        alpha = logo.getchannel("A")
        alpha = ImageEnhance.Contrast(alpha).enhance(1.20)
        alpha = alpha.point(
            lambda p: min(255, int(p * 0.90))
        )

        logo.putalpha(alpha)

        margin = 24

        x = image.width - logo.width - margin
        y = image.height - logo.height - margin

        image.alpha_composite(logo, (x, y))

        image.convert("RGB").save(
            image_file,
            "JPEG",
            quality=95,
            optimize=True
        )

        print("✅ لۆگۆی ASO NEWS زیاد کرا.")
        return image_file

    except Exception as e:
        print(f"⚠️ watermark error: {e}")
        return image_file


# ============================================================
# 🖼️ IMAGE PIPELINE — REAL PHOTO → NANO BANANA PRO
# ============================================================

def create_ai_news_image(news, filename=IMAGE_FILE):
    """Generate a high-quality editorial news visual with Nano Banana Pro.

    Important design rule: Gemini creates ONLY the visual. It must not create
    ASO NEWS branding, logos, captions, fake UI, or headline text. The single
    official logo is added later by add_watermark().
    """
    title = clean_text(news.get("kur_title", news.get("title", "NEWS")))
    body = clean_text(news.get("body", news.get("summary", "")))
    source = clean_text(news.get("source", ""))
    article_url = clean_text(news.get("link", ""))

    # Keep the prompt focused. Gemini 3 image models work best with clear,
    # direct instructions rather than a long list of conflicting constraints.
    prompt = f"""
Create a premium editorial news photograph for a Kurdish digital news outlet.

Story headline:
{title}

Story summary:
{body}

Source:
{source}

Reference article:
{article_url}

Visual direction:
- Create a believable, photorealistic editorial-news scene that clearly
  communicates the story above.
- Treat the image as an editorial reconstruction, NOT as a claim that this is
  an exact photograph of the real event.
- If the story involves officials or political meetings, show a realistic
  government/meeting environment, podium, conference table, security setting,
  vehicles, government buildings, or other relevant contextual visuals instead
  of inventing a recognizable person's face.
- If a person must appear, keep them generic/unidentifiable unless the prompt
  explicitly provides a reference image.
- Premium international-news photography look: realistic lens, natural skin
  and materials, believable lighting, documentary composition, crisp detail,
  subtle depth of field, restrained color grading.
- Strong focal subject, clean hierarchy, and visual storytelling suitable for
  a professional Facebook news post.
- 16:9 landscape.

Absolutely do not include:
- any words, letters, headlines, captions, numbers, signs, or readable text
- any logo, watermark, ASO NEWS mark, brand mark, badge, UI, screenshot,
  social-media frame, poster layout, or template
- fake news-channel graphics or decorative title boxes
- exaggerated fantasy/cinematic effects

The final output must look like a high-end editorial news photograph, not a
Canva template or generic graphic.
""".strip()

    for attempt in range(1, 3):
        try:
            print("\n" + "=" * 64)
            print(f"🎨 NANO BANANA PRO — IMAGE ATTEMPT {attempt}/2")
            print(f"🎨 IMAGE MODEL: {GEMINI_IMAGE_MODEL}")

            interaction = client.interactions.create(
                model=GEMINI_IMAGE_MODEL,
                input=prompt,
                tools=[{"type": "google_search"}],
                response_format={
                    "type": "image",
                    "aspect_ratio": "16:9",
                    "image_size": "2K",
                },
            )

            output_image = getattr(interaction, "output_image", None)
            image_data = getattr(output_image, "data", None)

            if not image_data:
                print("⚠️ Nano Banana Pro بەڵگەی وێنەی نەگەڕاندەوە.")
                continue

            if isinstance(image_data, str):
                image_data = base64.b64decode(image_data)

            with Image.open(BytesIO(image_data)) as generated:
                generated = generated.convert("RGB")
                generated = fit_cover(generated, (1200, 675))
                generated.save(filename, "JPEG", quality=96, optimize=True)

            # Verify the file can be reopened after saving.
            with Image.open(filename) as check:
                check.verify()

            print("✅ Nano Banana Pro وێنەی پڕۆفیشنالی دروست کرد.")
            return filename

        except Exception as e:
            print(f"⚠️ Nano Banana Pro image error (attempt {attempt}): {e}")
            if attempt < 2:
                time.sleep(3)

    print("❌ دوو هەوڵی Nano Banana Pro سەرکەوتوو نەبوون.")
    return None

def prepare_image(news):
    candidates = []

    # Prefer article/RSS images, but reject obvious generic assets.
    if news.get("image_url"):
        candidates.append(news["image_url"])

    article_url = news.get("link")
    if article_url:
        try:
            candidates.extend(get_article_images(article_url))
        except Exception:
            pass

    candidates = list(dict.fromkeys(candidates))

    print("\n" + "=" * 64)
    print("📸 بەدوای وێنەی ڕاستەقینە و گونجاودا دەگەڕێین...")

    best = download_image_candidates(candidates)

    if best:
        try:
            with open(IMAGE_FILE, "wb") as f:
                f.write(best["data"])

            print(f"📐 وێنە: {best['width']}x{best['height']}")

            image_file = add_professional_overlay(
                IMAGE_FILE,
                news.get("kur_title", news.get("title", "ASO NEWS"))
            )

        except Exception as e:
            print(f"⚠️ image save/overlay error: {e}")
            image_file = None
    else:
        print("⚠️ هیچ وێنەیەکی ڕاستەقینەی گونجاو نەدۆزرایەوە.")

        # Generate a real editorial visual with Nano Banana Pro.
        # Do NOT fall back to the old generic template: a bad visual is worse
        # than skipping the post.
        image_file = create_ai_news_image(news)

        if not image_file:
            print("❌ هیچ وێنەیەکی پڕۆفیشنالی بەردەست نییە؛ ئەم run ـە پۆست ناکرێت.")

    if image_file:
        image_file = add_watermark(image_file)

    return image_file


# ============================================================
# 📤 FACEBOOK PHOTO
# ============================================================

def publish_photo(message, image_file):
    if not image_file or not os.path.exists(image_file):
        print("❌ image file نەدۆزرایەوە.")
        return None

    print("\n" + "=" * 64)
    print("📘 FACEBOOK PHOTO POST")

    try:
        with open(image_file, "rb") as image:
            response = session.post(
                FACEBOOK_PHOTO_URL,
                data={
                    "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
                    "message": message,
                },
                files={
                    "source": (
                        os.path.basename(image_file),
                        image,
                        "image/jpeg"
                    )
                },
                timeout=60
            )

        print(f"Status: {response.status_code}")
        print(response.text)

        if response.status_code != 200:
            return None

        try:
            data = response.json()
        except Exception:
            data = {}

        post_id = data.get("post_id") or data.get("id")

        if post_id:
            print(f"✅ Facebook photo success: {post_id}")
            return post_id

    except Exception as e:
        print(f"❌ Facebook photo error: {e}")

    return None


# ============================================================
# 🎥 FACEBOOK VIDEO
# ============================================================

def publish_video(message, video_url):
    if not video_url:
        return None

    print("\n" + "=" * 64)
    print("🎥 VIDEO FOUND")
    print(video_url)

    try:
        response = session.post(
            FACEBOOK_VIDEO_URL,
            data={
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
                "file_url": video_url,
                "description": message,
            },
            timeout=90
        )

        print(f"Status: {response.status_code}")
        print(response.text)

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception:
                data = {}

            return data.get("id") or data.get("post_id")

    except Exception as e:
        print(f"⚠️ Facebook video error: {e}")

    return None


# ============================================================
# 💬 FIRST COMMENT
# ============================================================

def publish_first_comment(post_id, comment):
    """Publish the continuation as the first comment, with a safe retry strategy."""
    if not post_id or not comment:
        print("⚠️ post_id یان comment بەتاڵە.")
        return False

    print("\n" + "=" * 64)
    print("💬 FIRST COMMENT — دەستپێدەکات")

    post_ids = [str(post_id).strip()]
    # Some Facebook photo responses return the photo id instead of the feed post id.
    if "_" not in str(post_id):
        post_ids.append(f"{PAGE_ID}_{post_id}")

    for current_id in dict.fromkeys(post_ids):
        url = f"https://graph.facebook.com/{GRAPH_VERSION}/{current_id}/comments"
        try:
            response = session.post(
                url,
                data={
                    "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
                    "message": comment,
                },
                timeout=40,
            )

            print(f"Comment target: {current_id}")
            print(f"Comment status: {response.status_code}")
            print(f"Comment response: {response.text}")

            if response.status_code == 200:
                print("✅ کۆمێنتی یەکەم بە سەرکەوتوویی کرا.")
                return True

            try:
                error_data = response.json().get("error", {})
                message = error_data.get("message", response.text)
                code = error_data.get("code", "?")
                subcode = error_data.get("error_subcode", "?")
                print(f"❌ Facebook comment error: {message}")
                print(f"   code={code}, subcode={subcode}")
            except Exception:
                pass

        except Exception as e:
            print(f"⚠️ comment request error: {e}")

    print("❌ هیچ یەکێک لە هەوڵەکانی کۆمێنت سەرکەوتوو نەبوو.")
    print(
        "ℹ️ کۆدەکە تا ئەم خاڵە دروستە؛ Facebook ڕەتیکردووەتەوە. "
        "بۆ کۆمێنتکردن بە ناوی پەیج، Page Access Token دەبێت "
        "pages_manage_engagement هەبێت و Page task ـی MODERATE هەبێت."
    )
    print(
        "ℹ️ ئەمە بە گۆڕینی کۆد بە تەنیا چارەسەر نابێت؛ "
        "دەبێت token ـەکە بە permission ـە دروستەکان نوێ بکرێتەوە."
    )
    return False

def record_post(news, post_id):
    posted_news.append({
        "id": news.get("id"),
        "title": news.get("title", ""),
        "kur_title": news.get("kur_title", ""),
        "source": news.get("source", ""),
        "link": news.get("link", ""),
        "post_id": post_id,
        "timestamp": int(time.time()),
    })

    save_history(posted_news)


# ============================================================
# 🧹 OLD IMAGE
# ============================================================

def remove_old_image():
    try:
        if os.path.exists(IMAGE_FILE):
            os.remove(IMAGE_FILE)
    except Exception:
        pass


# ============================================================
# 🚀 MAIN
# ============================================================

def main():
    print("\n" + "=" * 64)
    print("🇮🇶 ASO NEWS — AUTO PUBLISHER v6")
    print("=" * 64)

    candidates = collect_news()

    if not candidates:
        print("⚠️ هیچ هەواڵێکی نوێ نەدۆزرایەوە.")
        return

    good_candidates = [
        item
        for item in candidates
        if item.get("score", 0) >= MIN_NEWS_SCORE
    ]

    if not good_candidates:
        good_candidates = candidates

    news = generate_kurdish_news(good_candidates)

    if not news:
        print("❌ Gemini نەیتوانی هەواڵ دروست بکات.")
        return

    final_post = build_post(news)
    first_comment = build_first_comment(news)

    print("\n" + "=" * 64)
    print("📰 ASO NEWS — FINAL POST")
    print("=" * 64)
    print(final_post)

    print("\n" + "=" * 64)
    print("💬 FIRST COMMENT")
    print("=" * 64)
    print(first_comment)

    remove_old_image()

    image_file = prepare_image(news)

    if not image_file and not news.get("video_url"):
        print("❌ وێنەی پڕۆفیشنالی بەردەست نییە؛ پۆستی بێ وێنە نانێرین.")
        return

    video_url = news.get("video_url")
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
        print("\n❌ پۆست نەکرا.")
        return

    print(f"\n✅ پۆست کرا: {post_id}")
    time.sleep(2)

    # First comment is attempted AFTER the post is confirmed.
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
    print("✅ ASO NEWS تەواو بوو.")
    print(f"🆔 POST ID: {post_id}")
    print(f"📰 SOURCE: {news.get('source', '')}")
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
