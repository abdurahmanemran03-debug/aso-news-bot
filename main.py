import os
import json
import hashlib
import re
import html
from urllib.parse import urljoin

import requests
import feedparser
from PIL import Image
from io import BytesIO
from google import genai


# =========================================================
# ASO NEWS — AUTO PUBLISHER v2
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"

HISTORY_FILE = "posted_news.json"

# Gemini
GEMINI_MODEL = "gemini-3.5-flash"

MAX_HISTORY = 2000

# لە نێوان ئەو هەموو هەواڵانەدا
# ئەمانە دەچن بۆ Gemini
MAX_CANDIDATES = 20

# ---------------------------------------------------------
# Facebook
# ---------------------------------------------------------

FACEBOOK_PHOTO_URL = (
    f"https://graph.facebook.com/{PAGE_ID}/photos"
)

# ---------------------------------------------------------
# Logo
# ---------------------------------------------------------

LOGO_FILE = "logo.png"


# =========================================================
# NEWS PRIORITY
# =========================================================

IRAQ_KURDISTAN_KEYWORDS = [
    # Kurdistan
    "kurdistan",
    "kurdish",
    "erbil",
    "hawler",
    "sulaymaniyah",
    "sulaimani",
    "duhok",
    "dohuk",
    "halabja",
    "kirkuk",
    "zakho",
    "akre",
    "kalar",
    "rawanduz",

    # Iraq
    "iraq",
    "iraqi",
    "baghdad",
    "basra",
    "mosul",
    "najaf",
    "karbala",
    "anbar",
    "ninawa",
    "diyala",
    "salahaddin",

    # KRG
    "krg",
    "kurdistan regional government",
]


# =========================================================
# RSS SOURCES
# =========================================================

RSS_SOURCES = [

    # =====================================================
    # 🇮🇶 KURDISTAN / IRAQ — HIGH PRIORITY
    # =====================================================

    {
        "name": "Rudaw",
        "priority": 10,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Arudaw.net+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "Kurdistan24",
        "priority": 10,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Akurdistan24.net+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "NRT",
        "priority": 9,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Anrt.tv+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "BasNews",
        "priority": 9,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Abasnews.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "Shafaq News",
        "priority": 9,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Ashafaq.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "Iraqi News",
        "priority": 8,
        "url": (
            "https://news.google.com/rss/search?"
            "q=Iraq+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    # =====================================================
    # 🌍 WORLD / REGION
    # =====================================================

    {
        "name": "Al Jazeera",
        "priority": 7,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Aaljazeera.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "Reuters",
        "priority": 7,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Areuters.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "Associated Press",
        "priority": 7,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Aapnews.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "BBC News",
        "priority": 6,
        "url": (
            "https://feeds.bbci.co.uk/news/rss.xml"
        )
    },

    {
        "name": "DW",
        "priority": 6,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Adw.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "France 24",
        "priority": 6,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Afrance24.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "VOA",
        "priority": 5,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Avoanews.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "Anadolu Agency",
        "priority": 6,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Aaa.com.tr+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "The Guardian",
        "priority": 5,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Atheguardian.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },

    {
        "name": "NPR",
        "priority": 5,
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Anpr.org+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },
]


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
})


# =========================================================
# GEMINI
# =========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# HISTORY
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
            f"⚠️ کێشە لە history: {e}"
        )

    return []


def save_history(history):

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


posted_news = load_history()


# =========================================================
# TEXT
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(text)

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
# NEWS ID
# =========================================================

def create_news_id(title, link):

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
# PRIORITY SCORE
# =========================================================

def calculate_priority(item):

    text = (
        item["title"]
        + " "
        + item["summary"]
    ).lower()

    score = item["priority"] * 10

    # Kurdistan / Iraq boost
    for keyword in IRAQ_KURDISTAN_KEYWORDS:

        if keyword in text:
            score += 35

    # Recent-looking important terms
    important_words = [
        "breaking",
        "urgent",
        "latest",
        "attack",
        "earthquake",
        "government",
        "president",
        "prime minister",
        "election",
        "oil",
        "security",
        "war",
        "iran",
        "turkey",
        "syria",
        "iraq",
        "kurdistan",
    ]

    for word in important_words:

        if word in text:
            score += 3

    return score


