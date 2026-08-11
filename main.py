import os
import json
import hashlib
import re
import html
from urllib.parse import urljoin

import requests
import feedparser
from google import genai


# =========================================================
# ASO NEWS — Automatic Kurdish Sorani News Publisher
# =========================================================
# Features:
# 🇹🇯 Kurdish Sorani news writing
# 📸 News image extraction
# 📘 Facebook Photo Post
# 🔐 Duplicate-news protection
# 🤖 Automatic publishing
# 🛡️ logo.png watermark will be added later
# =========================================================


# =========================================================
# CONFIGURATION
# =========================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

PAGE_ID = "1128027710403407"

HISTORY_FILE = "posted_news.json"

# Gemini model
GEMINI_MODEL = "gemini-3.5-flash"

# Maximum number of old IDs to keep
MAX_HISTORY = 1000

# How many news candidates Gemini should inspect
MAX_CANDIDATES = 10

# Facebook Graph API
FACEBOOK_GRAPH_URL = f"https://graph.facebook.com/{PAGE_ID}/photos"


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
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
})


# =========================================================
# GEMINI CLIENT
# =========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# HISTORY FUNCTIONS
# =========================================================

def load_history():
    """Load previously posted news IDs."""

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
        print(f"⚠️ نەتوانرا مێژووی هەواڵەکان بخوێندرێتەوە: {e}")

    return []


def save_history(history):
    """Save posted news IDs."""

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
    """Remove HTML and unnecessary whitespace."""

    if not text:
        return ""

    text = html.unescape(text)

    # Remove HTML tags
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # Remove excessive whitespace
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
    """
    Create stable ID.
    Prefer URL, but also include title so that
    duplicate stories with slightly different URLs
    are easier to detect.
    """

    base = (
        link.strip()
        if link.strip()
        else title.strip()
    )

    normalized_title = re.sub(
        r"\s+",
        " ",
        title.lower().strip()
    )

    unique_text = (
        base
        + "|"
        + normalized_title
    )

    return hashlib.sha256(
        unique_text.encode("utf-8")
    ).hexdigest()


# =========================================================
# IMAGE EXTRACTION FROM RSS ENTRY
# =========================================================

def get_image_from_entry(entry):
    """
    Try to find an image directly from RSS metadata.
    """

    # media_content
    media_content = entry.get("media_content")

    if media_content:
        for media in media_content:

            url = media.get("url")

            if url:
                return url

    # media_thumbnail
    media_thumbnail = entry.get("media_thumbnail")

    if media_thumbnail:
        for media in media_thumbnail:

            url = media.get("url")

            if url:
                return url

    # enclosure
    enclosures = entry.get("enclosures")

    if enclosures:
        for enclosure in enclosures:

            url = enclosure.get("href") or enclosure.get("url")

            mime = enclosure.get("type", "")

            if url and (
                mime.startswith("image/")
                or re.search(
                    r"\.(jpg|jpeg|png|webp)(\?.*)?$",
                    url,
                    re.IGNORECASE
                )
            ):
                return url

    # Search image URL inside summary/description
    raw = (
        entry.get("summary", "")
        + " "
        + entry.get("description", "")
    )

    image_match = re.search(
        r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?',
        raw,
        re.IGNORECASE
    )

    if image_match:
        return html.unescape(
            image_match.group(0)
        )

    return None


# =========================================================
# IMAGE EXTRACTION FROM ARTICLE PAGE
# =========================================================

def get_image_from_article(url):
    """
    Open the article page and look for:
    og:image
    twitter:image
    image meta tags
    """

    if not url:
        return None

    try:

        response = session.get(
            url,
            timeout=20,
            allow_redirects=True
        )

        if response.status_code != 200:
            return None

        page = response.text

        # og:image
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

            r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                page,
                re.IGNORECASE
            )

            if match:

                image_url = html.unescape(
                    match.group(1).strip()
                )

                image_url = urljoin(
                    response.url,
                    image_url
                )

                if image_url.startswith("http"):
                    return image_url

    except Exception as e:

        print(
            f"⚠️ نەتوانرا وێنە لە پەڕەکە وەربگیرێت: {e}"
        )

    return None


# =========================================================
# DOWNLOAD IMAGE
# =========================================================

