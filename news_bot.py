#!/usr/bin/env python3
"""
News Bot v4.1 — Refined Daily Briefing System

  Morning 08:00 : Tesla FSD / Autopilot / Robotaxi / Optimus (strict focus)
  Noon    12:00 : Chinese NEV by brand (NIO/Li Auto/XPeng/Xiaomi/AITO)
  Evening 17:30 : Global frontier tech with AI-style summaries

Cloud-only (GitHub Actions) · Precise timing · Global dedup
Dual push: WeChat (Server酱 Markdown) + iCloud Email (HTML)

v4.1 changes:
  - Morning: RSSHub Twitter primary, strict FSD filter, 200-char summary
  - Noon: more RSS sources, Weibo backup, per-brand coverage
  - Evening: intelligent summary extraction (150-200 chars)
  - Global: every item = summary(≤200字) + link + author + time
"""

import os, sys, smtplib, re, time, hashlib, textwrap, feedparser, requests
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
UA = "Mozilla/5.0 (compatible; NewsBot/4.1)"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORTS = {
    "morning":  {"title": "特斯拉FSD晨报", "emoji": "🌅", "hours": 12, "max": 15},
    "noon":     {"title": "新能源午报",    "emoji": "⚡", "hours": 8,  "max": 15},
    "evening":  {"title": "前沿科技晚报",  "emoji": "🔬", "hours": 10, "max": 15},
}

# ============================================================
# Morning: X/Twitter Account Sources (via RSSHub)
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

# Strict FSD / Autopilot / Tesla-tech keywords (morning only)
MORNING_STRICT_KW = [
    # FSD & Autopilot
    "fsd", "full self-driving", "full self driving", "autopilot",
    "self-driving", "self driving", "autonomous driving",
    "supervised", "unsupervised", "v12", "v13",
    # Robotaxi
    "robotaxi", "robot taxi", "cybercab",
    # Tesla AI / Vision
    "tesla ai", "neural net", "vision", "hw3", "hw4",
    "phantom braking", "auto steer", "smart summon", "summon",
    "navigate on autopilot", "noa", "lane change", "merge",
    "park assist", "auto park", "city streets",
    # Optimus / Robot
    "optimus", "tesla bot", "humanoid",
    # Software / OTA
    "software update", "ota update", "firmware",
    "release notes", "holiday update",
    # Tesla core tech
    "megapack", "supercharger", "4680", "battery",
]

# Morning supplemental RSS feeds (Tesla FSD focused)
MORNING_RSS_FEEDS = [
    {"name": "Electrek", "url": "https://electrek.co/feed/", "lang": "en",
     "keywords": ["fsd", "autopilot", "self-driving", "robotaxi", "optimus",
                  "software update", "tesla ai", "autonomous"]},
    {"name": "TeslaRati", "url": "https://www.teslarati.com/feed/", "lang": "en",
     "keywords": ["fsd", "autopilot", "self-driving", "robotaxi", "optimus",
                  "software update", "supervised"]},
    {"name": "Not a Tesla App", "url": "https://www.notateslaapp.com/rss", "lang": "en",
     "keywords": ["fsd", "autopilot", "software", "update", "self-driving",
                  "robotaxi", "autonomous", "release notes"]},
    {"name": "InsideEVs", "url": "https://insideevs.com/rss/", "lang": "en",
     "keywords": ["fsd", "autopilot", "self-driving", "tesla", "robotaxi"]},
    {"name": "Car and Driver", "url": "https://www.caranddriver.com/rss/all.xml/", "lang": "en",
     "keywords": ["tesla fsd", "autopilot", "self-driving"]},
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["FSD", "特斯拉自动驾驶", "Robotaxi", "Optimus", "特斯拉AI",
                  "特斯拉软件更新", "特斯拉智驾"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["FSD", "特斯拉自动驾驶", "Robotaxi", "Optimus"]},
]

