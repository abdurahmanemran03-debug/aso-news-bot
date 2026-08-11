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
# ASO NEWS — AUTO PUBLISHER
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"

HISTORY_FILE = "posted_news.json"

GEMINI_MODEL = "gemini-3.5-flash"

MAX_HISTORY = 1000
MAX_CANDIDATES = 10

FACEBOOK_PHOTO_URL = (
    f"https://graph.facebook.com/{PAGE_ID}/photos"
)


# =========================================================
# RSS SOURCES
# =========================================================

RSS_SOURCES = [
    {
        "name": "BBC News",
        "url": "https://feeds.bbci.co.uk/news/rss.xml"
    },
    {
        "name": "Rudaw",
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Arudaw.net+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    },
    {
        "name": "Kurdistan24",
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Akurdistan24.net+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        )
    }
]


# =========================================================
# HTTP SESSION
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
            f"⚠️ کێشە لە خوێندنەوەی history: {e}"
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
# TEXT CLEANING
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
# IMAGE URL EXTRACTION
# =========================================================

def get_rss_image(entry):

    # media_content
    media_content = entry.get(
        "media_content"
    )

    if media_content:

        for media in media_content:

            url = media.get("url")

            if url:
                return url


    # media_thumbnail
    media_thumbnail = entry.get(
        "media_thumbnail"
    )

    if media_thumbnail:

        for media in media_thumbnail:

            url = media.get("url")

            if url:
                return url


    # enclosure
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


    # HTML image
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
# ARTICLE PAGE IMAGE
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

        # og:image
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


        # Also look for large image URLs
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


        return images[:20]

    except Exception as e:

        print(
            f"⚠️ کێشە لە پشکنینی پەڕەی هەواڵ: {e}"
        )

        return []


# =========================================================
# DOWNLOAD + QUALITY CHECK
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

            if len(image_data) < 30_000:
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

            # Reject very small images
            if width < 800 or height < 450:
                print(
                    "⛔ قەبارەی وێنەکە بۆ پۆستی هەواڵ کەمە."
                )
                continue

            # Score image by resolution and file size
            score = (
                width * height
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

        print(
            "❌ هیچ وێنەیەکی کوالێتی باش نەدۆزرایەوە."
        )

        return None

    try:

        image = Image.open(
            BytesIO(best["data"])
        )

        # Convert to RGB
        if image.mode != "RGB":
            image = image.convert(
                "RGB"
            )

        # Save JPEG with high quality
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
# FIND BEST IMAGE
# =========================================================

def find_best_image(entry):

    candidates = []

    # First: RSS images
    rss_image = get_rss_image(
        entry
    )

    if rss_image:

        candidates.append(
            rss_image
        )

    # Second: article page
    article_url = entry.get(
        "link",
        ""
    ).strip()

    if article_url:

        article_images = get_article_images(
            article_url
        )

        candidates.extend(
            article_images
        )

    # Remove duplicates
    unique_candidates = []

    for url in candidates:

        if url and url not in unique_candidates:

            unique_candidates.append(
                url
            )

    return download_best_image(
        unique_candidates
    )


# =========================================================
# COLLECT NEWS
# =========================================================

def collect_news():

    all_news = []

    for source in RSS_SOURCES:

        print("\n" + "=" * 60)
        print(
            f"🔎 سەرچاوە: {source['name']}"
        )
        print("=" * 60)

        try:

            feed = feedparser.parse(
                source["url"]
            )

            print(
                f"📰 {len(feed.entries)} "
                f"هەواڵ دۆزرایەوە"
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

                if news_id in posted_news:
                    continue

                all_news.append({
                    "id": news_id,
                    "source": source["name"],
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "entry": item
                })

        except Exception as e:

            print(
                f"⚠️ کێشە لە {source['name']}: {e}"
            )

    return all_news


# =========================================================
# GEMINI NEWS WRITER
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
سەردێڕ: {item['title']}
پوختە: {item['summary']}
لینک: {item['link']}
"""


    prompt = f"""
تۆ دەستکارێکی هەواڵی پیشەیی بۆ ASO NEWS ـیت.

لە نێوان هەواڵەکانی خوارەوە تەنها یەک هەواڵ
هەڵبژێرە و بە کوردی سۆرانیی ڕەوان و
بێ هەڵەی تایپی بیگۆڕە بۆ پۆستی Facebook.

یاساکان:

- هیچ زانیارییەکی خۆت زیاد مەکە.
- هیچ شتێک مەخەمنە.
- ژمارە و بەروارەکان مەگۆڕە.
- ناوی کەس و شوێن مەگۆڕە.
- شیکاری سیاسی مەکە.
- هەواڵەکە بە کوردی سۆرانیی سروشتی بنووسە.
- سەردێڕ کورت و ڕوون بێت.
- دەقی هەواڵەکە کورت و زانیاری‌دار بێت.
- ئەگەر هەمان ڕووداو لە چەند سەرچاوەیەکدا هەبوو،
  تەنها یەکێکیان هەڵبژێرە.

فۆرماتی وەڵام:

SOURCE_NUMBER: ژمارە

TITLE: سەردێڕ

BODY:
دەقی هەواڵ

HASHTAGS:
#ASONEWS #کوردستان #هەواڵ

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
        r"BODY:\s*(.*?)(?=\nHASHTAGS:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    hashtags_match = re.search(
        r"HASHTAGS:\s*(.*?)(?=\nSOURCE:)",
        result,
        re.IGNORECASE | re.DOTALL
    )

    source_match_name = re.search(
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

    hashtags = (
        hashtags_match.group(1).strip()
        if hashtags_match
        else "#ASONEWS"
    )

    source_name = (
        source_match_name.group(1).strip()
        if source_match_name
        else ""
    )

    if not title or not body:
        return None

    return {
        "source_number": source_number,
        "title": title,
        "body": body,
        "hashtags": hashtags,
        "source_name": source_name
    }


# =========================================================
# BUILD POST
# =========================================================

def build_post(
    parsed
):

    return (
        f"📰 {parsed['title']}\n\n"
        f"{parsed['body']}\n\n"
        f"{parsed['hashtags']}\n\n"
        f"سەرچاوە: {parsed['source_name']}"
    )


# =========================================================
# FACEBOOK
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
                    "message": message,
                    "access_token":
                        FACEBOOK_PAGE_ACCESS_TOKEN
                },
                timeout=60
            )

        print("\n" + "=" * 60)
        print(
            "📘 FACEBOOK PHOTO POST"
        )
        print("=" * 60)

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
# MAIN
# =========================================================