# =========================================================
# RSS IMAGE
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
# ARTICLE IMAGES
# =========================================================

def get_article_images(article_url):

    if not article_url:
        return []

    try:

        response = session.get(
            article_url,
            timeout=25,
            allow_redirects=True
        )

        if response.status_code != 200:
            return []

        page = response.text

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
                    response.url,
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
                response.url,
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

    except Exception as e:

        print(
            f"⚠️ کێشە لە پشکنینی وێنە: {e}"
        )

        return []


# =========================================================
# DOWNLOAD BEST IMAGE
# =========================================================

def download_best_image(
    candidates,
    filename="news_image.jpg"
):

    best = None

    for image_url in candidates:

        if not image_url:
            continue

        try:

            print(
                f"🔎 پشکنینی وێنە: {image_url}"
            )

            response = session.get(
                image_url,
                timeout=25
            )

            if response.status_code != 200:
                continue

            content_type = response.headers.get(
                "content-type",
                ""
            ).lower()

            if "image" not in content_type:
                continue

            image_data = response.content

            if len(image_data) < 25_000:
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

            if width < 800 or height < 450:
                print(
                    "⛔ قەبارەی وێنەکە کەمە."
                )
                continue

            # Prefer landscape news images
            aspect = width / height

            if aspect < 1.15:
                score = width * height * 0.5
            else:
                score = width * height

            score += len(image_data) / 100

            if (
                best is None
                or score > best["score"]
            ):

                best = {
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

        print(
            "❌ هیچ وێنەیەکی گونجاو نەدۆزرایەوە."
        )

        return None

    try:

        image = Image.open(
            BytesIO(best["data"])
        )

        if image.mode != "RGB":
            image = image.convert("RGB")

        image.save(
            filename,
            "JPEG",
            quality=95,
            optimize=True
        )

        print(
            "\n✅ باشترین وێنە:"
        )

        print(
            f"📐 {best['width']}x{best['height']}"
        )

        return filename

    except Exception as e:

        print(
            f"❌ هەڵە لە هەڵگرتنی وێنە: {e}"
        )

        return None


# =========================================================
# WATERMARK
# =========================================================

def add_logo_watermark(
    image_path,
    logo_path=LOGO_FILE
):

    if not os.path.exists(logo_path):

        print(
            f"⚠️ لۆگۆ نەدۆزرایەوە: {logo_path}"
        )

        return image_path

    try:

        base = Image.open(
            image_path
        ).convert("RGBA")

        logo = Image.open(
            logo_path
        ).convert("RGBA")

        # Remove transparent empty area
        alpha = logo.getchannel("A")

        bbox = alpha.getbbox()

        if bbox:
            logo = logo.crop(bbox)

        # Small and clean logo
        target_width = max(
            75,
            int(base.width * 0.075)
        )

        ratio = (
            target_width / logo.width
        )

        target_height = max(
            1,
            int(logo.height * ratio)
        )

        logo = logo.resize(
            (
                target_width,
                target_height
            ),
            Image.Resampling.LANCZOS
        )

        # Clearer logo
        alpha = logo.getchannel("A")

        alpha = alpha.point(
            lambda p: min(
                255,
                int(p * 0.96)
            )
        )

        logo.putalpha(alpha)

        # Margin
        margin = max(
            16,
            int(base.width * 0.018)
        )

        x = (
            base.width
            - logo.width
            - margin
        )

        y = (
            base.height
            - logo.height
            - margin
        )

        layer = Image.new(
            "RGBA",
            base.size,
            (0, 0, 0, 0)
        )

        layer.alpha_composite(
            logo,
            (x, y)
        )

        result = Image.alpha_composite(
            base,
            layer
        )

        result.convert("RGB").save(
            image_path,
            "JPEG",
            quality=95,
            optimize=True
        )

        print(
            "✅ لۆگۆ بە شێوەی پاک و ڕوون زیاد کرا."
        )

        return image_path

    except Exception as e:

        print(
            f"⚠️ کێشە لە watermark: {e}"
        )

        return image_path


# =========================================================
# FIND IMAGE
# =========================================================

def find_best_image(entry):

    candidates = []

    rss_image = get_rss_image(
        entry
    )

    if rss_image:
        candidates.append(
            rss_image
        )

    article_url = entry.get(
        "link",
        ""
    ).strip()

    if article_url:

        candidates.extend(
            get_article_images(
                article_url
            )
        )

    unique = []

    for url in candidates:

        if (
            url
            and url not in unique
        ):
            unique.append(url)

    image_path = download_best_image(
        unique
    )

    if not image_path:
        return None

    return add_logo_watermark(
        image_path
    )


# =========================================================
# COLLECT NEWS
# =========================================================

def collect_news():

    all_news = []

    seen_ids = set()

    for source in RSS_SOURCES:

        print(
            "\n" + "=" * 60
        )

        print(
            f"🔎 سەرچاوە: {source['name']}"
        )

        print(
            "=" * 60
        )

        try:

            feed = feedparser.parse(
                source["url"]
            )

            print(
                f"📰 {len(feed.entries)} هەواڵ"
            )

            for item in feed.entries:

                title = clean_text(
                    item.get(
                        "title",
                        ""
                    )
                )

                summary = clean_text(
                    item.get(
                        "summary",
                        ""
                    )
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

                if news_id in posted_news:
                    continue

                if news_id in seen_ids:
                    continue

                seen_ids.add(news_id)

                news_item = {

                    "id": news_id,

                    "source": source["name"],

                    "priority": source[
                        "priority"
                    ],

                    "title": title,

                    "summary": summary,

                    "link": link,

                    "entry": item
                }

                news_item[
                    "score"
                ] = calculate_priority(
                    news_item
                )

                all_news.append(
                    news_item
                )

        except Exception as e:

            print(
                f"⚠️ کێشە لە {source['name']}: {e}"
            )

    # Highest priority first
    all_news.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return all_news


# =========================================================
# GEMINI
# =========================================================

def generate_news_post(
    candidates
):

    news_text = ""

    for i, item in enumerate(
        candidates,
        start=1
    ):

        news_text += f"""
[{i}]
سەرچاوە: {item['source']}
نمرەی گرنگی: {item['score']}
سەردێڕ: {item['title']}
پوختە: {item['summary']}
لینک: {item['link']}
"""

    prompt = f"""
تۆ دەستکارێکی هەواڵی پیشەیی بۆ ASO NEWS ـیت.

لە نێوان ئەو هەواڵانەی خوارەوە تەنها یەک هەواڵ
هەڵبژێرە بۆ پۆستی Facebook.

ئەولەویەتی:

1. هەواڵی هەرێمی کوردستان.
2. هەواڵی عێراق.
3. هەواڵی ناوچەکە.
4. هەواڵی جیهانی زۆر گرنگ.

بەڵام:
- هەموو جارێک BBC هەڵمەبژێرە.
- سەرچاوەی جیاواز بەکاربهێنە.
- ئەگەر هەواڵێکی Rudaw، Kurdistan24، NRT،
  BasNews یان Shafaq گرنگتر بوو، ئەویان هەڵبژێرە.
- هەمان ڕووداو دووبارە مەکە.

یاساکانی نووسین:

- تەنها زانیارییەکانی سەرچاوە بەکاربهێنە.
- هیچ زانیارییەکی خۆت زیاد مەکە.
- ناوی کەس و شوێن مەگۆڕە.
- ژمارە و بەروار مەگۆڕە.
- شیکاری سیاسی مەکە.
- کوردی سۆرانیی سروشتی و ڕوون بەکاربهێنە.
- سەردێڕ کورت و سەرنجڕاکێش بێت.
- BODY کورت بێت.
- FULL_BODY دوو تا چوار پاراگراف بێت.
- FULL_BODY هەموو زانیاریی پشتڕاستکراوی هەواڵەکە بگرێتەوە.
- هیچ شتێکی خەیاڵی زیاد مەکە.

HASHTAGS:
هاشتاکی پەیوەندیدار بە هەواڵەکە دروست بکە.
هەمیشە #ASONEWS دابنێ.
لە 4 تا 7 هاشتاک زیاتر مەکە.

فۆرماتی وەڵام:

SOURCE_NUMBER: ژمارە

TITLE: سەردێڕ

BODY:
دەقی کورت

FULL_BODY:
دەقی درێژتر

HASHTAGS:
#ASONEWS ...

SOURCE:
ناوی سەرچاوە

هیچ دەقێکی تر زیاد مەکە.

هەواڵەکان:

{news_text}
"""

    try:

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        return response.text.strip()

    except Exception as e:

        print(
            f"❌ کێشە لە Gemini: {e}"
        )

        return None


# =========================================================
# PARSE GEMINI
# =========================================================

def parse_gemini_result(
    result
):

    if not result:
        return None

    source_match = re.search(
        r"SOURCE_NUMBER:\s*(\d+)",
        result,
        re.IGNORECASE
    )

    title_match = re.search(
        r"TITLE:\s*(.+)",
        result,
        re.IGNORECASE
    )

    body_match = re.search(
        r"BODY:\s*(.*?)(?=\nFULL_BODY:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    full_body_match = re.search(
        r"FULL_BODY:\s*(.*?)(?=\nHASHTAGS:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    hashtags_match = re.search(
        r"HASHTAGS:\s*(.*?)(?=\nSOURCE:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    source_name_match = re.search(
        r"SOURCE:\s*(.+)",
        result,
        re.IGNORECASE
    )

    if not source_match:
        return None

    try:

        source_number = int(
            source_match.group(1)
        )

    except ValueError:

        return None

    title = (
        title_match.group(1).strip()
        if title_match
        else ""
    )

    body = (
        body_match.group(1).strip()
        if body_match
        else ""
    )

    full_body = (
        full_body_match.group(1).strip()
        if full_body_match
        else body
    )

    hashtags = (
        hashtags_match.group(1).strip()
        if hashtags_match
        else "#ASONEWS"
    )

    source_name = (
        source_name_match.group(1).strip()
        if source_name_match
        else ""
    )

    if not title or not body:
        return None

    return {

        "source_number":
            source_number,

        "title":
            title,

        "body":
            body,

        "full_body":
            full_body,

        "hashtags":
            hashtags,

        "source_name":
            source_name
    }


# =========================================================
# BUILD POST
# =========================================================

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
# FACEBOOK POST
# =========================================================

def publish_photo(
    image_path,
    message
):

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
                    "message":
                        message,

                    "access_token":
                        FACEBOOK_PAGE_ACCESS_TOKEN
                },

                timeout=60
            )

        print(
            "\n" + "=" * 60
        )

        print(
            "📘 FACEBOOK PHOTO POST"
        )

        print(
            "=" * 60
        )

        print(
            "Status:",
            response.status_code
        )

        print(
            response.text
        )

        return response

    except Exception as e:

        print(
            f"❌ کێشە لە Facebook: {e}"
        )

        return None


