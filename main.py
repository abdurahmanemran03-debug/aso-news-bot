import os
import json
import hashlib
import re
import html
import time
from urllib.parse import urljoin, quote

import requests
import feedparser
from PIL import Image, ImageEnhance
from io import BytesIO
from google import genai


# =========================================================
# 🇮🇶 ASO NEWS — AUTO PUBLISHER v3
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"

HISTORY_FILE = "posted_news.json"

GEMINI_MODEL = "gemini-3.5-flash"

MAX_HISTORY = 2000

# تەنها ئەو هەواڵانەی score ـی بەرزترینیان هەیە
MAX_CANDIDATES = 25

# کەمترین score بۆ ئەوەی هەواڵەکە بتوانێت هەڵبژێردرێت
MIN_NEWS_SCORE = 10

FACEBOOK_PHOTO_URL = (
    f"https://graph.facebook.com/{PAGE_ID}/photos"
)

FACEBOOK_VIDEO_URL = (
    f"https://graph.facebook.com/{PAGE_ID}/videos"
)

LOGO_FILE = "logo.png"

IMAGE_FILE = "news_image.jpg"


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
    )
})


# =========================================================
# 🤖 GEMINI
# =========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# 📰 NEWS SOURCES
# =========================================================
#
# Google News RSS queries are used for some sources because
# they are more stable than guessing private RSS endpoints.
#
# Kurdistan / Iraq sources get higher priority.
# =========================================================

RSS_SOURCES = [

    # =====================================================
    # 🇮🇶 KURDISTAN / IRAQ — HIGH PRIORITY
    # =====================================================

    {
        "name": "Rudaw",
        "priority": 20,
        "query": "site:rudaw.net Iraq OR Kurdistan",
    },

    {
        "name": "Kurdistan24",
        "priority": 20,
        "query": "site:kurdistan24.net Iraq OR Kurdistan",
    },

    {
        "name": "NRT",
        "priority": 20,
        "query": "site:nrt-news.com Iraq OR Kurdistan",
    },

    {
        "name": "BasNews",
        "priority": 20,
        "query": "site:basnews.com Iraq OR Kurdistan",
    },

    {
        "name": "Shafaq News",
        "priority": 20,
        "query": "site:shafaq.com Iraq OR Kurdistan",
    },

    {
        "name": "Iraqi News",
        "priority": 18,
        "query": "Iraq latest news",
    },

    # =====================================================
    # 🌍 INTERNATIONAL
    # =====================================================

    {
        "name": "Al Jazeera",
        "priority": 10,
        "query": "site:aljazeera.com Iraq OR Middle East OR world",
    },

    {
        "name": "Reuters",
        "priority": 10,
        "query": "site:reuters.com Iraq OR Middle East OR world",
    },

    {
        "name": "Associated Press",
        "priority": 9,
        "query": "site:apnews.com Iraq OR Middle East OR world",
    },

    {
        "name": "BBC News",
        "priority": 9,
        "query": "site:bbc.com/news Iraq OR Middle East OR world",
    },

    {
        "name": "DW",
        "priority": 8,
        "query": "site:dw.com Iraq OR Middle East OR world",
    },

    {
        "name": "France 24",
        "priority": 8,
        "query": "site:france24.com Iraq OR Middle East OR world",
    },

    {
        "name": "VOA",
        "priority": 7,
        "query": "site:voanews.com Iraq OR Middle East OR world",
    },

    {
        "name": "Anadolu Agency",
        "priority": 7,
        "query": "site:aa.com.tr Iraq OR Middle East OR world",
    },

    {
        "name": "The Guardian",
        "priority": 6,
        "query": "site:theguardian.com Iraq OR Middle East OR world",
    },

    {
        "name": "NPR",
        "priority": 6,
        "query": "site:npr.org Iraq OR Middle East OR world",
    },
]


# =========================================================
# 🔗 BUILD GOOGLE NEWS RSS
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
            f"⚠️ کێشە لە خوێندنەوەی history: {e}"
        )

    return []


