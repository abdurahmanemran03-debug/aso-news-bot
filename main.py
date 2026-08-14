import os
import json
import hashlib
import re
import html
import time
from urllib.parse import urljoin, quote

import requests
import feedparser

from PIL import (
    Image,
    ImageEnhance,
    ImageDraw,
    ImageFont
)

from io import BytesIO
from google import genai


# =========================================================
# 🇮🇶 ASO NEWS — AUTO PUBLISHER v4
# =========================================================

print("=" * 60)
print("🇮🇶 ASO NEWS — AUTO PUBLISHER v4")
print("=" * 60)


# =========================================================
# 🔐 ENVIRONMENT
# =========================================================

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY"
)

FACEBOOK_PAGE_ACCESS_TOKEN = os.environ.get(
    "FACEBOOK_PAGE_ACCESS_TOKEN"
)

if not GEMINI_API_KEY:
    raise RuntimeError(
        "❌ GEMINI_API_KEY نەدۆزرایەوە."
    )

if not FACEBOOK_PAGE_ACCESS_TOKEN:
    raise RuntimeError(
        "❌ FACEBOOK_PAGE_ACCESS_TOKEN نەدۆزرایەوە."
    )


# =========================================================
# ⚙️ CONFIGURATION
# =========================================================

PAGE_ID = "1128027710403407"

HISTORY_FILE = "posted_news.json"

LOGO_FILE = "logo.png"

IMAGE_FILE = "news_image.jpg"

MAX_HISTORY = 2000

MAX_CANDIDATES = 30

MIN_NEWS_SCORE = 8

# ئەو هەواڵانەی لەم ماوەیەدا زۆر کۆنترن، پشتگوێ دەخرێن
MAX_AGE_HOURS = 48

# هەر workflow ـێک تەنها یەک هەواڵ بڵاودەکاتەوە
POST_ONE_NEWS_PER_RUN = True

# Facebook Graph API
GRAPH_VERSION = "v23.0"

FACEBOOK_PHOTO_URL = (
    f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/photos"
)

FACEBOOK_VIDEO_URL = (
    f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/videos"
)

FACEBOOK_COMMENTS_URL = (
    f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/comments"
)


# =========================================================
# 🤖 GEMINI
# =========================================================

# ئەگەر لە GitHub Secret ـەکاندا GEMINI_MODEL دانرا،
# ئەوە بەکاری دەهێنێت.
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash"
)

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# 🌐 HTTP SESSION
# =========================================================

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


# =========================================================
# 📰 NEWS SOURCES
# =========================================================
#
# سەرچاوە ناوخۆییەکان priority ـی زۆرتریان هەیە.
#
# Google News RSS بەکاردهێنین بۆ ئەو سەرچاوانەی
# RSS ـی جێگیریان نییە.
# =========================================================

RSS_SOURCES = [

    # =====================================================
    # 🇮🇶 KURDISTAN / IRAQ
    # =====================================================

    {
        "name": "Rudaw",
        "priority": 30,
        "query": "site:rudaw.net Kurdistan OR Iraq",
    },

    {
        "name": "Kurdistan24",
        "priority": 30,
        "query": "site:kurdistan24.net Kurdistan OR Iraq",
    },

    {
        "name": "NRT",
        "priority": 29,
        "query": "site:nrt-news.com Kurdistan OR Iraq",
    },

    {
        "name": "BasNews",
        "priority": 29,
        "query": "site:basnews.com Kurdistan OR Iraq",
    },

    {
        "name": "Shafaq News",
        "priority": 28,
        "query": "site:shafaq.com Iraq OR Kurdistan",
    },

    {
        "name": "Iraqi News",
        "priority": 26,
        "query": "Iraq latest news Kurdistan",
    },

    {
        "name": "Iraq News",
        "priority": 25,
        "query": "site:iraqinews.com Iraq OR Kurdistan",
    },

    # =====================================================
    # 🌍 MIDDLE EAST / INTERNATIONAL
    # =====================================================

    {
        "name": "Al Jazeera",
        "priority": 18,
        "query": "site:aljazeera.com Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "Reuters",
        "priority": 18,
        "query": "site:reuters.com Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "Associated Press",
        "priority": 17,
        "query": "site:apnews.com Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "BBC News",
        "priority": 16,
        "query": "site:bbc.com/news Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "DW",
        "priority": 14,
        "query": "site:dw.com Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "France 24",
        "priority": 14,
        "query": "site:france24.com Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "VOA",
        "priority": 13,
        "query": "site:voanews.com Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "Anadolu Agency",
        "priority": 13,
        "query": "site:aa.com.tr Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "The Guardian",
        "priority": 10,
        "query": "site:theguardian.com Iraq OR Kurdistan OR Middle East",
    },

    {
        "name": "NPR",
        "priority": 9,
        "query": "site:npr.org Iraq OR Kurdistan OR Middle East",
    },
]


