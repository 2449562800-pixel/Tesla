#!/usr/bin/env python3
"""
News Bot v4 — Refined Daily Briefing System

  Morning 08:00 : X/Twitter Tesla core bloggers (FSD + tech only)
  Noon    12:00 : Chinese NEV dynamics (NIO/Li Auto/XPeng/Xiaomi/AITO)
  Evening 17:30 : Global frontier tech (AI/biotech/space/robotics)

Cloud-only (GitHub Actions) · Precise timing · Global dedup
Dual push: WeChat (Server酱 Markdown) + iCloud Email (HTML)
"""

import os, sys, smtplib, re, time, hashlib, feedparser, requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from html import unescape

# ============================================================
# Configuration
# ============================================================
SCT_SENDKEY = os.environ.get("SCT_SENDKEY", "")
ICLOUD_USER = os.environ.get("ICLOUD_USER", "")
ICLOUD_PASS = os.environ.get("ICLOUD_PASS", "")
REPORT_TYPE = sys.argv[1] if len(sys.argv) > 1 else "morning"

BEIJING = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; NewsBot/4.0)"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORTS = {
    "morning":  {"title": "特斯拉晨报",   "emoji": "🌅", "hours": 12, "max": 15},
    "noon":     {"title": "新能源午报",   "emoji": "⚡", "hours": 8,  "max": 15},
    "evening":  {"title": "前沿科技晚报", "emoji": "🔬", "hours": 10, "max": 15},
}

# ============================================================
# Morning: X/Twitter Account Sources
# ============================================================
TWITTER_ACCOUNTS = [
    {"handle": "SawyerMerritt",    "name": "Sawyer Merritt",    "zh": "Sawyer Merritt"},
    {"handle": "ChuckCook95",      "name": "Chuck Cook",       "zh": "Chuck Cook"},
    {"handle": "greentheonly",     "name": "green",             "zh": "green"},
    {"handle": "DirtyTesla",       "name": "Dirty Tesla",       "zh": "Dirty Tesla"},
    {"handle": "brandonee916",     "name": "Brandon",           "zh": "Brandon"},
    {"handle": "WholeMarsBlog",    "name": "Whole Mars Catalog", "zh": "Whole Mars"},
    {"handle": "elonmusk",         "name": "Elon Musk",         "zh": "马斯克"},
    {"handle": "Tesla_AI",         "name": "Tesla AI",          "zh": "Tesla AI"},
    {"handle": "Tesla",            "name": "Tesla",             "zh": "Tesla官方"},
]

# Nitter instances for RSS fallback
NITTER_INSTANCES = [
    "nitter.poast.org",
    "nitter.privacydev.net",
    "nitter.woodland.cafe",
    "nitter.d420.de",
]

# Cached working Nitter instance (discovered at runtime)
_working_nitter = None

