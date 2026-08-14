import os
import json
import hashlib
import re
import html
from urllib.parse import urljoin
from datetime import datetime, timezone

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
MAX_CANDIDATES = 12

# The ASO NEWS watermark file in GitHub.
LOGO_FILE = "logo.png"

FACEBOOK_PHOTO_URL = f"https://graph.facebook.com/{PAGE_ID}/photos"
FACEBOOK_VIDEO_URL = f"https://graph.facebook.com/{PAGE_ID}/videos"


# =========================================================
# NEWS SOURCES
# =========================================================
# More sources = ASO NEWS identity, not BBC-only.
RSS_SOURCES = [
    {
        "name": "Rudaw",
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Arudaw.net+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Kurdistan24",
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Akurdistan24.net+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
    },
    {
        "name": "DW",
        "url": "https://rss.dw.com/rdf/rss-en-all",
    },
    {
        "name": "France 24",
        "url": "https://www.france24.com/en/rss",
    },
    {
        "name": "Reuters",
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Areuters.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "AP News",
        "url": (
            "https://news.google.com/rss/search?"
            "q=site%3Aapnews.com+when%3A1d"
            "&hl=en-US&gl=US&ceid=US%3Aen"
        ),
    },
    {
        "name": "BBC News",
        "url": "https://feeds.bbci.co.uk/news/rss.xml",
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

                if news_id in posted_news:
                    continue

                all_news.append({
                    "id": news_id,
                    "source": source["name"],
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "entry": item,
                    "date": entry_date(item)
                })

        except Exception as e:
            print(
                f"⚠️ کێشە لە {source['name']}: {e}"
            )

    all_news.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    return all_news


# =========================================================
# SOURCE DIVERSITY
# =========================================================

def diverse_candidates(all_news):
    by_source = {}

    for item in all_news:
        by_source.setdefault(
            item["source"],
            []
        ).append(item)

    # Maximum 3 candidates per source.
    for source in by_source:
        by_source[source] = by_source[source][:3]

    result = []
    round_number = 0
    sources = list(by_source.keys())

    while len(result) < MAX_CANDIDATES:
        added = False

        for source in sources:
            items = by_source[source]

            if round_number < len(items):
                result.append(
                    items[round_number]
                )

                added = True

                if len(result) >= MAX_CANDIDATES:
                    break

        if not added:
            break

        round_number += 1

    return result


# =========================================================
# GEMINI WRITER
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
تۆ دەستکارێکی هەواڵی پیشەیی بۆ ASO NEWS ـیت.

لە نێوان هەواڵەکانی خوارەوە تەنها یەک هەواڵ هەڵبژێرە
و بە کوردی سۆرانیی ڕەوان و بێ هەڵەی تایپی بیگۆڕە بۆ پۆستی Facebook.

یاساکان:
- هیچ زانیارییەکی خۆت زیاد مەکە.
- هیچ شتێک مەخەمنە.
- ژمارە و بەروارەکان مەگۆڕە.
- ناوی کەس و شوێن مەگۆڕە.
- شیکاری سیاسی مەکە.
- سەردێڕ کورت و ڕوون بێت.
- دەقەکە کورت و زانیاری‌دار بێت.
- ئەگەر هەمان ڕووداو لە چەند سەرچاوەیەکدا هەبوو،
  تەنها یەکێکیان هەڵبژێرە.
- سەرچاوەکە بە دروستی بنووسە.
- هەوڵ بدە سەرچاوەکان جۆراوجۆر بن، نەک تەنها BBC.

فۆرمات:
SOURCE_NUMBER: ژمارە

TITLE: سەردێڕ

BODY:
دەقی هەواڵ

HASHTAGS:
#ASONEWS #هەواڵ #کوردستان

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
        print(f"❌ کێشە لە Gemini: {e}")
        return None


# =========================================================
# PARSE GEMINI
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

    return {
        "source_number": source_number,
        "title": title,
        "body": body,
        "hashtags": hashtags,
        "source_name": source_name
    }


def build_post(parsed):
    return (
        f"📰 {parsed['title']}\n\n"
        f"{parsed['body']}\n\n"
        f"{parsed['hashtags']}\n\n"
        f"سەرچاوە: {parsed['source_name']}"
    )


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

def main():
    print("\n" + "=" * 60)
    print("🇹🇯 ASO NEWS — AUTO PUBLISHER")
    print("=" * 60)

    all_news = collect_news()

    if not all_news:
        print(
            "ℹ️ هیچ هەواڵێکی نوێ نییە."
        )
        return

    print(
        f"✅ {len(all_news)} هەواڵی نوێ دۆزرایەوە."
    )

    candidates = diverse_candidates(
        all_news
    )

    print("\n📊 هەواڵەکانی Gemini:")
    for i, item in enumerate(
        candidates,
        start=1
    ):
        print(
            f"{i}. [{item['source']}] "
            f"{item['title']}"
        )

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

    post = build_post(
        parsed
    )

    print("\n" + "=" * 60)
    print("📰 ASO NEWS — FINAL POST")
    print("=" * 60)
    print(post)

    # -----------------------------------------------------
    # Find media
    # -----------------------------------------------------

    print("\n📸/🎥 بەدوای میدیادا دەگەڕێین...")

    image_candidates, video_candidates = find_media(
        selected_news["entry"]
    )

    facebook_response = None

    # Prefer a direct video if the source exposes one.
    if video_candidates:
        video_path = download_video(
            video_candidates[0]
        )

        if video_path:
            facebook_response = publish_video(
                video_path,
                post
            )

    # Otherwise use a branded photo.
    if facebook_response is None:
        image_path = download_best_image(
            image_candidates
        )

        if not image_path:
            print(
                "⛔ هیچ وێنەیەکی کوالێتی باش نەدۆزرایەوە."
            )
            return

        branded_image = add_aso_logo(
            image_path
        )

        facebook_response = publish_photo(
            branded_image,
            post
        )

    # -----------------------------------------------------
    # Save history only after successful Facebook post.
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