# =========================================================
# 🔗 GOOGLE NEWS RSS
# =========================================================

def build_google_news_rss(query):

    encoded = quote(query)

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )


# =========================================================
# 📚 HISTORY
# =========================================================

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

        if isinstance(data, list):
            return data

    except Exception as e:

        print(
            f"⚠️ history error: {e}"
        )

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
            f"💾 history پاشەکەوت کرا: {len(history)}"
        )

    except Exception as e:

        print(
            f"⚠️ نەتوانرا history پاشەکەوت بکرێت: {e}"
        )


posted_news = load_history()


# =========================================================
# 🧹 TEXT CLEANING
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(
        str(text)
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# 🆔 NEWS ID
# =========================================================

def create_news_id(
    title,
    link
):

    title = clean_text(title)

    normalized_title = re.sub(
        r"\s+",
        " ",
        title.lower()
    ).strip()

    link = (
        link.strip()
        if link
        else ""
    )

    base = (
        link
        if link
        else normalized_title
    )

    return hashlib.sha256(
        (
            base
            + "|"
            + normalized_title
        ).encode(
            "utf-8"
        )
    ).hexdigest()


# =========================================================
# 🔍 HISTORY CHECK
# =========================================================

def is_already_posted(news_id):

    for item in posted_news:

        if isinstance(item, str):

            if item == news_id:
                return True

        elif isinstance(item, dict):

            if (
                item.get("id")
                == news_id
            ):
                return True

    return False


# =========================================================
# 🕐 PARSE DATE
# =========================================================

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


# =========================================================
# 🖼️ RSS IMAGE
# =========================================================

def get_rss_image(entry):

    try:

        media_content = entry.get(
            "media_content"
        )

        if media_content:

            for media in media_content:

                url = media.get("url")

                if url:
                    return url

        media_thumbnail = entry.get(
            "media_thumbnail"
        )

        if media_thumbnail:

            for media in media_thumbnail:

                url = media.get("url")

                if url:
                    return url

        enclosures = entry.get(
            "enclosures"
        )

        if enclosures:

            for enclosure in enclosures:

                url = (
                    enclosure.get("href")
                    or enclosure.get("url")
                )

                if url:
                    return url

        raw = (
            str(entry.get("summary", ""))
            + " "
            + str(entry.get("description", ""))
        )

        if entry.get("content"):

            raw += " " + str(
                entry.get("content")[0].get(
                    "value",
                    ""
                )
            )

        matches = re.findall(
            r'<img[^>]+src=["\']([^"\']+)',
            raw,
            re.IGNORECASE
        )

        if matches:
            return matches[0]

    except Exception:
        pass

    return None


# =========================================================
# 📹 RSS VIDEO
# =========================================================

def get_video_url(entry):

    try:

        media_content = entry.get(
            "media_content"
        )

        if media_content:

            for media in media_content:

                url = media.get("url")

                media_type = (
                    media.get(
                        "type",
                        ""
                    )
                    .lower()
                )

                if (
                    url
                    and (
                        "video" in media_type
                        or url.lower().endswith(
                            (
                                ".mp4",
                                ".mov",
                                ".webm",
                                ".m4v"
                            )
                        )
                    )
                ):

                    return url

        enclosures = entry.get(
            "enclosures"
        )

        if enclosures:

            for enclosure in enclosures:

                url = (
                    enclosure.get("href")
                    or enclosure.get("url")
                )

                media_type = (
                    enclosure.get(
                        "type",
                        ""
                    )
                    .lower()
                )

                if (
                    url
                    and "video" in media_type
                ):

                    return url

    except Exception:
        pass

    return None


# =========================================================
# 🌐 ARTICLE PAGE
# =========================================================

def get_article_page(
    article_url
):

    if not article_url:
        return ""

    try:

        response = session.get(
            article_url,
            timeout=20,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        return response.text

    except Exception as e:

        print(
            f"⚠️ article page error: {e}"
        )

        return ""


# =========================================================
# 🖼️ ARTICLE IMAGES
# =========================================================

def get_article_images(
    article_url
):

    page = get_article_page(
        article_url
    )

    if not page:
        return []

    images = []

    patterns = [

        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',

        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:

        try:

            matches = re.findall(
                pattern,
                page,
                re.IGNORECASE
            )

            for match in matches:

                image_url = html.unescape(
                    match.strip()
                )

                image_url = urljoin(
                    article_url,
                    image_url
                )

                if (
                    image_url.startswith(
                        "http"
                    )
                    and image_url
                    not in images
                ):

                    images.append(
                        image_url
                    )

        except Exception:
            pass

    # HTML images
    try:

        html_images = re.findall(
            r'<img[^>]+(?:src|data-src)=["\']([^"\']+)',
            page,
            re.IGNORECASE
        )

        for image_url in html_images:

            image_url = html.unescape(
                image_url.strip()
            )

            image_url = urljoin(
                article_url,
                image_url
            )

            if (
                image_url.startswith(
                    "http"
                )
                and image_url
                not in images
            ):

                images.append(
                    image_url
                )

    except Exception:
        pass

    return images[:40]


# =========================================================
# 🖼️ DOWNLOAD BEST IMAGE
# =========================================================

def download_best_image(
    candidates,
    filename=IMAGE_FILE
):

    best = None

    checked = set()

    for image_url in candidates:

        if not image_url:
            continue

        if image_url in checked:
            continue

        checked.add(
            image_url
        )

        try:

            print(
                f"🔎 پشکنینی وێنە: {image_url}"
            )

            response = session.get(
                image_url,
                timeout=20,
                allow_redirects=True
            )

            if response.status_code != 200:
                continue

            content_type = (
                response.headers.get(
                    "content-type",
                    ""
                ).lower()
            )

            if (
                "image"
                not in content_type
            ):
                continue

            data = response.content

            if len(data) < 20_000:
                continue

            image = Image.open(
                BytesIO(data)
            )

            width, height = image.size

            if (
                width < 700
                or height < 400
            ):
                continue

            aspect = (
                width / height
                if height
                else 0
            )

            # Landscape ـەکان پێشینەیان هەیە
            landscape_bonus = (
                2.0
                if 1.30 <= aspect <= 2.20
                else 1.0
            )

            # وێنەی زۆر باریک پشتگوێ دەخرێت
            portrait_penalty = (
                0.25
                if aspect < 0.90
                else 1.0
            )

            score = (
                width
                * height
                * landscape_bonus
                * portrait_penalty
                + len(data) / 100
            )

            if (
                best is None
                or score > best["score"]
            ):

                best = {
                    "url": image_url,
                    "data": data,
                    "width": width,
                    "height": height,
                    "score": score
                }

        except Exception as e:

            print(
                f"⚠️ image error: {e}"
            )

    if best is None:

        print(
            "❌ هیچ وێنەیەکی گونجاو نەدۆزرایەوە."
        )

        return None

    try:

        image = Image.open(
            BytesIO(
                best["data"]
            )
        )

        if image.mode != "RGB":

            image = image.convert(
                "RGB"
            )

        image.save(
            filename,
            "JPEG",
            quality=94,
            optimize=True
        )

        print(
            "\n✅ باشترین وێنە:"
        )

        print(
            f"📐 {best['width']}x{best['height']}"
        )

        print(
            f"💾 {len(best['data']) / 1024:.1f} KB"
        )

        return filename

    except Exception as e:

        print(
            f"❌ نەتوانرا وێنە پاشەکەوت بکرێت: {e}"
        )

        return None


# =========================================================
# 🖼️ WATERMARK
# =========================================================

def add_watermark(
    image_file
):

    if not os.path.exists(
        LOGO_FILE
    ):

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

        # logo ـەکە کەمێک گەورەتر دەکەین
        max_logo_width = int(
            image.width * 0.16
        )

        max_logo_height = int(
            image.height * 0.16
        )

        logo.thumbnail(
            (
                max_logo_width,
                max_logo_height
            ),
            Image.LANCZOS
        )

        # ڕوونی watermark
        alpha = logo.getchannel(
            "A"
        )

        alpha = ImageEnhance.Contrast(
            alpha
        ).enhance(
            1.25
        )

        # opacity ـی زۆر کەم نەبێت
        alpha = alpha.point(
            lambda p: min(
                255,
                int(p * 0.90)
            )
        )

        logo.putalpha(
            alpha
        )

        margin = 28

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

        image = image.convert(
            "RGB"
        )

        image.save(
            image_file,
            "JPEG",
            quality=95,
            optimize=True
        )

        print(
            "✅ لۆگۆ بە watermark ـی پاک زیاد کرا."
        )

        return image_file

    except Exception as e:

        print(
            f"⚠️ watermark error: {e}"
        )

        return image_file


# =========================================================
# 🖼️ FALLBACK IMAGE
# =========================================================

def create_fallback_image(
    title,
    filename=IMAGE_FILE
):

    try:

        width = 1200
        height = 675

        image = Image.new(
            "RGB",
            (
                width,
                height
            ),
            (18, 18, 22)
        )

        draw = ImageDraw.Draw(
            image
        )

        # -------------------------------------------------
        # FONT
        # -------------------------------------------------

        bold_font = None

        regular_font = None

        bold_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]

        regular_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

        for path in bold_paths:

            if os.path.exists(path):

                try:

                    bold_font = ImageFont.truetype(
                        path,
                        55
                    )

                    break

                except Exception:
                    pass

        for path in regular_paths:

            if os.path.exists(path):

                try:

                    regular_font = ImageFont.truetype(
                        path,
                        28
                    )

                    break

                except Exception:
                    pass

        if bold_font is None:
            bold_font = ImageFont.load_default()

        if regular_font is None:
            regular_font = ImageFont.load_default()

        # -------------------------------------------------
        # BACKGROUND
        # -------------------------------------------------

        draw.rectangle(
            [
                0,
                0,
                width,
                height
            ],
            fill=(18, 18, 22)
        )

        # red bars
        draw.rectangle(
            [
                0,
                0,
                width,
                12
            ],
            fill=(220, 30, 45)
        )

        draw.rectangle(
            [
                0,
                height - 12,
                width,
                height
            ],
            fill=(220, 30, 45)
        )

        # -------------------------------------------------
        # BRAND
        # -------------------------------------------------

        draw.text(
            (
                70,
                80
            ),
            "ASO NEWS",
            fill=(255, 255, 255),
            font=bold_font
        )

        draw.text(
            (
                73,
                150
            ),
            "KURDISTAN • IRAQ • WORLD",
            fill=(220, 30, 45),
            font=regular_font
        )

        # -------------------------------------------------
        # NEWS
        # -------------------------------------------------

        draw.rounded_rectangle(
            [
                70,
                235,
                width - 70,
                475
            ],
            radius=25,
            fill=(30, 30, 36),
            outline=(220, 30, 45),
            width=3
        )

        draw.text(
            (
                110,
                285
            ),
            "هەواڵی نوێ",
            fill=(255, 255, 255),
            font=bold_font
        )

        draw.text(
            (
                110,
                365
            ),
            "ASO NEWS",
            fill=(220, 30, 45),
            font=bold_font
        )

        # -------------------------------------------------
        # FOOTER
        # -------------------------------------------------

        draw.text(
            (
                70,
                height - 80
            ),
            "هەواڵ بەخێرایی",
            fill=(240, 240, 240),
            font=regular_font
        )

        image.save(
            filename,
            "JPEG",
            quality=95,
            optimize=True
        )

        print(
            "✅ fallback image دروست کرا."
        )

        return filename

    except Exception as e:

        print(
            f"❌ fallback error: {e}"
        )

        return None


# =========================================================
# 📰 FETCH SOURCE
# =========================================================

def fetch_source(
    source
):

    print("=" * 60)

    print(
        f"🔎 سەرچاوە: {source['name']}"
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
                f"⚠️ RSS status: {response.status_code}"
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

            if not title:
                continue

            if not link:
                continue

            published_time = get_entry_time(
                entry
            )

            age_hours = (
                time.time()
                - published_time
            ) / 3600

            if (
                age_hours > MAX_AGE_HOURS
                and published_time
                > 0
            ):
                continue

            image_url = get_rss_image(
                entry
            )

            video_url = get_video_url(
                entry
            )

            news_id = create_news_id(
                title,
                link
            )

            if is_already_posted(
                news_id
            ):
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

                "image_url": image_url,

                "video_url": video_url,

            })

        print(
            f"📰 {len(items)} هەواڵ"
        )

        return items

    except Exception as e:

        print(
            f"❌ RSS error: {e}"
        )

        return []


# =========================================================
# 🧠 NEWS SCORING
# =========================================================

def calculate_news_score(
    news
):

    title = (
        news.get(
            "title",
            ""
        )
        .lower()
    )

    summary = (
        news.get(
            "summary",
            ""
        )
        .lower()
    )

    text = (
        title
        + " "
        + summary
    )

    score = float(
        news.get(
            "priority",
            0
        )
    )

    # =====================================================
    # 🇮🇶 IRAQ
    # =====================================================

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
        "کرکوک",
    ]

    for keyword in iraq_keywords:

        if keyword in text:
            score += 18

    # =====================================================
    # 🔥 BREAKING / IMPORTANT
    # =====================================================

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
        "breaking news",
        "فۆری",
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
    ]

    for keyword in breaking_keywords:

        if keyword in text:
            score += 10

    # =====================================================
    # 📈 FRESHNESS
    # =====================================================

    age = news.get(
        "age_hours",
        24
    )

    if age < 2:
        score += 15

    elif age < 6:
        score += 10

    elif age < 12:
        score += 6

    elif age < 24:
        score += 3

    # =====================================================
    # 📸 IMAGE
    # =====================================================

    if news.get(
        "image_url"
    ):
        score += 5

    # =====================================================
    # 🎥 VIDEO
    # =====================================================

    if news.get(
        "video_url"
    ):
        score += 12

    # =====================================================
    # 📰 SOURCE BONUS
    # =====================================================

    preferred_sources = [
        "Rudaw",
        "Kurdistan24",
        "NRT",
        "BasNews",
        "Shafaq News",
        "Iraqi News",
        "Iraq News",
    ]

    if news.get(
        "source"
    ) in preferred_sources:

        score += 10

    return score