def _find_working_nitter():
    """Quick probe to find a working Nitter instance. Returns None if none work."""
    global _working_nitter
    if _working_nitter is not None:
        return _working_nitter
    for instance in NITTER_INSTANCES:
        try:
            r = requests.get(f"https://{instance}/elonmusk/rss", timeout=3,
                           headers={"User-Agent": UA}, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 100:
                _working_nitter = instance
                print(f"  ✅ Nitter可用: {instance}")
                return instance
        except Exception:
            continue
    print("  ⚠ 所有Nitter实例不可用，跳过Twitter源")
    return None

# Morning keyword filter (only keep FSD/tech-related content)
MORNING_FILTER_KW = [
    "fsd", "full self-driving", "autopilot", "self-driving", "autonomous",
    "tesla", "model y", "model 3", "model s", "model x", "cybertruck",
    "optimus", "robotaxi", "robot", "software update", "ota",
    "superc", "charging", "giga", "battery", "megapack",
    "hw4", "hw3", "vision", "neural net", "phantom braking",
    "summon", "smart summon", "park assist", "auto steer",
    "navigate on autopilot", "noa", "lane change", "merge",
]

# Morning supplemental RSS feeds (Tesla news sites that cite these bloggers)
MORNING_RSS_FEEDS = [
    {"name": "Electrek", "url": "https://electrek.co/feed/", "lang": "en",
     "keywords": ["tesla", "fsd", "autopilot", "musk", "model y", "model 3",
                  "cybertruck", "robotaxi", "optimus", "software update"]},
    {"name": "TeslaRati", "url": "https://www.teslarati.com/feed/", "lang": "en",
     "keywords": ["tesla", "fsd", "autopilot", "musk", "model y", "model 3",
                  "cybertruck", "robotaxi", "optimus"]},
    {"name": "Not a Tesla App", "url": "https://www.notateslaapp.com/rss", "lang": "en",
     "keywords": ["tesla", "fsd", "autopilot", "software", "update", "model y",
                  "model 3", "cybertruck", "supercharger"]},
    {"name": "YouTube FSD实测", "url": "https://www.youtube.com/feeds/videos.xml?search_query=tesla+fsd+test+drive+2025", "lang": "en",
     "keywords": ["fsd", "tesla", "full self-driving", "autopilot"], "type": "video"},
    {"name": "YouTube特斯拉", "url": "https://www.youtube.com/feeds/videos.xml?search_query=tesla+update+review+2025", "lang": "en",
     "keywords": ["tesla", "update", "review", "fsd"], "type": "video"},
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["特斯拉", "Tesla", "FSD", "自动驾驶", "马斯克", "Model Y",
                  "Cybertruck", "Robotaxi", "Optimus", "超级充电"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["特斯拉", "Tesla", "FSD", "马斯克", "Model Y", "自动驾驶"]},
]

# ============================================================
# Noon: Chinese NEV Brand Sources
# ============================================================
NOON_BRANDS = [
    {"name": "蔚来", "en": "NIO", "founder": "李斌",
     "keywords": ["蔚来", "NIO", "李斌", "ET5", "ET7", "ES6", "ES8", "EC6",
                  "NOP+", "蔚来自动驾驶", "换电", "蔚来智驾"]},
    {"name": "理想", "en": "Li Auto", "founder": "李想",
     "keywords": ["理想", "Li Auto", "李想", "L6", "L7", "L8", "L9", "MEGA",
                  "理想智驾", "AD Max", "AD Pro", "理想NOA", "端到端"]},
    {"name": "小鹏", "en": "XPeng", "founder": "何小鹏",
     "keywords": ["小鹏", "XPeng", "何小鹏", "G6", "G9", "P7", "X9", "MONA",
                  "XNGP", "天玑", "小鹏智驾", "端到端", "小鹏NOA"]},
    {"name": "小米", "en": "Xiaomi Auto", "founder": "雷军",
     "keywords": ["小米汽车", "小米SU7", "雷军", "Xiaomi Auto", "小米智驾",
                  "小米NOA", "城市领航", "端到端"]},
    {"name": "问界", "en": "AITO", "founder": "余承东",
     "keywords": ["问界", "AITO", "余承东", "M5", "M7", "M9", "享界", "S7",
                  "华为智驾", "华为ADS", "鸿蒙智行", "乾崑", "NCA"]},
]

NOON_RSS_FEEDS = [
    {"name": "36氪汽车", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["新能源", "蔚来", "理想", "小鹏", "小米汽车", "问界", "比亚迪",
                  "智驾", "NOA", "自动驾驶", "华为ADS", "鸿蒙智行", "电车",
                  "续航", "OTA", "端到端", "交付", "销量"]},
    {"name": "IT之家汽车", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["新能源", "蔚来", "理想", "小鹏", "小米汽车", "问界", "智驾",
                  "自动驾驶", "华为ADS", "NOA", "OTA", "续航", "交付"]},
    {"name": "懂车帝", "url": "https://www.dongchedi.com/rss", "lang": "zh",
     "keywords": ["新能源", "蔚来", "理想", "小鹏", "小米SU7", "问界", "智驾",
                  "自动驾驶", "OTA", "续航", "交付"]},
    {"name": "汽车之家", "url": "https://www.autohome.com.cn/rss", "lang": "zh",
     "keywords": ["新能源", "蔚来", "理想", "小鹏", "小米SU7", "问界", "智驾",
                  "自动驾驶", "OTA", "续航"]},
    {"name": "InsideEVs", "url": "https://insideevs.com/rssfeeds/all.xml", "lang": "en",
     "keywords": ["NIO", "Li Auto", "XPeng", "Xiaomi", "AITO", "BYD", "Zeekr",
                  "Chinese EV", "smart driving", "Huawei", "NOA"]},
    {"name": "CarNewsChina", "url": "https://www.carnewschina.com/feed/", "lang": "en",
     "keywords": ["NIO", "Li Auto", "XPeng", "Xiaomi", "AITO", "Huawei",
                  "smart driving", "EV", "China", "sales"]},
]

# Weibo founder accounts (RSSHub routes)
WEIBO_FOUNDERS = [
    {"name": "李想", "brand": "理想", "uid": "1749126163"},
    {"name": "何小鹏", "brand": "小鹏", "uid": "1771926952"},
    {"name": "雷军", "brand": "小米", "uid": "1749405855"},
    {"name": "李斌", "brand": "蔚来", "uid": "1749405855"},
    {"name": "余承东", "brand": "问界", "uid": "1749405855"},
]

# ============================================================
# Evening: Frontier Tech Sources
# ============================================================
EVENING_DOMAINS = [
    {"tag": "AI", "icon": "🤖", "keywords": [
        "ai", "artificial intelligence", "gpt", "llm", "openai", "claude",
        "gemini", "deep learning", "model", "nvidia", "chatgpt", "copilot",
        "agent", "reasoning", "foundation model", "transformer", "diffusion",
        "人工智能", "大模型", "GPT", "芯片", "英伟达"]},
    {"tag": "机器人", "icon": "🦾", "keywords": [
        "robot", "robotics", "embodied", "humanoid", "boston dynamics",
        "figure", "tesla bot", "optimus", "manipulation", "locomotion",
        "具身智能", "机器人", "人形机器人"]},
    {"tag": "生物", "icon": "🧬", "keywords": [
        "gene", "crispr", "biotech", "drug", "cancer", "protein", "cell",
        "vaccine", "therapy", "clinical", "stem cell", "mrna", "genomics",
        "生物", "基因", "CRISPR", "疫苗", "蛋白质", "癌症", "细胞"]},
    {"tag": "航天", "icon": "🚀", "keywords": [
        "spacex", "nasa", "rocket", "mars", "moon", "orbit", "satellite",
        "starship", "falcon", "blue origin", "launch", "space", "payload",
        "航天", "火箭", "SpaceX", "火星", "星舰"]},
    {"tag": "芯片", "icon": "💡", "keywords": [
        "chip", "semiconductor", "tsmc", "intel", "amd", "nanometer", "3nm",
        "lithography", "asml", "fab", "processor", "gpu", "tpu",
        "芯片", "半导体", "台积电", "光刻机"]},
]

EVENING_RSS_FEEDS = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "lang": "en",
     "keywords": ["ai", "openai", "google", "nvidia", "model", "robot", "chip", "breakthrough"]},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "lang": "en",
     "keywords": ["ai", "openai", "nvidia", "model", "robot", "startup", "agent"]},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "lang": "en",
     "keywords": ["ai", "biotech", "gene", "quantum", "breakthrough", "robot", "research", "space"]},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en",
     "keywords": ["ai", "openai", "apple", "google", "nvidia", "robot", "chip", "space"]},
    {"name": "Science Daily", "url": "https://www.sciencedaily.com/rss/top.xml", "lang": "en",
     "keywords": ["breakthrough", "discovery", "gene", "cancer", "quantum", "ai", "space", "protein"]},
    {"name": "Nature", "url": "https://www.nature.com/nature.rss", "lang": "en",
     "keywords": ["breakthrough", "gene", "crispr", "ai", "quantum", "protein", "cell", "cancer"]},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "lang": "en",
     "keywords": ["ai", "apple", "google", "nvidia", "space", "spacex", "robot", "chip", "science"]},
    {"name": "36氪科技", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["AI", "人工智能", "大模型", "GPT", "芯片", "量子", "生物",
                  "基因", "科学", "突破", "OpenAI", "英伟达", "苹果", "微软",
                  "机器人", "SpaceX", "脑机", "核聚变"]},
    {"name": "IT之家科技", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["AI", "人工智能", "大模型", "芯片", "量子", "生物", "基因",
                  "OpenAI", "英伟达", "苹果", "微软", "脑机", "核聚变"]},
    {"name": "Wired Science", "url": "https://www.wired.com/feed/rss", "lang": "en",
     "keywords": ["ai", "science", "space", "biotech", "robot", "quantum", "breakthrough", "nvidia"]},
]