# =========================================================
# FIRST COMMENT
# =========================================================

def publish_first_comment(
    post_id,
    comment
):

    try:

        url = (
            f"https://graph.facebook.com/"
            f"{post_id}/comments"
        )

        response = requests.post(

            url,

            data={
                "message":
                    comment,

                "access_token":
                    FACEBOOK_PAGE_ACCESS_TOKEN
            },

            timeout=60
        )

        print(
            "\n" + "=" * 60
        )

        print(
            "💬 FACEBOOK FIRST COMMENT"
        )

        print(
            "=" * 60
        )

        print(
            "Status:",
            response.status_code
        )

        print(
            response.text
        )

        return response

    except Exception as e:

        print(
            f"❌ کێشە لە کۆمێنت: {e}"
        )

        return None


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n" + "=" * 60
    )

    print(
        "🇮🇶 ASO NEWS — AUTO PUBLISHER v2"
    )

    print(
        "=" * 60
    )

    all_news = collect_news()

    if not all_news:

        print(
            "\nℹ️ هیچ هەواڵێکی نوێ نییە."
        )

        return

    print(
        f"\n✅ {len(all_news)} هەواڵی نوێ دۆزرایەوە."
    )

    # Only top candidates
    candidates = all_news[
        :MAX_CANDIDATES
    ]

    print(
        "\n🎯 هەواڵە بەرزترینەکان:"
    )

    for i, item in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{i}. "
            f"[{item['source']}] "
            f"{item['title']}"
        )

    result = generate_news_post(
        candidates
    )

    if not result:
        return

    print(
        "\n" + "=" * 60
    )

    print(
        "🤖 GEMINI"
    )

    print(
        "=" * 60
    )

    print(
        result
    )

    parsed = parse_gemini_result(
        result
    )

    if not parsed:

        print(
            "❌ Gemini result نادروستە."
        )

        return

    selected_index = (
        parsed["source_number"]
    )

    if (
        selected_index < 1
        or selected_index > len(candidates)
    ):

        print(
            "❌ ژمارەی هەڵبژێردراو نادروستە."
        )

        return

    selected_news = candidates[
        selected_index - 1
    ]

    post = build_post(
        parsed
    )

    first_comment = build_first_comment(
        parsed
    )

    print(
        "\n" + "=" * 60
    )

    print(
        "📰 FINAL POST"
    )

    print(
        "=" * 60
    )

    print(
        post
    )

    print(
        "\n📌 سەرچاوەی ڕاستەقینە:"
        f" {selected_news['source']}"
    )

    print(
        "\n" + "=" * 60
    )

    print(
        "📸 بەدوای وێنەی باشدا دەگەڕێین..."
    )

    print(
        "=" * 60
    )

    image_path = find_best_image(
        selected_news["entry"]
    )

    if not image_path:

        print(
            "⛔ وێنەی گونجاو نەدۆزرایەوە."
        )

        return

    facebook_response = publish_photo(
        image_path,
        post
    )

    if (
        facebook_response
        and facebook_response.status_code == 200
    ):

        try:

            facebook_data = (
                facebook_response.json()
            )

        except Exception:

            facebook_data = {}

        post_id = (
            facebook_data.get(
                "post_id"
            )
            or
            facebook_data.get(
                "id"
            )
        )

        if post_id:

            comment_response = (
                publish_first_comment(
                    post_id,
                    first_comment
                )
            )

            if (
                comment_response
                and
                comment_response.status_code == 200
            ):

                print(
                    "\n✅ کۆمێنتی یەکەم زیاد کرا."
                )

            else:

                print(
                    "\n⚠️ پۆست کرا، "
                    "بەڵام کۆمێنت نەکرا."
                )

        else:

            print(
                "\n⚠️ post_id نەگەڕێندرایەوە."
            )

        # Save ONLY after successful Facebook post
        posted_news.append(
            selected_news["id"]
        )

        save_history(
            posted_news
        )

        print(
            "\n✅ پۆست بە سەرکەوتوویی بڵاوکرایەوە."
        )

    else:

        print(
            "\n❌ Facebook پۆستەکەی قبوڵ نەکرد."
        )

    # Cleanup
    try:

        if os.path.exists(
            "news_image.jpg"
        ):

            os.remove(
                "news_image.jpg"
            )

    except Exception:
        pass


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