# =========================================================
# 🔄 DEDUPLICATE CANDIDATES
# =========================================================

def deduplicate_news(
    items
):

    unique = {}

    for item in items:

        title = re.sub(
            r"[^a-zA-Z0-9\u0600-\u06FF]+",
            " ",
            item["title"].lower()
        ).strip()

        key = (
            title[:160]
        )

        if key not in unique:

            unique[key] = item

        else:

            # هەواڵەکەی score ـی بەرزتر هەڵبژێرە
            old_score = calculate_news_score(
                unique[key]
            )

            new_score = calculate_news_score(
                item
            )

            if new_score > old_score:

                unique[key] = item

    return list(
        unique.values()
    )


# =========================================================
# 🎯 COLLECT NEWS
# =========================================================

def collect_news():

    all_news = []

    for source in RSS_SOURCES:

        items = fetch_source(
            source
        )

        all_news.extend(
            items
        )

        # کەمێک interval بۆ RSS
        time.sleep(
            0.4
        )

    print("=" * 60)

    print(
        f"✅ کۆی هەواڵی نوێ: {len(all_news)}"
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

    candidates = all_news[
        :MAX_CANDIDATES
    ]

    print(
        "\n🎯 هەواڵە بەرزترینەکان:"
    )

    for index, item in enumerate(
        candidates[:20],
        start=1
    ):

        print(
            f"{index}. "
            f"[{item['source']}] "
            f"{item['title']}"
            f" | score={item['score']:.1f}"
        )

    return candidates


# =========================================================
# 🤖 GEMINI — KURDISH NEWS WRITER
# =========================================================

def generate_kurdish_news(
    candidates
):

    if not candidates:
        return None

    candidate_text = ""

    for i, item in enumerate(
        candidates,
        start=1
    ):

        candidate_text += (
            f"\n\nSOURCE_NUMBER: {i}\n"
            f"SOURCE: {item['source']}\n"
            f"TITLE: {item['title']}\n"
            f"SUMMARY: {item['summary'][:1200]}\n"
            f"URL: {item['link']}\n"
        )

    prompt = f"""
تۆ دەستیارێکی پیشەیی بۆ پەیجی هەواڵی ASO NEWS ـیت.

ئەرک:
لە نێوان هەواڵەکانی خوارەوەدا تەنها یەک هەواڵ هەڵبژێرە کە:
1. زۆرترین گرنگی هەبێت.
2. تازە بێت.
3. ئەگەر هەواڵی گرنگی کوردستان یان عێراق هەیە،
   پێش هەواڵی جیهانی هەڵیبژێرە.
4. دووبارە نەبێت.
5. هەواڵێکی ڕاستەقینە و پشت بە سەرچاوە ببەستێت.

پاشان هەواڵەکە بە زمانی کوردی سۆرانییەکی ڕوون و پیشەیی بنووسە.

هیچ شتێک زیاد مەکە کە لە سەرچاوەکەدا نییە.
هیچ پێشبینی یان شیکاری سیاسی مەکە.
ناوی کەسان و شوێنەکان بە دروستی بنووسە.

ئەگەر هەواڵەکە سیاسییە:
تەنها ڕاپۆرتی هەواڵەکە بنووسە، شیکاری مەکە.

OUTPUT ـەکە تەنها بە ئەم شێوەیە بێت:

SOURCE_NUMBER: 1

TITLE:
ناونیشانی کوردی

BODY:
پوختەی کورت، ڕوون و سەرنجڕاکێش، 2 تا 4 ڕستە.

FULL_BODY:
وردەکاری زیاتر، 2 تا 5 پاراگرافی کورت.

HASHTAGS:
#ASONEWS #کوردستان #عێراق

SOURCE:
ناوی سەرچاوە

هەواڵەکان:
{candidate_text}
"""

    try:

        print(
            "\n============================================================"
        )

        print(
            "🤖 GEMINI"
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        text = (
            response.text
            if response
            else ""
        )

        text = text.strip()

        if not text:

            print(
                "❌ Gemini هیچ وەڵامێکی نەدا."
            )

            return None

        print(
            text
        )

        # -------------------------------------------------
        # SOURCE NUMBER
        # -------------------------------------------------

        match = re.search(
            r"SOURCE_NUMBER\s*:\s*(\d+)",
            text,
            re.IGNORECASE
        )

        if not match:

            print(
                "⚠️ SOURCE_NUMBER نەدۆزرایەوە."
            )

            source_number = 1

        else:

            source_number = int(
                match.group(1)
            )

        if (
            source_number < 1
            or source_number > len(
                candidates
            )
        ):

            source_number = 1

        selected = candidates[
            source_number - 1
        ].copy()

        # -------------------------------------------------
        # PARSE TITLE
        # -------------------------------------------------

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

        if title_match:

            selected["kur_title"] = clean_text(
                title_match.group(1)
            )

        else:

            selected["kur_title"] = clean_text(
                selected["title"]
            )

        if body_match:

            selected["body"] = clean_text(
                body_match.group(1)
            )

        else:

            selected["body"] = clean_text(
                selected["summary"]
            )

        if full_body_match:

            selected["full_body"] = clean_text(
                full_body_match.group(1)
            )

        else:

            selected["full_body"] = selected[
                "body"
            ]

        if hashtags_match:

            selected["hashtags"] = clean_text(
                hashtags_match.group(1)
            )

        else:

            selected["hashtags"] = (
                "#ASONEWS #کوردستان #عێراق"
            )

        # -------------------------------------------------
        # Ensure hashtags
        # -------------------------------------------------

        if "#ASONEWS" not in selected[
            "hashtags"
        ]:

            selected["hashtags"] += (
                " #ASONEWS"
            )

        if (
            "کوردستان"
            not in selected["hashtags"]
            and
            "Kurdistan"
            not in selected["hashtags"]
        ):

            selected["hashtags"] += (
                " #کوردستان"
            )

        if (
            "عێراق"
            not in selected["hashtags"]
            and
            "Iraq"
            not in selected["hashtags"]
        ):

            selected["hashtags"] += (
                " #عێراق"
            )

        return selected

    except Exception as e:

        print(
            f"❌ Gemini error: {e}"
        )

        return None


# =========================================================
# 📝 BUILD FACEBOOK POST
# =========================================================

def build_post(
    news
):

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

    post = (
        f"📰 {title}\n\n"
        f"{body}\n\n"
        f"{hashtags}\n\n"
        f"سەرچاوە: {source}"
    )

    return post


# =========================================================
# 💬 FIRST COMMENT
# =========================================================

def build_first_comment(
    news
):

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

    return (
        "📌 درێژەی هەواڵ:\n\n"
        f"{full_body}\n\n"
        f"سەرچاوە: {source}"
    )


# =========================================================
# 📸 PREPARE IMAGE
# =========================================================

def prepare_image(
    news
):

    candidates = []

    rss_image = news.get(
        "image_url"
    )

    if rss_image:

        candidates.append(
            rss_image
        )

    article_url = news.get(
        "link"
    )

    if article_url:

        try:

            article_images = get_article_images(
                article_url
            )

            candidates.extend(
                article_images
            )

        except Exception:
            pass

    # remove duplicates
    candidates = list(
        dict.fromkeys(
            candidates
        )
    )

    print(
        "\n============================================================"
    )

    print(
        "📸 بەدوای وێنەی باشدا دەگەڕێین..."
    )

    image_file = download_best_image(
        candidates
    )

    if not image_file:

        print(
            "⚠️ وێنە نەدۆزرایەوە."
        )

        image_file = create_fallback_image(
            news.get(
                "kur_title",
                news.get(
                    "title",
                    "ASO NEWS"
                )
            )

    if image_file:

        image_file = add_watermark(
            image_file
        )

    return image_file


# =========================================================
# 📤 FACEBOOK PHOTO POST
# =========================================================

def publish_photo(
    message,
    image_file
):

    if not image_file:
        return None

    if not os.path.exists(
        image_file
    ):

        print(
            "❌ image file نەدۆزرایەوە."
        )

        return None

    print(
        "\n============================================================"
    )

    print(
        "📘 FACEBOOK PHOTO POST"
    )

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
            f"Status: {response.status_code}"
        )

        print(
            response.text
        )

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
                "✅ Facebook photo post success."
            )

            return post_id

        return None

    except Exception as e:

        print(
            f"❌ Facebook photo error: {e}"
        )

        return None


# =========================================================
# 🎥 FACEBOOK VIDEO POST
# =========================================================

def publish_video(
    message,
    video_url
):

    if not video_url:

        return None

    print(
        "\n============================================================"
    )

    print(
        "🎥 VIDEO FOUND"
    )

    print(
        video_url
    )

    try:

        # تێبینی:
        # تەنها ئەو video URL ـانە هەوڵی publish دەدرێن
        # کە Facebook بتوانێت بیانخوێنێتەوە.

        response = session.post(
            FACEBOOK_VIDEO_URL,
            data={
                "