def save_history(history):

    history = history[-MAX_HISTORY:]

    try:

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

    text = html.unescape(str(text))

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

    normalized_title = re.sub(
        r"\s+",
        " ",
        title.lower().strip()
    )

    base = (
        link.strip()
        if link.strip()
        else normalized_title
    )

    return hashlib.sha256(
        f"{base}|{normalized_title}".encode(
            "utf-8"
        )
    ).hexdigest()


# =========================================================
# 🖼️ RSS IMAGE
# =========================================================

def get_rss_image(entry):

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
        entry.get("summary", "")
        + " "
        + entry.get("description", "")
        + " "
        + entry.get("content", [{}])[0].get(
            "value",
            ""
        )
        if entry.get("content")
        else
        entry.get("summary", "")
        + " "
        + entry.get("description", "")
    )

    matches = re.findall(
        r'<img[^>]+src=["\']([^"\']+)',
        raw,
        re.IGNORECASE
    )

    if matches:
        return matches[0]

    return None


# =========================================================
# 📹 FIND VIDEO URL
# =========================================================

def get_video_url(entry):

    media_content = entry.get(
        "media_content"
    )

    if media_content:

        for media in media_content:

            media_type = (
                media.get("type", "")
                .lower()
            )

            url = media.get("url")

            if (
                url
                and (
                    "video" in media_type
                    or url.lower().endswith(
                        (".mp4", ".mov", ".webm")
                    )
                )
            ):

                return url

    enclosures = entry.get(
        "enclosures"
    )

    if enclosures:

        for enclosure in enclosures:

            media_type = (
                enclosure.get("type", "")
                .lower()
            )

            url = (
                enclosure.get("href")
                or enclosure.get("url")
            )

            if (
                url
                and "video" in media_type
            ):

                return url

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
            timeout=25,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        return response.text

    except Exception as e:

        print(
            f"⚠️ کێشە لە پشکنینی article: {e}"
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
                image_url.startswith("http")
                and image_url not in images
            ):

                images.append(
                    image_url
                )

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
            image_url.startswith("http")
            and image_url not in images
        ):

            images.append(
                image_url
            )

    return images[:30]


# =========================================================
# 🖼️ DOWNLOAD IMAGE
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
                timeout=25,
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

            if "image" not in content_type:
                continue

            image_data = response.content

            if len(image_data) < 20_000:

                print(
                    "⛔ وێنەکە زۆر بچووکە."
                )

                continue

            image = Image.open(
                BytesIO(image_data)
            )

            width, height = image.size

            print(
                f"📐 قەبارە: {width}x{height}"
            )

            if width < 700 or height < 400:

                print(
                    "⛔ قەبارەی وێنەکە کەمە."
                )

                continue

            # ئەولەویەت بە وێنەی گەورە و landscape
            aspect = (
                width / height
                if height
                else 0
            )

            aspect_bonus = (
                1.5
                if 1.3 <= aspect <= 2.2
                else 1
            )

            score = (
                width
                * height
                * aspect_bonus
                + len(image_data) / 100
            )

            if (
                best is None
                or score > best["score"]
            ):

                best = {
                    "url": image_url,
                    "data": image_data,
                    "width": width,
                    "height": height,
                    "score": score
                }

        except Exception as e:

            print(
                f"⚠️ نەتوانرا وێنەکە پشکنرێت: {e}"
            )

    if best is None:

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
            quality=95,
            optimize=True
        )

        print(
            "\n✅ باشترین وێنە هەڵبژێردرا:"
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
            f"❌ هەڵە لە پاشەکەوتکردنی وێنە: {e}"
        )

        return None


# =========================================================
# 🖼️ FALLBACK IMAGE
# =========================================================

def create_fallback_image(
    title,
    filename=IMAGE_FILE
):

    """
    ئەگەر هیچ وێنەیەکی ڕاستەوخۆ نەدۆزرایەوە،
    پۆستەکە بە وێنەی fallback ـی خۆمان بڵاودەکەینەوە.
    """

    try:

        width = 1200
        height = 675

        image = Image.new(
            "RGB",
            (width, height),
            (20, 20, 20)
        )

        # تەنها text ـی سادە بۆ fallback
        # بەبێ فۆنتی دەرەکی
        #
        # ئەگەر فۆنتی تایبەتت هەیە دەتوانرێت