# ============================================================
# Noon: Chinese NEV Brand Sources
# ============================================================
NOON_BRANDS = [
    {"name": "蔚来", "en": "NIO", "founder": "李斌",
     "keywords": ["蔚来", "NIO", "李斌", "ET5", "ET7", "ES6", "ES8", "EC6",
                  "NOP+", "蔚来自动驾驶", "换电", "蔚来智驾", "蔚来ET"]},
    {"name": "理想", "en": "Li Auto", "founder": "李想",
     "keywords": ["理想", "Li Auto", "李想", "L6", "L7", "L8", "L9", "MEGA",
                  "理想智驾", "AD Max", "AD Pro", "理想NOA", "端到端", "理想L"]},
    {"name": "小鹏", "en": "XPeng", "founder": "何小鹏",
     "keywords": ["小鹏", "XPeng", "何小鹏", "G6", "G9", "P7", "X9", "MONA",
                  "XNGP", "小鹏智驾", "小鹏自动驾驶", "天玑"]},
    {"name": "小米", "en": "Xiaomi", "founder": "雷军",
     "keywords": ["小米汽车", "小米SU7", "雷军", "小米智驾", "小米自动驾驶",
                  "SU7", "Xiaomi Auto", "澎湃智驾"]},
    {"name": "问界", "en": "AITO", "founder": "余承东",
     "keywords": ["问界", "AITO", "余承东", "M5", "M7", "M8", "M9",
                  "华为智驾", "鸿蒙智行", "ADS", "乾崑智驾"]},
]

# Weibo founder UIDs (via RSSHub)
WEIBO_FOUNDERS = [
    {"uid": "2171350430", "name": "李想",  "brand": "理想"},
    {"uid": "1252070184", "name": "何小鹏", "brand": "小鹏"},
    {"uid": "1704116900", "name": "雷军",  "brand": "小米"},
    {"uid": "1650987740", "name": "李斌",  "brand": "蔚来"},
    {"uid": "1708388644", "name": "余承东", "brand": "问界"},
]

# Noon RSS feeds (expanded for more coverage)
NOON_RSS_FEEDS = [
    {"name": "36氪汽车", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米汽车", "问界", "NIO", "XPeng",
                  "Li Auto", "Xiaomi Auto", "AITO", "华为智驾", "智驾", "NOA",
                  "自动驾驶", "新能源车", "电动车"]},
    {"name": "IT之家汽车", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米汽车", "问界", "华为智驾",
                  "智驾", "NOA", "自动驾驶", "新能源"]},
    {"name": "CarNewsChina", "url": "https://carnewschina.com/feed/", "lang": "en",
     "keywords": ["nio", "li auto", "xpeng", "xiaomi", "aito", "huawei",
                  "autonomous", "ads", "ngp", "nop"]},
    {"name": "汽车之家", "url": "https://www.autohome.com.cn/rss/", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米汽车", "问界", "智驾", "自动驾驶"]},
    {"name": "懂车帝", "url": "https://www.dongchedi.com/rss", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米", "问界", "智驾"]},
    {"name": "电动邦", "url": "https://www.ddc.net.cn/rss", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米", "问界", "智驾", "新能源"]},
    {"name": "新出行", "url": "https://www.xinchuxing.com/rss", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米", "问界", "智驾", "NOA"]},
]

# ============================================================
# Evening: Frontier Tech Sources
# ============================================================
EVENING_DOMAINS = [
    {"tag": "AI",     "icon": "🧠", "keywords": ["ai", "artificial intelligence", "gpt",
     "llm", "大模型", "人工智能", "openai", "deepseek", "gemini", "claude",
     "机器学习", "深度学习", "transformer", "diffusion", "多模态"]},
    {"tag": "机器人", "icon": "🤖", "keywords": ["robot", "humanoid", "机器人", "人形机器人",
     "boston dynamics", "figure", "unitree", "宇树", "figure ai", "1x"]},
    {"tag": "生物",   "icon": "🧬", "keywords": ["gene", "crispr", "dna", "mrna", "vaccine",
     "基因", "crispr", "生物", "蛋白质", "细胞", "免疫", "脑机接口"]},
    {"tag": "航天",   "icon": "🚀", "keywords": ["spacex", "starship", "nasa", "rocket",
     "航天", "火箭", "卫星", "月球", "火星", "太空", "空间站"]},
    {"tag": "芯片",   "icon": "💎", "keywords": ["chip", "semiconductor", "gpu", "nvidia",
     "芯片", "半导体", "光刻", "先进制程", "3nm", "2nm", "tsmc", "台积电"]},
]

EVENING_RSS_FEEDS = [
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "lang": "en",
     "keywords": []},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en",
     "keywords": []},
    {"name": "Science Daily", "url": "https://www.sciencedaily.com/rss/all.xml", "lang": "en",
     "keywords": []},
    {"name": "36氪科技", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["AI", "人工智能", "大模型", "芯片", "机器人", "航天", "生物技术"]},
    {"name": "IT之家科技", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["AI", "芯片", "大模型", "机器人", "航天", "生物"]},
    {"name": "Wired Science", "url": "https://www.wired.com/feed/tag/science/latest/rss", "lang": "en",
     "keywords": []},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "lang": "en",
     "keywords": []},
    {"name": "Nature News", "url": "https://www.nature.com/nature.rss", "lang": "en",
     "keywords": []},
]