def main():

    print("\n" + "=" * 60)
    print(
        "🇹🇯 ASO NEWS — AUTO PUBLISHER"
    )
    print("=" * 60)

    # -----------------------------------------------------
    # Collect
    # -----------------------------------------------------

    all_news = collect_news()

    if not all_news:

        print(
            "ℹ️ هیچ هەواڵێکی نوێ نییە."
        )

        return

    print(
        f"✅ {len(all_news)} هەواڵی نوێ دۆزرایەوە."
    )

    candidates = all_news[
        :MAX_CANDIDATES
    ]

    # -----------------------------------------------------
    # Gemini
    # -----------------------------------------------------

    result = generate_news_post(
        candidates
    )

    if not result:

        return

    print("\n" + "=" * 60)
    print("🤖 GEMINI")
    print("=" * 60)
    print(result)

    parsed = parse_gemini_result(
        result
    )

    if not parsed:

        print(
            "❌ Gemini result نادروستە."
        )

        return

    selected_index = parsed[
        "source_number"
    ]

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

    # -----------------------------------------------------
    # Final post
    # -----------------------------------------------------

    post = build_post(
        parsed
    )

    print("\n" + "=" * 60)
    print(
        "📰 ASO NEWS — FINAL POST"
    )
    print("=" * 60)
    print(post)

    # -----------------------------------------------------
    # BEST IMAGE
    # -----------------------------------------------------

    print("\n" + "=" * 60)
    print(
        "📸 بەدوای باشترین وێنەدا دەگەڕێین..."
    )
    print("=" * 60)

    image_path = find_best_image(
        selected_news["entry"]
    )

    if not image_path:

        print(
            "⛔ هیچ وێنەیەکی کوالێتی باش نەدۆزرایەوە."
        )

        print(
            "پۆست ناکرێت بۆ ئەوەی وێنەی ناساف "
            "لە Facebook بڵاونەکرێتەوە."
        )

        return

    # -----------------------------------------------------
    # Facebook
    # -----------------------------------------------------

    facebook_response = publish_photo(
        image_path,
        post
    )

    # -----------------------------------------------------
    # Save history
    # -----------------------------------------------------

    if (
        facebook_response
        and facebook_response.status_code == 200
    ):

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

    # -----------------------------------------------------
    # Cleanup
    # -----------------------------------------------------

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