# ============================================================
# Utility Functions
# ============================================================
def clean_html(text):
    text = unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    for p in [r'Read more.*', r'Continue reading.*', r'Click here.*',
              r'Source:.*', r'Image via.*', r'\[…\]', r'\.{3,}',
              r'Photo credit.*', r'Posted by.*', r'Leave a comment.*',
              r'The post .* appeared first.*', r'\[.*\]$']:
        text = re.sub(p, '', text, flags=re.IGNORECASE).strip()
    return text


def truncate(text, max_len=180):
    if not text or len(text) <= max_len:
        return text
    return text[:max_len].rstrip(' .,:;！？，。、；：""''…') + "…"


def is_chinese(text):
    if not text:
        return False
    return len(re.findall(r'[\u4e00-\u9fff]', text)) > len(text) * 0.1


def parse_time(entry):
    try:
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub:
            return datetime(*pub[:6], tzinfo=timezone.utc).astimezone(BEIJING)
    except Exception:
        pass
    return None


def fmt_time(dt):
    if dt:
        return f"{dt.year}-{dt.month:02d}-{dt.day:02d} {dt.hour:02d}:{dt.minute:02d}"
    now = datetime.now(BEIJING)
    return f"{now.year}-{now.month:02d}-{now.day:02d}"


def fmt_time_short(dt):
    if dt:
        return f"{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
    return ""


def within_hours(entry, hours):
    dt = parse_time(entry)
    if not dt:
        return True
    return (datetime.now(BEIJING) - dt).total_seconds() <= hours * 3600


def fingerprint(text):
    """Generate a fingerprint for dedup: normalize + hash."""
    norm = re.sub(r'[\s\-_|,，.。:：!！?？\(\)【】《》]+', '', text.lower())
    norm = re.sub(r'[0-9]+', 'N', norm)
    return hashlib.md5(norm[:60].encode()).hexdigest()[:12]


def similarity(s1, s2):
    """Simple character-overlap similarity for dedup."""
    if not s1 or not s2:
        return 0
    set1 = set(re.sub(r'[\s\-_|,，.。:：!！?？]+', '', s1.lower()))
    set2 = set(re.sub(r'[\s\-_|,，.。:：!！?？]+', '', s2.lower()))
    if not set1 or not set2:
        return 0
    return len(set1 & set2) / max(len(set1), len(set2))


# ============================================================
# Translation (Free, no API key)
# ============================================================
_translate_session = None

def _get_session():
    """Create a session with retry strategy for translation requests."""
    global _translate_session
    if _translate_session is None:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        _translate_session = requests.Session()
        retries = Retry(total=1, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        _translate_session.mount("https://", HTTPAdapter(max_retries=retries))
        _translate_session.mount("http://", HTTPAdapter(max_retries=retries))
    return _translate_session


def translate(text):
    """Translate English to Chinese via free APIs. Never crashes."""
    if not text or len(text) < 3 or is_chinese(text):
        return text

    sess = _get_session()

    # Google Translate (unofficial)
    try:
        r = sess.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text[:1200]},
            timeout=6, headers={"User-Agent": UA},
        )
        if r.status_code == 200:
            parts = r.json()
            result = "".join(p[0] for p in parts[0] if p[0])
            if result and is_chinese(result):
                return result
    except Exception:
        pass
    time.sleep(0.2)

    # MyMemory fallback
    try:
        r = sess.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": "en|zh-CN"}, timeout=6,
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("responseStatus") == 200:
                t = d["responseData"]["translatedText"]
                if t != text and is_chinese(t):
                    return t
    except Exception:
        pass
    return text