# ============================================================
# HTTP Session with Retry
# ============================================================
_session = None

def _get_session():
    global _session
    if _session is None:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        _session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503])
        adapter = HTTPAdapter(max_retries=retry)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
        _session.headers.update({"User-Agent": UA})
    return _session


# ============================================================
# Translation (English → Chinese)
# ============================================================
_translate_cache = {}

def translate(text, lang="en"):
    """Translate English text to Chinese. Caches results."""
    if lang == "zh" or not text:
        return text
    if text in _translate_cache:
        return _translate_cache[text]

    # Try Google Translate (unofficial)
    try:
        s = _get_session()
        r = s.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text},
            timeout=6,
        )
        if r.status_code == 200:
            result = "".join(seg[0] for seg in r.json()[0] if seg[0])
            _translate_cache[text] = result
            return result
    except Exception:
        pass

    # Try MyMemory backup
    try:
        s = _get_session()
        r = s.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": "en|zh-CN"},
            timeout=6,
        )
        if r.status_code == 200:
            result = r.json()["responseData"]["translatedText"]
            _translate_cache[text] = result
            return result
    except Exception:
        pass

    return text  # Return original if both fail


# ============================================================
# Intelligent Summary Extraction (replaces AI)
# ============================================================
def smart_summary(text, max_chars=180):
    """
    Extract key information from article text and compress to max_chars.
    Uses sentence scoring: first sentences, position, keyword density.
    """
    if not text:
        return ""

    # Strip HTML
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) <= max_chars:
        return text

    # Split into sentences
    sentences = re.split(r'(?<=[.。！？!?\n])\s*', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 8]

    if not sentences:
        return text[:max_chars] + "..."

    # Score sentences: position + length preference
    scored = []
    for i, s in enumerate(sentences[:8]):  # Only consider first 8 sentences
        score = 0
        # First sentence gets highest score (usually the lede)
        if i == 0:
            score += 10
        elif i == 1:
            score += 5
        elif i == 2:
            score += 3
        # Prefer medium-length sentences (not too short, not too long)
        if 20 <= len(s) <= 120:
            score += 3
        # Bonus for containing key tech terms
        tech_terms = ["announced", "released", "breakthrough", "first", "new",
                      "首次", "突破", "发布", "推出", "研发", "成功", "宣布",
                      "achieved", "demonstrated", "developed", "launched"]
        score += sum(1 for t in tech_terms if t.lower() in s.lower())
        scored.append((score, s))

    # Sort by score descending, take top sentences in original order
    scored.sort(key=lambda x: (-x[0], sentences.index(x[1])))
    top = sorted(scored[:3], key=lambda x: sentences.index(x[1]))

    result = " ".join(s for _, s in top)

    # Trim to max_chars
    if len(result) > max_chars:
        result = result[:max_chars - 3] + "..."

    return result