def download_image(image_url, filename="news_image.jpg"):
    """
    Download image locally so it can be uploaded
    directly to Facebook.
    """

    if not image_url:
        return None

    try:

        response = session.get(
            image_url,
            timeout=30,
            stream=True
        )

        if response.status_code != 200:
            print(
                f"⚠️ وێنەکە نەهێنراوە. Status: "
                f"{response.status_code}"
            )
            return None

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if (
            "image" not in content_type
            and not re.search(
                r"\.(jpg|jpeg|png|webp)(\?.*)?$",
                image_url,
                re.IGNORECASE
            )
        ):
            print("⚠️ URL ـەکە وێنە نییە.")
            return None

        with open(
            filename,
            "wb"
        ) as f:

            for chunk in response.iter_content(
                chunk_size=8192
            ):

                if chunk:
                    f.write(chunk)

        if os.path.getsize(filename) < 1000:

            os.remove(filename)

            return None

        return filename

    except Exception as e:

        print(
            f"⚠️ کێشە لە داگرتنی وێنە: {e}"
        )

        return None


# =========================================================
# FIND NEWS IMAGE
# =========================================================

def find_news_image(entry):
    """
    Try RSS image first.
    If unavailable, inspect article page.
    """

    image_url = get_image_from_entry(entry)

    if image_url:

        print(
            f"📸 وێنە لە RSS ـەوە دۆزرایەوە: "
            f"{image_url}"
        )

        return image_url

    article_url = entry.get(
        "link",
        ""
    ).strip()

    if article_url:

        print("🔎 بەدوای og:image ـدا دەگەڕێین...")

        image_url = get_image_from_article(
            article_url
        )

        if image_url:

            print(
                f"📸 وێنە لە پەڕەی هەواڵەکە دۆزرایەوە: "
                f"{image_url}"
            )

            return image_url

    return None


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

                image_url = find_news_image(
                    item
                )

                all_news.append({
                    "id": news_id,
                    "source": source["name"],
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "image_url": image_url
                })

        except Exception as e:

            print(
                f"⚠️ کێشە لە "
                f"{source['name']}: {e}"
            )

    return all_news


# =========================================================
# SELECT AND WRITE NEWS WITH GEMINI
# =========================================================

def generate_news_post(candidates):

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
تۆ دەستکارێکی هەواڵی پیشەیی و زمانزانیت
بۆ پەیجی ASO NEWS.

ئەرکەکەت:
لە نێوان هەواڵەکانی خوارەوە تەنها یەک هەواڵ
هەڵبژێرە و بە کوردی سۆرانیی ڕەوان و
پیشەیی بیگۆڕە بۆ پۆستی Facebook.

یاساکانی گرنگ:

1. تەنها یەک هەواڵ هەڵبژێرە.
2. هەواڵی گرنگ و نوێ پێش هەموو شتێک هەڵبژێرە.
3. هەواڵی کۆمەڵایەتی و بێ گرنگی مەهێنە
   ئەگەر هەواڵێکی گرنگتر هەبێت.
4. هیچ زانیارییەکی خۆت زیاد مەکە.
5. هیچ شتێک مەخەمنە.
6. ناوی کەسەکان مەگۆڕە.
7. ناوی شوێنەکان مەگۆڕە.
8. ژمارە و بەروارەکان مەگۆڕە.
9. شیکاری سیاسی مەکە.
10. ئاراستەی سیاسی مەدە.
11. هەواڵەکە بە زمانی کوردی سۆرانی بنووسە.
12. کوردییەکە دەبێت ڕەوان، سروشتی و
    بێ هەڵەی تایپی بێت.
13. وشەی نامۆی فارسی یان عەرەبی بەکارمەهێنە
    ئەگەر وشەی کوردیی ڕوون هەبێت.
14. سەردێڕەکە کورت و ڕوون بێت.
15. دەقی هەواڵەکە زانیاریی سەرەکی ڕوون بکاتەوە.
16. دەقەکە زۆر درێژ مەکە.
17. هیچ emoji ـی زۆر بەکارمەهێنە.
18. هەمان ڕووداو ئەگەر لە چەند سەرچاوەیەکدا
    هەبوو، تەنها یەکێکیان هەڵبژێرە.
19. سەرچاوەکە لە کۆتایی پۆستەکە بنووسە.
20. هەشتاگەکان پەیوەندیدار و کەم بن.

فۆرماتی وەڵام دەبێت تەنها ئەمە بێت:

SOURCE_NUMBER: ژمارە

TITLE: سەردێڕی کوردی

BODY:
دەقی هەواڵ بە کوردی سۆرانی

HASHTAGS:
#ASONEWS #کوردستان #هەواڵ

SOURCE:
ناوی سەرچاوە

هیچ دەقێکی تر لە دەرەوەی ئەم فۆرماتە مەنووسە.

هەواڵەکان:

{news_text}
"""


    try:

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        result = response.text.strip()

        return result

    except Exception as e:

        print(
            f"❌ کێشە لە Gemini: {e}"
        )

        return None


# =========================================================
# PARSE GEMINI RESULT
# =========================================================

def parse_gemini_result(result):

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

    # Clean accidental markdown
    title = re.sub(
        r"^\*+|\*+$",
        "",
        title
    ).strip()

    body = re.sub(
        r"\n{3,}",
        "\n\n",
        body
    ).strip()

    hashtags = re.sub(
        r"\s+",
        " ",
        hashtags
    ).strip()

    return {
        "source_number": source_number,
        "title": title,
        "body": body,
        "hashtags": hashtags,
        "source_name": source_name
    }


# =========================================================
# BUILD FACEBOOK POST
# =========================================================

def build_post(parsed):

    return (
        f"📰 {parsed['title']}\n\n"
        f"{parsed['body']}\n\n"
        f"{parsed['hashtags']}\n\n"
        f"سەرچاوە: {parsed['source_name']}"
    )


# =========================================================
# FACEBOOK PHOTO POST
# =========================================================

def publish_photo_to_facebook(
    image_path,
    message
):

    if not image_path:
        print(
            "❌ هیچ وێنەیەک بەردەست نییە."
        )
        return None

    try:

        with open(
            image_path,
            "rb"
        ) as image_file:

            response = requests.post(
                FACEBOOK_GRAPH_URL,
                files={
                    "source": (
                        os.path.basename(
                            image_path
                        ),
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
        print("📘 FACEBOOK PHOTO POST")
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
            f"❌ کێشە لە ناردنی وێنە بۆ Facebook: {e}"
        )

        return None


# =========================================================
# MAIN
# =========================================================

def main():

    print("\n")
    print("=" * 60)
    print("🇹🇯 ASO NEWS — AUTO PUBLISHER")
    print("=" * 60)

    # -----------------------------------------------------
    # Collect
    # -----------------------------------------------------

    all_news = collect_news()

    if not all_news:

        print(
            "\nℹ️ هیچ هەواڵێکی نوێ نەدۆزرایەوە."
        )

        return

    print("\n" + "=" * 60)
    print(
        f"✅ کۆی هەواڵە نوێکان: "
        f"{len(all_news)}"
    )
    print("=" * 60)

    # -----------------------------------------------------
    # Candidates
    # -----------------------------------------------------

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

        print(
            "❌ Gemini هیچ وەڵامێکی دروستی نەدا."
        )

        return

    print("\n" + "=" * 60)
    print("🤖 GEMINI")
    print("=" * 60)
    print(result)

    # -----------------------------------------------------
    # Parse
    # -----------------------------------------------------

    parsed = parse_gemini_result(
        result
    )

    if not parsed:

        print(
            "❌ نەتوانرا وەڵامی Gemini بخوێندرێتەوە."
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
    # Make final post
    # -----------------------------------------------------

    post = build_post(
        parsed
    )

    print("\n" + "=" * 60)
    print("📰 ASO NEWS — پۆستی کۆتایی")
    print("=" * 60)
    print(post)
    print("=" * 60)

    print(
        f"📌 سەرچاوەی ڕاستەقینە: "
        f"{selected_news['source']}"
    )

    print(
        f"🔗 {selected_news['link']}"
    )

    # -----------------------------------------------------
    # Find image
    # -----------------------------------------------------

    image_url = selected_news.get(
        "image_url"
    )

    if not image_url:

        print(
            "⚠️ بۆ ئەم هەواڵە هیچ وێنەیەک نەدۆزرایەوە."
        )

        print(
            "⛔ بۆ پاراستنی کوالێتی، "
            "پۆستەکە بەبێ وێنە بڵاوناکرێتەوە."
        )

        return

    print(
        f"📸 وێنە: {image_url}"
    )

    # -----------------------------------------------------
    # Download image
    # -----------------------------------------------------

    image_path = download_image(
        image_url,
        "news_image.jpg"
    )

    if not image_path:

        print(
            "❌ نەتوانرا وێنەکە دابەزێندرێت."
        )

        return

    # -----------------------------------------------------
    # Publish to Facebook
    # -----------------------------------------------------

    facebook_response = (
        publish_photo_to_facebook(
            image_path,
            post
        )
    )

    # -----------------------------------------------------
    # Save history ONLY after success
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

        print("\n" + "=" * 60)
        print(
            "✅ پۆستەکە بە سەرکەوتوویی "
            "لە Facebook بڵاوکرایەوە."
        )

        print(
            "🔐 هەواڵەکە وەک پۆستکراو "
            "تۆمار کرا."
        )

        print("=" * 60)

    else:

        print("\n" + "=" * 60)
        print(
            "❌ Facebook پۆستەکەی "
            "قبوڵ نەکرد."
        )

        print(
            "⚠️ هەواڵەکە وەک پۆستکراو "
            "تۆمار نەکرا."
        )

        print("=" * 60)

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