# ============================================================
# X/Twitter Fetching (Nitter RSS + RSSHub)
# ============================================================
def fetch_twitter_account(account, hours):
    """Fetch tweets from a specific X/Twitter account via Nitter RSS."""
    handle = account["handle"]
    results = []

    instance = _find_working_nitter()
    if not instance:
        return results

    url = f"https://{instance}/{handle}/rss"
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": UA},
                       allow_redirects=True)
        if r.status_code != 200:
            return results
        d = feedparser.parse(r.text)
        if not d.entries:
            return results

        for entry in d.entries[:10]:
            if not within_hours(entry, hours):
                continue

            title = clean_html(entry.get("title", ""))
            summary = clean_html(entry.get("summary", "") or entry.get("description", ""))
            link = entry.get("link", "")

            # Convert nitter link back to x.com
            if link and instance in link:
                link = link.replace(f"https://{instance}/", "https://x.com/")

            # Filter: only keep FSD/tech-related content
            text_lower = (title + " " + summary).lower()
            if not any(k in text_lower for k in MORNING_FILTER_KW):
                continue

            dt = parse_time(entry)

            # Translate if not Chinese
            if not is_chinese(title):
                title = translate(title)
                time.sleep(0.15)
            if summary and not is_chinese(summary):
                summary = translate(summary)
                time.sleep(0.15)

            results.append({
                "title": title,
                "source": f"@{handle}",
                "source_name": account["zh"],
                "time": fmt_time(dt),
                "time_short": fmt_time_short(dt),
                "summary": truncate(summary, 150) if summary else "",
                "link": link,
                "is_video": False,
                "is_tweet": True,
                "author_handle": handle,
                "author_name": account["zh"],
            })
    except Exception:
        pass

    # Fallback: try RSSHub Twitter
    if not results:
        try:
            url = f"https://rsshub.app/twitter/user/{handle}"
            r = requests.get(url, timeout=4, headers={"User-Agent": UA})
            if r.status_code == 200:
                d = feedparser.parse(r.text)
                for entry in d.entries[:10]:
                    if not within_hours(entry, hours):
                        continue
                    title = clean_html(entry.get("title", ""))
                    summary = clean_html(entry.get("summary", ""))
                    link = entry.get("link", "")
                    text_lower = (title + " " + summary).lower()
                    if not any(k in text_lower for k in MORNING_FILTER_KW):
                        continue
                    dt = parse_time(entry)
                    if not is_chinese(title):
                        title = translate(title)
                        time.sleep(0.15)
                    if summary and not is_chinese(summary):
                        summary = translate(summary)
                        time.sleep(0.15)
                    results.append({
                        "title": title,
                        "source": f"@{handle}",
                        "source_name": account["zh"],
                        "time": fmt_time(dt),
                        "time_short": fmt_time_short(dt),
                        "summary": truncate(summary, 150) if summary else "",
                        "link": link,
                        "is_video": False,
                        "is_tweet": True,
                        "author_handle": handle,
                        "author_name": account["zh"],
                    })
        except Exception:
            pass

    if results:
        print(f"  @{handle}: {len(results)} 条")
    return results


# ============================================================
# Weibo Founder Fetching (RSSHub)
# ============================================================
def fetch_weibo_user(founder, hours):
    """Fetch Weibo posts from a founder's account via RSSHub."""
    uid = founder["uid"]
    results = []

    # Try RSSHub Weibo user timeline
    try:
        url = f"https://rsshub.app/weibo/user/{uid}"
        r = requests.get(url, timeout=10, headers={"User-Agent": UA})
        if r.status_code == 200:
            d = feedparser.parse(r.text)
            for entry in d.entries[:8]:
                if not within_hours(entry, hours):
                    continue
                title = clean_html(entry.get("title", ""))
                summary = clean_html(entry.get("summary", "") or entry.get("description", ""))
                link = entry.get("link", "")
                dt = parse_time(entry)

                # Filter for auto/tech relevance
                brand_kw = []
                for b in NOON_BRANDS:
                    if b["name"] == founder["brand"]:
                        brand_kw = [k.lower() for k in b["keywords"]]
                        break
                text_lower = (title + " " + summary).lower()
                if brand_kw and not any(k in text_lower for k in brand_kw):
                    # Keep anyway if from founder (important voice)
                    pass

                results.append({
                    "title": title or truncate(summary, 50),
                    "source": f"微博·{founder['name']}",
                    "source_name": founder["name"],
                    "time": fmt_time(dt),
                    "time_short": fmt_time_short(dt),
                    "summary": truncate(summary, 150) if summary else "",
                    "link": link,
                    "is_video": False,
                    "is_tweet": False,
                    "is_weibo": True,
                    "brand": founder["brand"],
                    "category": "创始人动态",
                })
    except Exception:
        pass

    if results:
        print(f"  微博·{founder['name']}: {len(results)} 条")
    return results