# ============================================================
# Feed Fetching
# ============================================================
def fetch_feed(feed_cfg, hours):
    """Fetch and parse an RSS/Atom feed, return list of items."""
    s = _get_session()
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    try:
        r = s.get(feed_cfg["url"], timeout=8, allow_redirects=True)
        if r.status_code != 200:
            return items
        d = feedparser.parse(r.text)
    except Exception:
        return items

    kw = feed_cfg.get("keywords", [])

    for entry in d.entries:
        try:
            # Parse publish time
            published = None
            for time_field in ["published_parsed", "updated_parsed"]:
                t = entry.get(time_field)
                if t:
                    try:
                        published = datetime(*t[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass
                    break

            if published and published < cutoff:
                continue

            title = entry.get("title", "").strip()
            if not title:
                continue

            # Unescape HTML entities
            title = unescape(title)

            # Get full content for summary extraction
            content = ""
            for field in ["content", "summary_detail", "summary"]:
                c = entry.get(field)
                if c:
                    if isinstance(c, list):
                        content = c[0].get("value", "")
                    elif isinstance(c, dict):
                        content = c.get("value", "")
                    else:
                        content = str(c)
                    if content:
                        break

            # Keyword filter
            if kw:
                text_to_check = (title + " " + content).lower()
                if not any(k.lower() in text_to_check for k in kw):
                    continue

            # Get link
            link = entry.get("link", "")

            # Get author
            author = ""
            if entry.get("author"):
                author = entry["author"]
            elif entry.get("authors") and entry["authors"]:
                author = entry["authors"][0].get("name", "")

            # Build time strings
            time_short = ""
            if published:
                bj = published.astimezone(BEIJING)
                time_short = f"{bj.month}/{bj.day} {bj.hour:02d}:{bj.minute:02d}"

            # Translate if English
            lang = feed_cfg.get("lang", "en")
            if lang == "en":
                title_zh = translate(title, lang)
                # Smart summary from content
                if content:
                    summary_raw = smart_summary(content, 200)
                    summary_zh = translate(summary_raw, lang) if summary_raw else ""
                else:
                    summary_zh = ""
            else:
                title_zh = title
                summary_zh = smart_summary(content, 180) if content else ""

            # Truncate summary to 200 chars
            if len(summary_zh) > 200:
                summary_zh = summary_zh[:197] + "..."

            items.append({
                "title": title_zh,
                "title_en": title if lang == "en" else "",
                "summary": summary_zh,
                "link": link,
                "source": feed_cfg["name"],
                "author": author,
                "time_short": time_short,
            })

        except Exception:
            continue

    return items


def fetch_twitter_account(account, hours):
    """Fetch tweets via RSSHub (primary) then Nitter (fallback)."""
    handle = account["handle"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []

    # 1) Try RSSHub Twitter
    try:
        rsshub_url = f"https://rsshub.app/twitter/user/{handle}"
        s = _get_session()
        r = s.get(rsshub_url, timeout=8, allow_redirects=True)
        if r.status_code == 200:
            d = feedparser.parse(r.text)
            for entry in d.entries:
                try:
                    title = entry.get("title", "").strip()
                    if not title:
                        continue

                    published = None
                    for tf in ["published_parsed", "updated_parsed"]:
                        t = entry.get(tf)
                        if t:
                            try:
                                published = datetime(*t[:6], tzinfo=timezone.utc)
                            except Exception:
                                pass
                            break

                    if published and published < cutoff:
                        continue

                    content = ""
                    for field in ["content", "summary_detail", "summary"]:
                        c = entry.get(field)
                        if c:
                            if isinstance(c, list):
                                content = c[0].get("value", "")
                            elif isinstance(c, dict):
                                content = c.get("value", "")
                            else:
                                content = str(c)
                            if content:
                                break

                    full_text = title + " " + content

                    # Strict FSD filter
                    if not any(k.lower() in full_text.lower() for k in MORNING_STRICT_KW):
                        continue

                    link = entry.get("link", "")
                    time_short = ""
                    if published:
                        bj = published.astimezone(BEIJING)
                        time_short = f"{bj.month}/{bj.day} {bj.hour:02d}:{bj.minute:02d}"

                    # Translate tweet
                    title_zh = translate(title, "en")
                    summary_raw = smart_summary(content, 180) if content else ""
                    summary_zh = translate(summary_raw, "en") if summary_raw else ""

                    if len(summary_zh) > 200:
                        summary_zh = summary_zh[:197] + "..."

                    items.append({
                        "title": title_zh,
                        "title_en": title,
                        "summary": summary_zh,
                        "link": link,
                        "source": f"@{handle}",
                        "author": account["zh"],
                        "author_handle": handle,
                        "author_name": account["zh"],
                        "is_tweet": True,
                        "time_short": time_short,
                    })
                except Exception:
                    continue
    except Exception:
        pass

    # 2) Try Nitter RSS (fallback)
    if not items:
        nitter_instances = [
            "nitter.poast.org", "nitter.privacydev.net",
            "nitter.woodland.cafe", "nitter.d420.de",
        ]
        for instance in nitter_instances:
            try:
                url = f"https://{instance}/{handle}/rss"
                s = _get_session()
                r = s.get(url, timeout=5, allow_redirects=True)
                if r.status_code != 200 or len(r.text) < 100:
                    continue
                d = feedparser.parse(r.text)
                for entry in d.entries:
                    try:
                        title = entry.get("title", "").strip()
                        if not title:
                            continue
                        published = None
                        for tf in ["published_parsed", "updated_parsed"]:
                            t = entry.get(tf)
                            if t:
                                try:
                                    published = datetime(*t[:6], tzinfo=timezone.utc)
                                except Exception:
                                    pass
                                break
                        if published and published < cutoff:
                            continue
                        # Strict FSD filter
                        if not any(k.lower() in title.lower() for k in MORNING_STRICT_KW):
                            continue
                        link = entry.get("link", "")
                        time_short = ""
                        if published:
                            bj = published.astimezone(BEIJING)
                            time_short = f"{bj.month}/{bj.day} {bj.hour:02d}:{bj.minute:02d}"
                        title_zh = translate(title, "en")
                        items.append({
                            "title": title_zh,
                            "title_en": title,
                            "summary": "",
                            "link": link,
                            "source": f"@{handle}",
                            "author": account["zh"],
                            "author_handle": handle,
                            "author_name": account["zh"],
                            "is_tweet": True,
                            "time_short": time_short,
                        })
                    except Exception:
                        continue
                if items:
                    break  # This instance works, stop trying
            except Exception:
                continue

    return items


def fetch_weibo_user(founder, hours):
    """Fetch Weibo posts via RSSHub."""
    uid = founder["uid"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []

    try:
        rsshub_url = f"https://rsshub.app/weibo/user/{uid}"
        s = _get_session()
        r = s.get(rsshub_url, timeout=8, allow_redirects=True)
        if r.status_code != 200:
            return items
        d = feedparser.parse(r.text)
    except Exception:
        return items

    for entry in d.entries:
        try:
            title = entry.get("title", "").strip()
            if not title:
                continue

            published = None
            for tf in ["published_parsed", "updated_parsed"]:
                t = entry.get(tf)
                if t:
                    try:
                        published = datetime(*t[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass
                    break

            if published and published < cutoff:
                continue

            content = ""
            for field in ["content", "summary_detail", "summary"]:
                c = entry.get(field)
                if c:
                    if isinstance(c, list):
                        content = c[0].get("value", "")
                    elif isinstance(c, dict):
                        content = c.get("value", "")
                    else:
                        content = str(c)
                    if content:
                        break

            link = entry.get("link", "")
            time_short = ""
            if published:
                bj = published.astimezone(BEIJING)
                time_short = f"{bj.month}/{bj.day} {bj.hour:02d}:{bj.minute:02d}"

            summary_zh = smart_summary(content, 180) if content else ""
            if len(summary_zh) > 200:
                summary_zh = summary_zh[:197] + "..."

            items.append({
                "title": title,
                "summary": summary_zh,
                "link": link,
                "source": f"微博·{founder['name']}",
                "source_name": founder["name"],
                "author": founder["name"],
                "brand": founder["brand"],
                "is_weibo": True,
                "category": "创始人动态",
                "time_short": time_short,
            })
        except Exception:
            continue

    return items


# ============================================================
# Global Dedup
# ============================================================
def fingerprint(text):
    """Normalize and hash for dedup."""
    t = re.sub(r'[\s\-_|,，.。:：!！?？\(\)【】《》]+', '', text.lower())
    return hashlib.md5(t.encode()).hexdigest()[:12]


def similarity(a, b):
    """Character-set overlap ratio."""
    if not a or not b:
        return 0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0


def dedup(items):
    """Remove duplicates by fingerprint + similarity."""
    seen_fps = []
    seen_texts = []
    unique = []

    for item in items:
        title = item.get("title", "")
        fp = fingerprint(title)

        if fp in seen_fps:
            continue

        title_clean = re.sub(r'[\s\-_|,，.。:：!！?？]+', '', title.lower())
        is_dup = False
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
    """Morning: X/Twitter bloggers (FSD strict) + supplemental RSS."""
    cfg = REPORTS["morning"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")

    all_items = []

    # 1) X/Twitter accounts (primary - strict FSD filter)
    print("  📡 抓取 X/Twitter 博主动态（FSD严格过滤）...")
    for account in TWITTER_ACCOUNTS:
        items = fetch_twitter_account(account, cfg["hours"])
        count = len(items)
        if count:
            print(f"  @{account['handle']}: {count} 条")
        all_items.extend(items)
        time.sleep(0.3)

    # 2) Supplemental RSS feeds (also FSD-focused)
    print("  📡 抓取特斯拉FSD专业源...")
    for feed in MORNING_RSS_FEEDS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
            for item in items:
                item["is_tweet"] = False
            all_items.extend(items)

    all_items = dedup(all_items)

    # Prioritize: tweets first, then RSS
    tweets = [i for i in all_items if i.get("is_tweet")]
    others = [i for i in all_items if not i.get("is_tweet")]

    selected = tweets[:12]
    remaining = cfg["max"] - len(selected)
    if remaining > 0:
        selected.extend(others[:remaining])

    selected = selected[:cfg["max"]]
    print(f"  共 {len(selected)} 条（推文 {len(tweets)} / 资讯 {len(others)}）")
    return selected


# ============================================================
# Noon: Fetch + Organize
# ============================================================
def fetch_noon():
    """Noon: Chinese NEV by brand + founder Weibo + RSS."""
    cfg = REPORTS["noon"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")

    all_items = []

    # 1) Weibo founder accounts
    print("  📡 抓取创始人微博...")
    for founder in WEIBO_FOUNDERS:
        items = fetch_weibo_user(founder, cfg["hours"])
        if items:
            print(f"  {founder['name']}: {len(items)} 条")
        all_items.extend(items)
        time.sleep(0.3)

    # 2) RSS feeds for NEV news
    print("  📡 抓取新能源资讯...")
    for feed in NOON_RSS_FEEDS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
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

    brand_items["其他"] = []

    for item in all_items:
        b = item.get("brand", "")
        if b in brand_items:
            brand_items[b].append(item)
        else:
            item["brand"] = "其他"
            brand_items["其他"].append(item)

    # Select top items per brand, total 10-15
    selected = []
    per_brand = max(3, cfg["max"] // len(NOON_BRANDS))
    for brand_name in [b["name"] for b in NOON_BRANDS] + ["其他"]:
        items = brand_items.get(brand_name, [])
        selected.extend(items[:per_brand])

    selected = selected[:cfg["max"]]

    total = len(selected)
    brand_counts = {b: len([i for i in selected if i.get("brand") == b]) for b in [b["name"] for b in NOON_BRANDS]}
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
    """Evening: Frontier tech with domain tags + AI-style summaries."""
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
    """Morning WeChat: FSD-focused, blogger-centric, ≤200字 per item."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    lines = [
        f"## 🌅 特斯拉FSD晨报",
        f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条",
        "",
    ]

    for item in items:
        author = item.get("author", item.get("source", ""))
        source = item.get("source", "")
        time_str = item.get("time_short", "")
        summary = item.get("summary", "")

        if item.get("is_tweet"):
            handle = item.get("author_handle", "")
            lines.append(f"## **@{handle}** · {time_str}")
        else:
            lines.append(f"## **{item['title']}**")

        # Summary (≤200字)
        if summary:
            lines.append(f"📝 {summary}")
        elif not item.get("is_tweet"):
            # Use title as fallback if no summary
            pass

        # Link + Source + Author
        link = item.get("link", "")
        if link:
            lines.append(f"🔗 [原文链接]({link})")
        lines.append(f"_来源：{source}  ·  {author}  ·  {time_str}_")
        lines.append("")

    lines.append("---")
    lines.append("_🤖 云端自动采集 · 特斯拉FSD/智驾动态_")
    return "\n".join(lines)


def push_wechat_noon(items, brand_items):
    """Noon WeChat: brand-organized, ≤200字 per item."""
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
            author = item.get("author", item.get("source", ""))
            source = item.get("source", "")
            time_str = item.get("time_short", "")
            summary = item.get("summary", "")
            link = item.get("link", "")

            if item.get("is_weibo"):
                lines.append(f"👤 **{author}** · {time_str}")
                lines.append(f"📝 {summary if summary else item['title']}")
            else:
                lines.append(f"**{item['title']}**")
                if summary:
                    lines.append(f"📝 {summary}")

            if link:
                lines.append(f"🔗 [原文链接]({link})")
            lines.append(f"_来源：{source}  ·  {author}  ·  {time_str}_")
            lines.append("")

    lines.append("---")
    lines.append("_🤖 云端自动采集 · 新能源智驾动态_")
    return "\n".join(lines)


def push_wechat_evening(items):
    """Evening WeChat: domain-tagged + 150-200字核心摘要."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    lines = [
        f"## 🔬 前沿科技晚报",
        f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条",
        "",
    ]

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
            author = item.get("author", item.get("source", ""))
            source = item.get("source", "")
            time_str = item.get("time_short", "")
            summary = item.get("summary", "")
            link = item.get("link", "")

            lines.append(f"【{domain}】**{item['title']}**")
            if summary:
                lines.append(f"📝 {summary}")
            if link:
                lines.append(f"🔗 [原文链接]({link})")
            lines.append(f"_来源：{source}  ·  {author}  ·  {time_str}_")
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
    """Morning email: FSD-focused cards with summary."""
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    c1, c2 = "#e82127", "#c41e24"

    cards = ""
    for item in items:
        author = item.get("author", item.get("source", ""))
        source = item.get("source", "")
        time_str = item.get("time_short", "")
        summary = item.get("summary", "")
        link = item.get("link", "")

        if item.get("is_tweet"):
            handle = item.get("author_handle", "")
            link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
            summary_html = f'<div style="color:#555;font-size:13px;line-height:1.75;margin-top:6px;">{summary}</div>' if summary else ""
            cards += f'''
            <div style="padding:16px;background:#fafafa;border-radius:10px;margin-bottom:12px;border-left:4px solid {c1};">
                <div style="font-weight:700;color:{c1};font-size:14px;margin-bottom:6px;">
                    @{handle} <span style="color:#999;font-weight:400;font-size:12px;margin-left:8px;">{time_str}</span>
                </div>
                <div style="color:#1a1a1a;font-size:15px;line-height:1.7;">{link_html}</div>
                {summary_html}
                <div style="margin-top:8px;">
                    <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{source}</span>
                    <span style="color:#bbb;font-size:12px;margin-left:8px;">{author} · {time_str}</span>
                </div>
            </div>'''
        else:
            link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
            summary_html = f'<div style="color:#555;font-size:13px;line-height:1.75;margin-top:6px;">{summary}</div>' if summary else ""
            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #eee;">
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{link_html}</div>
                {summary_html}
                <div style="margin-top:6px;">
                    <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{source}</span>
                    <span style="color:#bbb;font-size:12px;margin-left:8px;">{author} · {time_str}</span>
                </div>
            </div>'''

    html = _email_wrapper("🌅 特斯拉FSD晨报", now, weekday, c1, c2, cards, len(items))
    return html


def push_email_noon(items, brand_items):
    """Noon email: brand-organized cards with summary."""
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
            author = item.get("author", item.get("source", ""))
            source = item.get("source", "")
            time_str = item.get("time_short", "")
            summary = item.get("summary", "")
            link = item.get("link", "")

            if item.get("is_weibo"):
                link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
                summary_html = f'<div style="color:#555;font-size:13px;line-height:1.75;margin-top:6px;">{summary}</div>' if summary else ""
                cards += f'''
                <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid {bc};">
                    <div style="font-size:12px;color:{bc};font-weight:600;margin-bottom:4px;">👤 {author}</div>
                    <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{link_html}</div>
                    {summary_html}
                    <div style="margin-top:6px;">
                        <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{source}</span>
                        <span style="color:#bbb;font-size:12px;margin-left:8px;">{time_str}</span>
                    </div>
                </div>'''
            else:
                link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
                summary_html = f'<div style="color:#555;font-size:13px;line-height:1.75;margin-top:6px;">{summary}</div>' if summary else ""
                cards += f'''
                <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #eee;">
                    <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{link_html}</div>
                    {summary_html}
                    <div style="margin-top:6px;">
                        <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{source}</span>
                        <span style="color:#bbb;font-size:12px;margin-left:8px;">{author} · {time_str}</span>
                    </div>
                </div>'''

    html = _email_wrapper("⚡ 新能源午报", now, weekday, c1, c2, cards, len(items))
    return html


def push_email_evening(items):
    """Evening email: domain-tagged cards with 150-200字 core summary."""
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
            link = item.get("link", "")
            summary = item.get("summary", "")
            author = item.get("author", item.get("source", ""))
            source = item.get("source", "")
            time_str = item.get("time_short", "")

            link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
            summary_html = f'<div style="color:#555;font-size:13px;line-height:1.75;margin-top:8px;">{summary}</div>' if summary else ""
            tag_badge = f'<span style="display:inline-block;background:#f3e8ff;color:#7c3aed;padding:1px 8px;border-radius:3px;font-size:10px;margin-right:6px;">{domain}</span>'

            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #eee;">
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{tag_badge}{link_html}</div>
                {summary_html}
                <div style="margin-top:6px;">
                    <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;">{source}</span>
                    <span style="color:#bbb;font-size:12px;margin-left:8px;">{author} · {time_str}</span>
                </div>
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
    print(f"  {cfg['emoji']} {cfg['title']} v4.1")
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