# ============================================================
# Standard RSS Feed Fetching
# ============================================================
def fetch_feed(feed, hours, extra_filter=None):
    """Fetch and parse a standard RSS feed."""
    try:
        r = requests.get(feed["url"], timeout=10, headers={"User-Agent": UA})
        if r.status_code != 200:
            return []
        d = feedparser.parse(r.text)
        if not d.entries:
            return []

        kw = [k.lower() for k in feed["keywords"]]
        lang = feed["lang"]
        is_video = feed.get("type") == "video"
        results = []

        for entry in d.entries[:25]:
            if not within_hours(entry, hours):
                continue

            title = clean_html(entry.get("title", ""))
            summary = clean_html(entry.get("summary", "") or entry.get("description", ""))

            if not title or len(title) < 4:
                continue

            # Keyword match
            text_lower = (title + " " + summary).lower()
            if not any(k in text_lower for k in kw):
                continue

            # Extra filter (for morning FSD filter etc.)
            if extra_filter and not any(k in text_lower for k in extra_filter):
                continue

            dt = parse_time(entry)

            # Translate English content
            if lang == "en":
                title = translate(title)
                time.sleep(0.15)
                if summary:
                    summary = translate(summary)
                    time.sleep(0.15)

            # Remove title duplication from summary
            if summary and len(title) > 6:
                prefix = title[:15]
                if prefix in summary:
                    summary = re.sub(r'^[\s\-_|,，：:]*' + re.escape(prefix), '', summary).strip()

            # Detect if it's a video (YouTube links)
            link = entry.get("link", "")
            if "youtube.com" in link or "youtu.be" in link:
                is_video = True

            results.append({
                "title": title,
                "source": feed["name"],
                "source_name": feed["name"],
                "time": fmt_time(dt),
                "time_short": fmt_time_short(dt),
                "summary": truncate(summary, 160) if summary else "",
                "link": link,
                "is_video": is_video,
                "is_tweet": False,
                "is_weibo": False,
            })

        return results
    except Exception as e:
        print(f"  ⚠ {feed['name']}: {e}")
        return []


# ============================================================
# Global Deduplication
# ============================================================
def dedup(items):
    """Remove duplicates using fingerprint + similarity."""
    seen_fps = []
    seen_texts = []
    unique = []

    for item in items:
        title = item.get("title", "")
        fp = fingerprint(title)

        # Check fingerprint match
        if fp in seen_fps:
            continue

        # Check content similarity (threshold 0.65)
        is_dup = False
        title_clean = re.sub(r'[\s\-_|,，.。:：!！?？]+', '', title.lower())
        for existing in seen_texts:
            if similarity(title_clean, existing) > 0.65:
                is_dup = True
                break

        if is_dup:
            continue

        seen_fps.append(fp)
        seen_texts.append(title_clean)
        unique.append(item)

    return unique


# ============================================================
# Morning: Fetch + Organize
# ============================================================
def fetch_morning():
    """Morning: X/Twitter bloggers + supplemental RSS."""
    cfg = REPORTS["morning"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")

    all_items = []

    # 1) X/Twitter accounts (primary source)
    print("  📡 抓取 X/Twitter 博主动态...")
    for account in TWITTER_ACCOUNTS:
        items = fetch_twitter_account(account, cfg["hours"])
        all_items.extend(items)
        time.sleep(0.5)

    # 2) Supplemental RSS feeds
    print("  📡 抓取 RSS 补充源...")
    for feed in MORNING_RSS_FEEDS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
            # Mark these as supplemental (not tweets)
            for item in items:
                item["is_tweet"] = False
            all_items.extend(items)

    all_items = dedup(all_items)

    # Organize: tweets first, then supplemental
    tweets = [i for i in all_items if i.get("is_tweet")]
    videos = [i for i in all_items if i.get("is_video")]
    others = [i for i in all_items if not i.get("is_tweet") and not i.get("is_video")]

    # Limit total to 10-15
    selected = tweets[:12]
    remaining = cfg["max"] - len(selected)
    if remaining > 0 and videos:
        selected.extend(videos[:min(remaining, 2)])
        remaining = cfg["max"] - len(selected)
    if remaining > 0 and others:
        selected.extend(others[:remaining])

    print(f"  共 {len(selected)} 条（推文 {len(tweets)} / 视频 {len(videos)} / 资讯 {len(others)}）")
    return selected


# ============================================================
# Noon: Fetch + Organize
# ============================================================
def fetch_noon():
    """Noon: Chinese NEV by brand + founder Weibo + owner feedback."""
    cfg = REPORTS["noon"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")

    all_items = []

    # 1) Weibo founder accounts
    print("  📡 抓取创始人微博...")
    for founder in WEIBO_FOUNDERS:
        items = fetch_weibo_user(founder, cfg["hours"])
        all_items.extend(items)
        time.sleep(0.5)

    # 2) RSS feeds for NEV news
    print("  📡 抓取新能源资讯...")
    for feed in NOON_RSS_FEEDS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
            # Auto-assign brand
            for item in items:
                item["brand"] = assign_brand(item["title"] + " " + item.get("summary", ""))
                item["category"] = "智驾/车型"
                item["is_weibo"] = False
            all_items.extend(items)

    all_items = dedup(all_items)

    # Organize by brand
    brand_items = {}
    for brand_info in NOON_BRANDS:
        brand_items[brand_info["name"]] = []

    # Uncategorized
    brand_items["其他"] = []

    for item in all_items:
        b = item.get("brand", "")
        if b in brand_items:
            brand_items[b].append(item)
        else:
            brand_items["其他"].append(item)

    # Select top items per brand, total 10-15
    selected = []
    per_brand = max(2, cfg["max"] // len(NOON_BRANDS))
    for brand_name in [b["name"] for b in NOON_BRANDS] + ["其他"]:
        items = brand_items.get(brand_name, [])
        selected.extend(items[:per_brand])

    # Trim to max
    selected = selected[:cfg["max"]]

    total = len(selected)
    brand_counts = {b: len(brand_items.get(b, [])) for b in [b["name"] for b in NOON_BRANDS]}
    print(f"  共 {total} 条（" + " / ".join(f"{k}{v}条" for k, v in brand_counts.items()) + "）")
    return selected, brand_items


def assign_brand(text):
    """Auto-assign a brand based on content keywords."""
    text_lower = text.lower()
    best_brand = ""
    best_score = 0
    for brand_info in NOON_BRANDS:
        score = sum(1 for k in brand_info["keywords"] if k.lower() in text_lower)
        if score > best_score:
            best_score = score
            best_brand = brand_info["name"]
    return best_brand if best_score >= 1 else "其他"


# ============================================================
# Evening: Fetch + Organize
# ============================================================
def fetch_evening():
    """Evening: Frontier tech with domain tags."""
    cfg = REPORTS["evening"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")

    all_items = []

    for feed in EVENING_RSS_FEEDS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
            all_items.extend(items)

    all_items = dedup(all_items)

    # Assign domain tags
    for item in all_items:
        item["domain"] = assign_domain(item["title"] + " " + item.get("summary", ""))

    # Organize by domain, select 10-15
    domain_items = {}
    for domain in EVENING_DOMAINS:
        domain_items[domain["tag"]] = []

    for item in all_items:
        tag = item.get("domain", "AI")
        if tag in domain_items:
            domain_items[tag].append(item)
        else:
            domain_items["AI"].append(item)

    # Select evenly across domains
    selected = []
    per_domain = max(2, cfg["max"] // len(EVENING_DOMAINS))
    for domain in EVENING_DOMAINS:
        items = domain_items.get(domain["tag"], [])
        selected.extend(items[:per_domain])

    # Fill remaining slots
    remaining = cfg["max"] - len(selected)
    if remaining > 0:
        unselected = [i for i in all_items if i not in selected]
        selected.extend(unselected[:remaining])

    selected = selected[:cfg["max"]]

    total = len(selected)
    domain_counts = {d["tag"]: len([i for i in selected if i.get("domain") == d["tag"]]) for d in EVENING_DOMAINS}
    active = {k: v for k, v in domain_counts.items() if v > 0}
    print(f"  共 {total} 条（" + " / ".join(f"【{k}】{v}条" for k, v in active.items()) + "）")
    return selected


def assign_domain(text):
    """Assign a domain tag based on content keywords."""
    text_lower = text.lower()
    best_tag = "AI"
    best_score = 0
    for domain in EVENING_DOMAINS:
        score = sum(1 for k in domain["keywords"] if k.lower() in text_lower)
        if score > best_score:
            best_score = score
            best_tag = domain["tag"]
    return best_tag


# ============================================================
# Format: WeChat Push (Server酱) — Markdown
# ============================================================
def push_wechat_morning(items):
    """Morning WeChat: blogger-centric format."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    lines = [
        f"## 🌅 特斯拉晨报",
        f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条",
        "",
    ]

    for item in items:
        if item.get("is_tweet"):
            handle = item.get("author_handle", "")
            name = item.get("author_name", handle)
            time_str = item.get("time", "")

            lines.append(f"## **@{handle} ({name})** · 发布时间：{time_str}")
            lines.append(f"📝 **内容摘要**：{item['title']}")
            if item.get("summary"):
                lines.append(f"💡 {item['summary']}")
            if item.get("link"):
                lines.append(f"🔗 **相关链接**：[{item['link']}]({item['link']})")
            lines.append("")
        elif item.get("is_video"):
            lines.append(f"🎬 **{item['title']}**")
            lines.append(f"_{item['source']}  ·  {item.get('time_short', '')}_")
            if item.get("summary"):
                lines.append(f"> {item['summary']}")
            if item.get("link"):
                lines.append(f"🔗 [视频链接]({item['link']})")
            lines.append("")
        else:
            lines.append(f"**{item['title']}**")
            lines.append(f"_{item['source']}  ·  {item.get('time_short', '')}_")
            if item.get("summary"):
                lines.append(f"> {item['summary']}")
            lines.append("")

    lines.append("---")
    lines.append("_🤖 云端自动采集 · X/Twitter博主动态_")
    return "\n".join(lines)


def push_wechat_noon(items, brand_items):
    """Noon WeChat: brand-organized format."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    lines = [
        f"## ⚡ 新能源午报",
        f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条",
        "",
    ]

    for brand_info in NOON_BRANDS:
        brand_name = brand_info["name"]
        brand_list = [i for i in items if i.get("brand") == brand_name]
        if not brand_list:
            continue

        lines.append(f"### 🚗 {brand_name}（{brand_info['en']}）")
        lines.append("")

        for item in brand_list:
            cat = item.get("category", "")
            cat_tag = f"【{cat}】" if cat else ""

            if item.get("is_weibo"):
                founder = item.get("source_name", "")
                lines.append(f"👤 **{founder}（{brand_name}）** · {item.get('time_short', '')}")
                lines.append(f"{cat_tag} {item['title']}")
                if item.get("summary"):
                    lines.append(f"> {item['summary']}")
            else:
                lines.append(f"{cat_tag} **{item['title']}**")
                lines.append(f"_{item['source']}  ·  {item.get('time_short', '')}_")
                if item.get("summary"):
                    lines.append(f"> {item['summary']}")
            if item.get("link"):
                lines.append(f"🔗 [原文链接]({item['link']})")
            lines.append("")

    lines.append("---")
    lines.append("_🤖 云端自动采集 · 新能源智驾动态_")
    return "\n".join(lines)


def push_wechat_evening(items):
    """Evening WeChat: domain-tagged format."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    lines = [
        f"## 🔬 前沿科技晚报",
        f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条",
        "",
    ]

    # Group by domain
    domain_order = [d["tag"] for d in EVENING_DOMAINS]
    domain_icons = {d["tag"]: d["icon"] for d in EVENING_DOMAINS}

    for domain in domain_order:
        domain_list = [i for i in items if i.get("domain") == domain]
        if not domain_list:
            continue

        icon = domain_icons.get(domain, "🔬")
        lines.append(f"### {icon} {domain}")
        lines.append("")

        for item in domain_list:
            # Format: 【领域标签】标题 + 150字核心总结
            title = item["title"]
            summary = item.get("summary", "")
            core = f" {summary}" if summary else ""
            lines.append(f"【{domain}】**{title}**")
            if core:
                lines.append(f"{core}")
            lines.append(f"_{item['source']}  ·  {item.get('time_short', '')}_")
            if item.get("link"):
                lines.append(f"🔗 [原文链接]({item['link']})")
            lines.append("")

    lines.append("---")
    lines.append("_🤖 云端自动采集 · 前沿科技资讯_")
    return "\n".join(lines)


def push_wechat(items, cfg, brand_items=None):
    """Dispatch to the right WeChat formatter."""
    print("[2/3] 正在推送微信...")

    if REPORT_TYPE == "morning":
        content = push_wechat_morning(items)
    elif REPORT_TYPE == "noon":
        content = push_wechat_noon(items, brand_items or {})
    else:
        content = push_wechat_evening(items)

    now = datetime.now(BEIJING)

    if SCT_SENDKEY:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SCT_SENDKEY}.send",
            json={
                "title": f"{cfg['emoji']} {cfg['title']}（{now.month}月{now.day}日）",
                "desp": content,
            },
            timeout=30,
        )
        r = resp.json()
        if r.get("code") == 0:
            print("  ✅ 微信推送成功")
        else:
            print(f"  ❌ 微信推送失败: {r}")
    else:
        print("  ⚠ 跳过微信推送（无SCT_SENDKEY）")

    return content


# ============================================================
# Format: Email Push (iCloud) — HTML
# ============================================================
def push_email_morning(items):
    """Morning email: blogger-centric cards."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    c1, c2 = "#e82127", "#c41e24"

    cards = ""
    for item in items:
        if item.get("is_tweet"):
            handle = item.get("author_handle", "")
            name = item.get("author_name", handle)
            time_str = item.get("time", "")

            # Author header
            cards += f'''
            <div style="padding:16px;background:#fafafa;border-radius:10px;margin-bottom:12px;border-left:4px solid {c1};">
                <div style="font-weight:700;color:{c1};font-size:14px;margin-bottom:6px;">
                    @{handle} ({name}) <span style="color:#999;font-weight:400;font-size:12px;margin-left:8px;">发布时间：{time_str}</span>
                </div>
                <div style="color:#1a1a1a;font-size:15px;line-height:1.7;">
                    📝 <strong>内容摘要</strong>：{item['title']}
                </div>'''

            if item.get("summary"):
                cards += f'''
                <div style="color:#666;font-size:13px;line-height:1.7;margin-top:6px;">
                    💡 {item['summary']}
                </div>'''

            if item.get("link"):
                cards += f'''
                <div style="margin-top:8px;">
                    🔗 <a href="{item['link']}" target="_blank" style="color:#999;text-decoration:none;font-size:12px;">相关链接</a>
                </div>'''

            cards += '</div>'

        elif item.get("is_video"):
            link_html = f'<a href="{item["link"]}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if item.get("link") else item["title"]
            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #f59e0b;">
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">
                    🎬 {link_html}
                </div>
                <div style="margin-top:6px;">
                    <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{item['source']}</span>
                    <span style="color:#bbb;font-size:12px;margin-left:8px;">{item.get('time_short','')}</span>
                </div>
            </div>'''

        else:
            link_html = f'<a href="{item["link"]}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if item.get("link") else item["title"]
            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #eee;">
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{link_html}</div>
                <div style="margin-top:6px;">
                    <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{item['source']}</span>
                    <span style="color:#bbb;font-size:12px;margin-left:8px;">{item.get('time_short','')}</span>
                </div>
            </div>'''

    html = _email_wrapper("🌅 特斯拉晨报", now, weekday, c1, c2, cards, len(items))
    return html


def push_email_noon(items, brand_items):
    """Noon email: brand-organized cards."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    c1, c2 = "#1a73e8", "#1557b0"

    cards = ""
    brand_colors = {
        "蔚来": "#1e88e5", "理想": "#43a047", "小鹏": "#ff9800",
        "小米": "#ff6f00", "问界": "#e53935", "其他": "#9e9e9e",
    }

    for brand_info in NOON_BRANDS:
        brand_name = brand_info["name"]
        brand_list = [i for i in items if i.get("brand") == brand_name]
        if not brand_list:
            continue

        bc = brand_colors.get(brand_name, "#9e9e9e")
        cards += f'''
        <div style="border-left:4px solid {bc};padding:6px 0 6px 14px;margin:24px 0 14px;">
            <span style="color:{bc};font-size:16px;font-weight:700;">🚗 {brand_name}（{brand_info['en']}）</span>
        </div>'''

        for item in brand_list:
            cat = item.get("category", "")
            cat_badge = f'<span style="display:inline-block;background:#e3f2fd;color:#1565c0;padding:1px 8px;border-radius:3px;font-size:10px;margin-right:6px;">{cat}</span>' if cat else ""

            if item.get("is_weibo"):
                founder = item.get("source_name", "")
                link_html = f'<a href="{item["link"]}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if item.get("link") else item["title"]
                cards += f'''
                <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid {bc};">
                    <div style="font-size:12px;color:{bc};font-weight:600;margin-bottom:4px;">👤 {founder}（{brand_name}）</div>
                    <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{cat_badge}{link_html}</div>
                    <div style="color:#999;font-size:12px;margin-top:4px;">{item.get('time_short','')}</div>
                </div>'''
            else:
                link_html = f'<a href="{item["link"]}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if item.get("link") else item["title"]
                summary_html = f'<div style="color:#666;font-size:13px;line-height:1.75;margin-top:8px;">{item["summary"]}</div>' if item.get("summary") else ""
                cards += f'''
                <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #eee;">
                    <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{cat_badge}{link_html}</div>
                    <div style="margin-top:6px;">
                        <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{item['source']}</span>
                        <span style="color:#bbb;font-size:12px;margin-left:8px;">{item.get('time_short','')}</span>
                    </div>{summary_html}
                </div>'''

    html = _email_wrapper("⚡ 新能源午报", now, weekday, c1, c2, cards, len(items))
    return html


def push_email_evening(items):
    """Evening email: domain-tagged cards."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    c1, c2 = "#7c3aed", "#6d28d9"

    domain_colors = {
        "AI": "#6366f1", "机器人": "#8b5cf6", "生物": "#10b981",
        "航天": "#f59e0b", "芯片": "#ef4444",
    }

    cards = ""
    domain_order = [d["tag"] for d in EVENING_DOMAINS]
    domain_icons = {d["tag"]: d["icon"] for d in EVENING_DOMAINS}

    for domain in domain_order:
        domain_list = [i for i in items if i.get("domain") == domain]
        if not domain_list:
            continue

        dc = domain_colors.get(domain, "#6366f1")
        icon = domain_icons.get(domain, "🔬")
        cards += f'''
        <div style="border-left:4px solid {dc};padding:6px 0 6px 14px;margin:24px 0 14px;">
            <span style="color:{dc};font-size:16px;font-weight:700;">{icon} {domain}</span>
        </div>'''

        for item in domain_list:
            link_html = f'<a href="{item["link"]}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if item.get("link") else item["title"]
            summary = item.get("summary", "")
            summary_html = f'<div style="color:#555;font-size:13px;line-height:1.75;margin-top:8px;">{summary}</div>' if summary else ""

            tag_badge = f'<span style="display:inline-block;background:#f3e8ff;color:#7c3aed;padding:1px 8px;border-radius:3px;font-size:10px;margin-right:6px;">{domain}</span>'

            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #eee;">
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{tag_badge}{link_html}</div>
                <div style="margin-top:6px;">
                    <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{item['source']}</span>
                    <span style="color:#bbb;font-size:12px;margin-left:8px;">{item.get('time_short','')}</span>
                </div>{summary_html}
            </div>'''

    html = _email_wrapper("🔬 前沿科技晚报", now, weekday, c1, c2, cards, len(items))
    return html


def _email_wrapper(title, now, weekday, c1, c2, cards, total):
    """Common HTML email wrapper."""
    return f'''
    <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;">
        <div style="background:linear-gradient(135deg,{c1} 0%,{c2} 100%);padding:28px 32px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">{title}</h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,0.75);font-size:13px;">{now.year}年{now.month}月{now.day}日 {weekday}</p>
        </div>
        <div style="padding:20px 28px 28px;">
            {cards}
            <div style="text-align:center;color:#ccc;font-size:11px;margin-top:24px;padding-top:16px;border-top:1px solid #f0f0f0;">
                🤖 云端自动采集 · 共{total}条
            </div>
        </div>
    </div>'''


def push_email(items, cfg, brand_items=None):
    """Dispatch to the right email formatter and send."""
    print("[3/3] 正在发送邮件...")

    if REPORT_TYPE == "morning":
        html = push_email_morning(items)
    elif REPORT_TYPE == "noon":
        html = push_email_noon(items, brand_items or {})
    else:
        html = push_email_evening(items)

    now = datetime.now(BEIJING)

    if ICLOUD_USER and ICLOUD_PASS:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{cfg['emoji']} {cfg['title']}（{now.month}月{now.day}日）"
        msg["From"] = ICLOUD_USER
        msg["To"] = ICLOUD_USER
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            with smtplib.SMTP("smtp.mail.me.com", 587) as s:
                s.starttls()
                s.login(ICLOUD_USER, ICLOUD_PASS)
                s.sendmail(ICLOUD_USER, ICLOUD_USER, msg.as_string())
            print("  ✅ 邮件发送成功")
        except Exception as e:
            print(f"  ❌ 邮件发送失败: {e}")
    else:
        print("  ⚠ 跳过邮件发送（无iCloud凭证）")

    return html


# ============================================================
# Main
# ============================================================
def main():
    cfg = REPORTS[REPORT_TYPE]
    now = datetime.now(BEIJING)

    print(f"\n{'='*50}")
    print(f"  {cfg['emoji']} {cfg['title']} v4")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} (北京时间)")
    print(f"{'='*50}\n")

    brand_items = None

    if REPORT_TYPE == "morning":
        items = fetch_morning()
    elif REPORT_TYPE == "noon":
        items, brand_items = fetch_noon()
    else:
        items = fetch_evening()

    if not items:
        print("未采集到新闻，跳过推送。")
        return

    push_wechat(items, cfg, brand_items)
    push_email(items, cfg, brand_items)

    print(f"\n{'='*50}")
    print("  ✅ 全部完成！")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
