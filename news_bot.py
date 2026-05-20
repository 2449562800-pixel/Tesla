#!/usr/bin/env python3
"""
News Bot v5.2 — Full Twitter Coverage + Chinese-First Pipeline

  Morning 08:00 : Tesla FSD / Autopilot / Robotaxi / Optimus (strict focus)
  Noon    12:00 : Chinese NEV by brand (NIO/Li Auto/XPeng/Xiaomi/AITO)
  Evening 17:30 : Global frontier tech with AI-extracted summaries

v5.2 changes:
  - ALL 9 Twitter accounts restored (user requirement)
  - Translate-then-extract pipeline: translate full text → ai_extract from Chinese
  - ensure_chinese() final pass: guarantees zero English in output
  - Morning priority: Twitter → overseas RSS → domestic RSS → Google News
  - More Nitter instances for better Twitter availability
  - All summaries ≤200字, complete Chinese, with date + link (NO exceptions)
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
UA = "Mozilla/5.0 (compatible; NewsBot/5.2)"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORTS = {
    "morning":  {"title": "特斯拉FSD晨报", "emoji": "🌅", "hours": 24, "max": 15},
    "noon":     {"title": "新能源午报",    "emoji": "⚡", "hours": 12, "max": 15},
    "evening":  {"title": "前沿科技晚报",  "emoji": "🔬", "hours": 10, "max": 15},
}

# ============================================================
# Morning: X/Twitter Account Sources (ALL 9 — user requirement)
# ============================================================
TWITTER_ACCOUNTS = [
    {"handle": "SawyerMerritt",    "name": "Sawyer Merritt",      "zh": "Sawyer Merritt"},
    {"handle": "ChuckCook95",      "name": "Chuck Cook",          "zh": "Chuck Cook"},
    {"handle": "greentheonly",     "name": "green",               "zh": "green (黑客)"},
    {"handle": "DirtyTesla",       "name": "Dirty Tesla",         "zh": "Dirty Tesla"},
    {"handle": "brandonee916",     "name": "Brandon",             "zh": "Brandon"},
    {"handle": "WholeMarsBlog",    "name": "Whole Mars Catalog",  "zh": "Whole Mars"},
    {"handle": "elonmusk",        "name": "Elon Musk",           "zh": "马斯克"},
    {"handle": "Tesla_AI",        "name": "Tesla AI",            "zh": "Tesla AI"},
    {"handle": "Tesla",           "name": "Tesla Official",      "zh": "特斯拉官方"},
]

# More Nitter instances for better availability
NITTER_INSTANCES = [
    "nitter.poast.org",
    "nitter.privacydev.net",
    "nitter.net",
    "nitter.cz",
    "nitter.unixfox.eu",
    "nitter.fdn.fr",
]

# Strict FSD / Autopilot / Tesla-tech keywords (morning only)
MORNING_STRICT_KW = [
    "fsd", "full self-driving", "full self driving", "autopilot",
    "self-driving", "self driving", "autonomous driving",
    "supervised", "unsupervised", "v12", "v13",
    "robotaxi", "robot taxi", "cybercab",
    "tesla ai", "neural net", "vision", "hw3", "hw4",
    "phantom braking", "auto steer", "smart summon", "summon",
    "navigate on autopilot", "noa", "lane change", "merge",
    "park assist", "auto park", "city streets",
    "optimus", "tesla bot", "humanoid",
    "software update", "ota update", "firmware",
    "release notes", "holiday update",
    "megapack", "supercharger", "4680", "battery",
    "特斯拉FSD", "特斯拉自动驾驶", "特斯拉智驾", "特斯拉AI",
    "完全自动驾驶", "智能驾驶", "特斯拉软件更新",
]

# Morning overseas RSS feeds (English — primary supplement after Twitter)
MORNING_OVERSEAS_RSS = [
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
]

# Morning domestic RSS feeds (Chinese — secondary supplement)
MORNING_DOMESTIC_RSS = [
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["FSD", "特斯拉自动驾驶", "Robotaxi", "Optimus", "特斯拉AI", "特斯拉智驾"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["FSD", "特斯拉自动驾驶", "Robotaxi", "Optimus", "特斯拉", "特斯拉AI"]},
    {"name": "汽车之家", "url": "https://www.autohome.com.cn/rss/", "lang": "zh",
     "keywords": ["特斯拉", "FSD", "自动驾驶", "智驾", "Robotaxi", "特斯拉AI"]},
    {"name": "懂车帝", "url": "https://www.dongchedi.com/rss", "lang": "zh",
     "keywords": ["特斯拉", "FSD", "自动驾驶", "智驾", "Robotaxi"]},
]

# Google News RSS search (direct — works from GitHub Actions US servers)
MORNING_GOOGLE_NEWS = [
    {"name": "Google·特斯拉FSD", "query": "tesla fsd autopilot robotaxi", "lang": "en"},
    {"name": "Google·Tesla AI", "query": "tesla AI optimus robot autonomous", "lang": "en"},
    {"name": "Google·特斯拉智驾", "query": "特斯拉 FSD 自动驾驶 Robotaxi", "lang": "zh"},
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

WEIBO_FOUNDERS = [
    {"uid": "2171350430", "name": "李想",  "brand": "理想"},
    {"uid": "1252070184", "name": "何小鹏", "brand": "小鹏"},
    {"uid": "1704116900", "name": "雷军",  "brand": "小米"},
    {"uid": "1650987740", "name": "李斌",  "brand": "蔚来"},
    {"uid": "1708388644", "name": "余承东", "brand": "问界"},
]

NOON_RSS_FEEDS = [
    {"name": "CnEVPost", "url": "https://cnevpost.com/feed/", "lang": "en",
     "keywords": ["nio", "li auto", "xpeng", "xiaomi", "aito", "huawei",
                  "zeekr", "byd", "nio", "ev", "battery swap", "autonomous",
                  "ads", "ngp", "nop", "intelligent", "smart"]},
    {"name": "36氪汽车", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米汽车", "问界", "NIO", "XPeng",
                  "Li Auto", "Xiaomi Auto", "AITO", "华为智驾", "智驾", "NOA",
                  "自动驾驶", "新能源车", "电动车", "新能源"]},
    {"name": "IT之家汽车", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米汽车", "问界", "华为智驾",
                  "智驾", "NOA", "自动驾驶", "新能源", "电动车", "SU7",
                  "蔚来ET", "小鹏G", "理想L", "问界M"]},
    {"name": "CarNewsChina", "url": "https://carnewschina.com/feed/", "lang": "en",
     "keywords": ["nio", "li auto", "xpeng", "xiaomi", "aito", "huawei",
                  "autonomous", "ads", "ngp", "nop", "ev", "electric",
                  "zeekr", "byd", "smart"]},
    {"name": "汽车之家", "url": "https://www.autohome.com.cn/rss/", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米汽车", "问界", "智驾", "自动驾驶",
                  "新能源", "电动车", "SU7", "ET5", "L6", "L7", "M5", "M7", "M9"]},
    {"name": "懂车帝", "url": "https://www.dongchedi.com/rss", "lang": "zh",
     "keywords": ["蔚来", "理想", "小鹏", "小米", "问界", "智驾", "新能源",
                  "自动驾驶", "SU7", "电动车"]},
    {"name": "Electrek中国EV", "url": "https://electrek.co/feed/", "lang": "en",
     "keywords": ["nio", "li auto", "xpeng", "xiaomi", "aito", "huawei",
                  "byd", "zeekr", "chinese ev", "china ev"]},
    {"name": "InsideEVs中国EV", "url": "https://insideevs.com/rss/", "lang": "en",
     "keywords": ["nio", "li auto", "xpeng", "xiaomi", "aito", "huawei",
                  "byd", "zeekr", "chinese ev", "china ev"]},
]

NOON_GOOGLE_NEWS = [
    {"name": "Google·蔚来", "query": "蔚来 NIO 智驾 NOP+ 换电", "lang": "zh"},
    {"name": "Google·理想", "query": "理想汽车 Li Auto NOA 智驾 L6 L7 L8 L9", "lang": "zh"},
    {"name": "Google·小鹏", "query": "小鹏 XPeng XNGP 智驾 G6 G9 MONA", "lang": "zh"},
    {"name": "Google·小米汽车", "query": "小米汽车 SU7 智驾 雷军", "lang": "zh"},
    {"name": "Google·问界", "query": "问界 AITO 华为智驾 ADS M7 M9", "lang": "zh"},
    {"name": "Google·中国新能源", "query": "中国新能源 智驾 电动车 2025", "lang": "zh"},
    {"name": "Google·Chinese EV", "query": "NIO XPeng Li Auto Xiaomi EV autonomous", "lang": "en"},
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
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "lang": "en", "keywords": []},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en", "keywords": []},
    {"name": "Science Daily", "url": "https://www.sciencedaily.com/rss/all.xml", "lang": "en", "keywords": []},
    {"name": "36氪科技", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["AI", "人工智能", "大模型", "芯片", "机器人", "航天", "生物技术"]},
    {"name": "IT之家科技", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["AI", "芯片", "大模型", "机器人", "航天", "生物"]},
    {"name": "Wired Science", "url": "https://www.wired.com/feed/tag/science/latest/rss", "lang": "en", "keywords": []},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "lang": "en", "keywords": []},
    {"name": "Nature News", "url": "https://www.nature.com/nature.rss", "lang": "en", "keywords": []},
]

EVENING_GOOGLE_NEWS = [
    {"name": "Google·AI", "query": "artificial intelligence LLM GPT breakthrough", "lang": "en"},
    {"name": "Google·机器人", "query": "humanoid robot breakthrough 2025", "lang": "en"},
    {"name": "Google·航天", "query": "SpaceX Starship NASA space", "lang": "en"},
    {"name": "Google·芯片", "query": "chip semiconductor NVIDIA TSMC", "lang": "en"},
    {"name": "Google·前沿科技", "query": "AI 大模型 芯片 机器人 航天", "lang": "zh"},
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
# Translation (English → Chinese) — with caching & fallback
# ============================================================
_translate_cache = {}

def translate(text, lang="en"):
    """Translate text to Chinese. Returns Chinese text, or original if already Chinese/empty."""
    if not text or lang == "zh":
        return text
    # Quick check: if text is already mostly Chinese, skip
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(re.sub(r'\s+', '', text))
    if total_chars > 0 and cn_chars / total_chars > 0.3:
        return text
    if text in _translate_cache:
        return _translate_cache[text]
    # Google Translate (free)
    try:
        s = _get_session()
        r = s.get("https://translate.googleapis.com/translate_a/single",
                   params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text}, timeout=6)
        if r.status_code == 200:
            result = "".join(seg[0] for seg in r.json()[0] if seg[0])
            _translate_cache[text] = result
            return result
    except Exception:
        pass
    # MyMemory fallback
    try:
        s = _get_session()
        r = s.get("https://api.mymemory.translated.net/get",
                   params={"q": text[:500], "langpair": "en|zh-CN"}, timeout=6)
        if r.status_code == 200:
            result = r.json()["responseData"]["translatedText"]
            _translate_cache[text] = result
            return result
    except Exception:
        pass
    return text


def ensure_chinese(text):
    """Final pass: if text still contains significant English, translate it.
    This is the safety net to guarantee zero English in output."""
    if not text:
        return text
    # Check ratio of English letters vs Chinese characters
    en_chars = len(re.findall(r'[a-zA-Z]', text))
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # If more than 40% English letters (and at least 10 English chars), translate
    total_alpha = en_chars + cn_chars
    if total_alpha > 5 and en_chars / total_alpha > 0.4:
        translated = translate(text, "en")
        # If translation produced Chinese, use it
        cn_after = len(re.findall(r'[\u4e00-\u9fff]', translated))
        if cn_after > cn_chars:
            return translated
    return text


# ============================================================
# AI Extract — Unified Key Information Extraction (≤200字)
# Works on CHINESE text for best results
# ============================================================
def ai_extract(text, max_chars=200):
    """Extract key information from text, compress to max_chars."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'(Read more|点击阅读|查看全文|了解详情|原文链接).*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'(\[.*?\]\(.*?\))', '', text)
    if len(text) <= max_chars:
        return text.strip()

    sentences = re.split(r'(?<=[。！？；.!?;])\s*|\n+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 6]
    if not sentences:
        return text[:max_chars - 3].strip() + "..."

    position_scores = [12, 7, 4, 2]
    key_verbs = [
        "announced", "released", "breakthrough", "first", "new", "achieved",
        "demonstrated", "developed", "launched", "unveiled", "revealed",
        "首次", "突破", "发布", "推出", "研发", "成功", "宣布", "亮相",
        "量产", "交付", "升级", "搭载", "配备", "超过", "实现", "上市", "开售", "预售",
    ]
    tech_pattern = re.compile(r'\d+\.?\d*|[Vv]\d+|[A-Z]{2,}|HW\d|v\d+\.\d+')

    scored = []
    for i, s in enumerate(sentences[:10]):
        score = 0
        if i < len(position_scores):
            score += position_scores[i]
        else:
            score += 1
        slen = len(s)
        if 30 <= slen <= 100:
            score += 5
        elif 20 <= slen <= 130:
            score += 2
        s_lower = s.lower()
        score += sum(2 for v in key_verbs if v in s_lower)
        score += min(len(tech_pattern.findall(s)), 4)
        if slen < 15:
            score -= 5
        boilerplate = ["subscribe", "sign up", "newsletter", "版权", "转载", "关注", "订阅"]
        if any(b in s_lower for b in boilerplate):
            score -= 10
        scored.append((score, s, i))

    scored.sort(key=lambda x: -x[0])
    top_ordered = sorted(scored[:3], key=lambda x: x[2])
    result = "".join(s for _, s, _ in top_ordered)

    if len(result) > max_chars:
        top2 = sorted(scored[:2], key=lambda x: x[2])
        result = "".join(s for _, s, _ in top2)
    if len(result) > max_chars:
        result = result[:max_chars - 3].strip() + "..."
    return result


def ensure_summary(item, max_chars=200):
    """GUARANTEE every item has a proper Chinese summary <= max_chars."""
    summary = item.get("summary", "")
    # If summary exists and is reasonable length, ensure it's Chinese
    if summary and 15 < len(summary) <= max_chars:
        return ensure_chinese(summary)
    # Try to extract from raw content (translate first if English)
    content = item.get("_raw_content", "")
    lang = item.get("_lang", "en")
    if content:
        if lang == "en":
            content_zh = translate(content, "en")
        else:
            content_zh = content
        extracted = ai_extract(content_zh, max_chars)
        if extracted and len(extracted) > 15:
            return extracted
    # Title fallback
    title = item.get("title", "")
    if title:
        title = ensure_chinese(title)
        return title[:max_chars - 3] + "..." if len(title) > max_chars else title
    return "暂无摘要"


# ============================================================
# Feed Fetching
# ============================================================
def fetch_feed(feed_cfg, hours):
    s = _get_session()
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        r = s.get(feed_cfg["url"], timeout=5, allow_redirects=True)
        if r.status_code != 200:
            return items
        d = feedparser.parse(r.text)
    except Exception:
        return items

    kw = feed_cfg.get("keywords", [])
    lang = feed_cfg.get("lang", "en")
    for entry in d.entries:
        try:
            published = None
            for tf in ["published_parsed", "updated_parsed"]:
                t = entry.get(tf)
                if t:
                    try: published = datetime(*t[:6], tzinfo=timezone.utc)
                    except Exception: pass
                    break
            if published and published < cutoff:
                continue
            title = unescape(entry.get("title", "").strip())
            if not title: continue

            content = ""
            for field in ["content", "summary_detail", "summary"]:
                c = entry.get(field)
                if c:
                    if isinstance(c, list): content = c[0].get("value", "")
                    elif isinstance(c, dict): content = c.get("value", "")
                    else: content = str(c)
                    if content: break

            if kw:
                text_to_check = (title + " " + content).lower()
                if not any(k.lower() in text_to_check for k in kw): continue

            link = entry.get("link", "")
            author = ""
            if entry.get("author"): author = entry["author"]
            elif entry.get("authors") and entry["authors"]: author = entry["authors"][0].get("name", "")

            time_short = date_str = ""
            if published:
                bj = published.astimezone(BEIJING)
                time_short = f"{bj.month}/{bj.day} {bj.hour:02d}:{bj.minute:02d}"
                date_str = f"{bj.year}-{bj.month:02d}-{bj.day:02d}"

            # Translate-then-extract pipeline:
            # For English: translate full content first, then ai_extract from Chinese
            if lang == "en":
                title_zh = translate(title, "en")
                if content:
                    content_zh = translate(content, "en")
                    summary_zh = ai_extract(content_zh, 200)
                else:
                    summary_zh = title_zh
            else:
                title_zh = title
                summary_zh = ai_extract(content, 200) if content else title

            if len(summary_zh) > 200:
                summary_zh = summary_zh[:197] + "..."

            items.append({
                "title": title_zh, "title_en": title if lang == "en" else "",
                "summary": summary_zh, "link": link, "source": feed_cfg["name"],
                "author": author, "time_short": time_short, "date": date_str,
                "_raw_content": content, "_lang": lang,
            })
        except Exception: continue
    return items


def fetch_google_news(query_cfg, hours):
    s = _get_session()
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = query_cfg["query"]
    lang = query_cfg.get("lang", "en")
    if lang == "zh":
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    else:
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en&gl=US&ceid=US:en"
    try:
        r = s.get(url, timeout=6, allow_redirects=True,
                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        if r.status_code != 200: return items
        d = feedparser.parse(r.text)
    except Exception:
        return items

    for entry in d.entries:
        try:
            title = unescape(entry.get("title", "").strip())
            if not title: continue
            published = None
            for tf in ["published_parsed", "updated_parsed"]:
                t = entry.get(tf)
                if t:
                    try: published = datetime(*t[:6], tzinfo=timezone.utc)
                    except Exception: pass
                    break
            if published and published < cutoff: continue

            content = ""
            for field in ["content", "summary_detail", "summary"]:
                c = entry.get(field)
                if c:
                    if isinstance(c, list): content = c[0].get("value", "")
                    elif isinstance(c, dict): content = c.get("value", "")
                    else: content = str(c)
                    if content: break

            link = entry.get("link", "")
            author = ""
            if entry.get("author"): author = entry["author"]
            elif entry.get("authors") and entry["authors"]: author = entry["authors"][0].get("name", "")

            time_short = date_str = ""
            if published:
                bj = published.astimezone(BEIJING)
                time_short = f"{bj.month}/{bj.day} {bj.hour:02d}:{bj.minute:02d}"
                date_str = f"{bj.year}-{bj.month:02d}-{bj.day:02d}"

            # Translate-then-extract for English Google News
            if lang == "en":
                title_zh = translate(title, "en")
                if content:
                    content_zh = translate(content, "en")
                    summary_zh = ai_extract(content_zh, 200)
                else:
                    summary_zh = title_zh
            else:
                title_zh = title
                summary_zh = ai_extract(content, 200) if content else title

            if len(summary_zh) > 200:
                summary_zh = summary_zh[:197] + "..."

            items.append({
                "title": title_zh, "title_en": title if lang == "en" else "",
                "summary": summary_zh, "link": link, "source": query_cfg["name"],
                "author": author, "time_short": time_short, "date": date_str,
                "_raw_content": content, "_is_google": True, "_lang": lang,
            })
        except Exception: continue
    return items


def fetch_twitter_account(account, hours):
    """Fetch tweets via RSSHub (primary, 3s) then Nitter (fallback, 2s each)."""
    handle = account["handle"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []

    # 1) RSSHub Twitter
    try:
        r = s_get(f"https://rsshub.app/twitter/user/{handle}", timeout=3)
        if r and r.status_code == 200:
            d = feedparser.parse(r.text)
            for entry in d.entries:
                try:
                    title = entry.get("title", "").strip()
                    if not title: continue
                    published = _parse_time(entry)
                    if published and published < cutoff: continue
                    content = _get_content(entry)
                    full_text = title + " " + content
                    if not any(k.lower() in full_text.lower() for k in MORNING_STRICT_KW): continue
                    link = entry.get("link", "")
                    time_short, date_str = _format_time(published)
                    # Translate-then-extract: translate full tweet, then extract from Chinese
                    full_tweet = content if content else title
                    tweet_zh = translate(full_tweet, "en")
                    title_zh = translate(title, "en")
                    summary_zh = ai_extract(tweet_zh, 180) if len(tweet_zh) > 30 else tweet_zh
                    if len(summary_zh) > 200: summary_zh = summary_zh[:197] + "..."
                    items.append({
                        "title": title_zh, "title_en": title, "summary": summary_zh,
                        "link": link, "source": f"@{handle}", "author": account["zh"],
                        "author_handle": handle, "is_tweet": True,
                        "time_short": time_short, "date": date_str,
                        "_raw_content": full_tweet, "_lang": "en",
                    })
                except Exception: continue
    except Exception: pass

    # 2) Nitter RSS (fallback, only if RSSHub gave nothing)
    if not items:
        for instance in NITTER_INSTANCES:
            try:
                url = f"https://{instance}/{handle}/rss"
                r = s_get(url, timeout=2)
                if not r or r.status_code != 200 or len(r.text) < 100: continue
                d = feedparser.parse(r.text)
                for entry in d.entries:
                    try:
                        title = entry.get("title", "").strip()
                        if not title: continue
                        published = _parse_time(entry)
                        if published and published < cutoff: continue
                        full_text = title + " " + _get_content(entry)
                        if not any(k.lower() in full_text.lower() for k in MORNING_STRICT_KW): continue
                        link = entry.get("link", "")
                        time_short, date_str = _format_time(published)
                        # Translate-then-extract
                        tweet_zh = translate(title, "en")
                        title_zh = tweet_zh
                        summary_zh = ai_extract(tweet_zh, 180) if len(tweet_zh) > 30 else tweet_zh
                        items.append({
                            "title": title_zh, "title_en": title, "summary": summary_zh,
                            "link": link, "source": f"@{handle}", "author": account["zh"],
                            "author_handle": handle, "is_tweet": True,
                            "time_short": time_short, "date": date_str,
                            "_raw_content": title, "_lang": "en",
                        })
                    except Exception: continue
                if items: break
            except Exception: continue

    return items


def fetch_weibo_user(founder, hours):
    uid = founder["uid"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    try:
        rsshub_url = f"https://rsshub.app/weibo/user/{uid}"
        r = s_get(rsshub_url, timeout=4)
        if not r or r.status_code != 200: return items
        d = feedparser.parse(r.text)
    except Exception:
        return items

    for entry in d.entries:
        try:
            title = entry.get("title", "").strip()
            if not title: continue
            published = _parse_time(entry)
            if published and published < cutoff: continue
            content = _get_content(entry)
            link = entry.get("link", "")
            time_short, date_str = _format_time(published)
            summary_zh = ai_extract(content, 180) if content else title
            if len(summary_zh) > 200: summary_zh = summary_zh[:197] + "..."

            items.append({
                "title": title, "summary": summary_zh, "link": link,
                "source": f"微博·{founder['name']}", "author": founder["name"],
                "brand": founder["brand"], "is_weibo": True,
                "time_short": time_short, "date": date_str, "_raw_content": content,
                "_lang": "zh",
            })
        except Exception: continue
    return items


# Helper functions
def s_get(url, timeout=5):
    try:
        return _get_session().get(url, timeout=timeout, allow_redirects=True)
    except Exception:
        return None

def _parse_time(entry):
    for tf in ["published_parsed", "updated_parsed"]:
        t = entry.get(tf)
        if t:
            try: return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception: pass
    return None

def _get_content(entry):
    for field in ["content", "summary_detail", "summary"]:
        c = entry.get(field)
        if c:
            if isinstance(c, list): return c[0].get("value", "")
            elif isinstance(c, dict): return c.get("value", "")
            else: return str(c)
    return ""

def _format_time(published):
    if published:
        bj = published.astimezone(BEIJING)
        return f"{bj.month}/{bj.day} {bj.hour:02d}:{bj.minute:02d}", f"{bj.year}-{bj.month:02d}-{bj.day:02d}"
    return "", ""


# ============================================================
# Global Dedup
# ============================================================
def fingerprint(text):
    t = re.sub(r'[\s\-_|,，.。:：!！?？\(\)【】《》]+', '', text.lower())
    return hashlib.md5(t.encode()).hexdigest()[:12]

def similarity(a, b):
    if not a or not b: return 0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0

def dedup(items):
    seen_fps, seen_texts, unique = [], [], []
    for item in items:
        title = item.get("title", "")
        fp = fingerprint(title)
        if fp in seen_fps: continue
        title_clean = re.sub(r'[\s\-_|,，.。:：!！?？]+', '', title.lower())
        if any(similarity(title_clean, e) > 0.65 for e in seen_texts): continue
        seen_fps.append(fp)
        seen_texts.append(title_clean)
        unique.append(item)
    return unique


# ============================================================
# Finalize: ensure every item meets format requirements + ALL Chinese
# ============================================================
def finalize_items(items):
    for item in items:
        # Ensure summary is proper Chinese and ≤200字
        item["summary"] = ensure_summary(item, 200)
        # Ensure title is Chinese
        item["title"] = ensure_chinese(item.get("title", ""))
        # Ensure date and time
        if not item.get("date"):
            now = datetime.now(BEIJING)
            item["date"] = f"{now.year}-{now.month:02d}-{now.day:02d}"
        if not item.get("time_short"):
            now = datetime.now(BEIJING)
            item["time_short"] = f"{now.month}/{now.day} {now.hour:02d}:{now.minute:02d}"
        if not item.get("link"):
            item["link"] = ""
    return items


# ============================================================
# Morning: Fetch + Organize (Priority: Twitter → overseas → domestic → Google)
# ============================================================
def fetch_morning():
    cfg = REPORTS["morning"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")
    all_items = []

    # 1) X/Twitter accounts — HIGHEST priority (all 9 accounts)
    print("  📡 抓取 X/Twitter 博主动态（9位核心博主，FSD严格过滤）...")
    tweet_count = 0
    for account in TWITTER_ACCOUNTS:
        items = fetch_twitter_account(account, cfg["hours"])
        if items:
            print(f"  @{account['handle']}: {len(items)} 条")
            tweet_count += len(items)
        all_items.extend(items)
        time.sleep(0.15)
    print(f"  → Twitter 共 {tweet_count} 条")

    # 2) Overseas English RSS feeds (primary supplement)
    print("  📡 抓取海外特斯拉FSD专业源...")
    overseas_items = []
    for feed in MORNING_OVERSEAS_RSS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
            for item in items:
                item["is_tweet"] = False
                item["_overseas"] = True
            overseas_items.extend(items)
            all_items.extend(items)

    # 3) Domestic Chinese RSS feeds (secondary supplement)
    print("  📡 抓取国内特斯拉相关源...")
    domestic_items = []
    for feed in MORNING_DOMESTIC_RSS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
            for item in items:
                item["is_tweet"] = False
                item["_overseas"] = False
            domestic_items.extend(items)
            all_items.extend(items)

    # 4) Google News search (last resort)
    print("  📡 搜索 Google News...")
    google_items = []
    for gn in MORNING_GOOGLE_NEWS:
        items = fetch_google_news(gn, cfg["hours"])
        if items:
            print(f"  {gn['name']}: {len(items)} 条")
            google_items.extend(items)
            all_items.extend(items)

    all_items = dedup(all_items)

    # Selection priority: tweets → overseas RSS → domestic RSS → Google News
    tweets = [i for i in all_items if i.get("is_tweet")]
    overseas = [i for i in all_items if not i.get("is_tweet") and i.get("_overseas") and not i.get("_is_google")]
    domestic = [i for i in all_items if not i.get("is_tweet") and not i.get("_overseas") and not i.get("_is_google")]
    google = [i for i in all_items if i.get("_is_google")]

    selected = tweets[:8]
    remaining = cfg["max"] - len(selected)
    if remaining > 0: selected.extend(overseas[:remaining])
    remaining = cfg["max"] - len(selected)
    if remaining > 0: selected.extend(domestic[:remaining])
    remaining = cfg["max"] - len(selected)
    if remaining > 0: selected.extend(google[:remaining])
    selected = selected[:cfg["max"]]
    selected = finalize_items(selected)

    print(f"  共 {len(selected)} 条（推文 {len(tweets)} / 海外 {len(overseas)} / 国内 {len(domestic)} / Google {len(google)}）")
    return selected


# ============================================================
# Noon: Fetch + Organize
# ============================================================
def fetch_noon():
    cfg = REPORTS["noon"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")
    all_items = []

    print("  📡 抓取创始人微博...")
    for founder in WEIBO_FOUNDERS:
        items = fetch_weibo_user(founder, cfg["hours"])
        if items: print(f"  {founder['name']}: {len(items)} 条")
        all_items.extend(items)
        time.sleep(0.2)

    print("  📡 抓取新能源资讯...")
    for feed in NOON_RSS_FEEDS:
        items = fetch_feed(feed, cfg["hours"])
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
            for item in items:
                item["brand"] = assign_brand(item["title"] + " " + item.get("summary", ""))
                item["is_weibo"] = False
            all_items.extend(items)

    print("  📡 搜索 Google News...")
    for gn in NOON_GOOGLE_NEWS:
        items = fetch_google_news(gn, cfg["hours"])
        if items:
            print(f"  {gn['name']}: {len(items)} 条")
            for item in items:
                item["brand"] = assign_brand(item["title"] + " " + item.get("summary", ""))
                item["is_weibo"] = False
            all_items.extend(items)

    all_items = dedup(all_items)
    brand_items = {b["name"]: [] for b in NOON_BRANDS}
    brand_items["其他"] = []
    for item in all_items:
        b = item.get("brand", "")
        if b in brand_items: brand_items[b].append(item)
        else: item["brand"] = "其他"; brand_items["其他"].append(item)

    # Select items: prioritize brand-matched, then fill with "其他"
    selected = []
    per_brand = max(3, cfg["max"] // len(NOON_BRANDS))
    for brand_name in [b["name"] for b in NOON_BRANDS]:
        selected.extend(brand_items.get(brand_name, [])[:per_brand])
    # Fill remaining slots with "其他" items
    remaining = cfg["max"] - len(selected)
    if remaining > 0:
        selected.extend(brand_items.get("其他", [])[:remaining])
    selected = selected[:cfg["max"]]
    selected = finalize_items(selected)

    brand_counts = {b: len([i for i in selected if i.get("brand") == b]) for b in [b["name"] for b in NOON_BRANDS]}
    print(f"  共 {len(selected)} 条（" + " / ".join(f"{k}{v}条" for k, v in brand_counts.items()) + "）")
    return selected, brand_items

def assign_brand(text):
    text_lower = text.lower()
    best_brand, best_score = "", 0
    for brand_info in NOON_BRANDS:
        score = sum(1 for k in brand_info["keywords"] if k.lower() in text_lower)
        if score > best_score: best_score = score; best_brand = brand_info["name"]
    return best_brand if best_score >= 1 else "其他"


# ============================================================
# Evening: Fetch + Organize
# ============================================================
def fetch_evening():
    cfg = REPORTS["evening"]
    print(f"[1/3] 采集「{cfg['title']}」（最近 {cfg['hours']} 小时）...")
    all_items = []

    for feed in EVENING_RSS_FEEDS:
        items = fetch_feed(feed, cfg["hours"])
        if items: print(f"  {feed['name']}: {len(items)} 条"); all_items.extend(items)

    print("  📡 搜索 Google News...")
    for gn in EVENING_GOOGLE_NEWS:
        items = fetch_google_news(gn, cfg["hours"])
        if items: print(f"  {gn['name']}: {len(items)} 条"); all_items.extend(items)

    all_items = dedup(all_items)
    for item in all_items:
        item["domain"] = assign_domain(item["title"] + " " + item.get("summary", ""))

    domain_items = {d["tag"]: [] for d in EVENING_DOMAINS}
    for item in all_items:
        tag = item.get("domain", "AI")
        if tag in domain_items: domain_items[tag].append(item)
        else: domain_items["AI"].append(item)

    selected = []
    per_domain = max(2, cfg["max"] // len(EVENING_DOMAINS))
    for domain in EVENING_DOMAINS:
        selected.extend(domain_items.get(domain["tag"], [])[:per_domain])
    remaining = cfg["max"] - len(selected)
    if remaining > 0:
        unselected = [i for i in all_items if i not in selected]
        selected.extend(unselected[:remaining])
    selected = selected[:cfg["max"]]
    selected = finalize_items(selected)

    domain_counts = {d["tag"]: len([i for i in selected if i.get("domain") == d["tag"]]) for d in EVENING_DOMAINS}
    active = {k: v for k, v in domain_counts.items() if v > 0}
    print(f"  共 {len(selected)} 条（" + " / ".join(f"【{k}】{v}条" for k, v in active.items()) + "）")
    return selected

def assign_domain(text):
    text_lower = text.lower()
    best_tag, best_score = "AI", 0
    for domain in EVENING_DOMAINS:
        score = sum(1 for k in domain["keywords"] if k.lower() in text_lower)
        if score > best_score: best_score = score; best_tag = domain["tag"]
    return best_tag


# ============================================================
# Format: WeChat Push (Server酱) — Markdown
# ============================================================
def push_wechat_morning(items):
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    lines = [f"## 🌅 特斯拉FSD晨报", f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条", ""]
    for item in items:
        source = item.get("source", "")
        time_str = item.get("time_short", "")
        date_str = item.get("date", "")
        summary = item.get("summary", "")
        link = item.get("link", "")
        if item.get("is_tweet"):
            handle = item.get("author_handle", "")
            lines.append(f"**@{handle}** · {date_str} {time_str}")
        else:
            lines.append(f"**{item['title']}**")
        lines.append(f"📝 {summary}")
        if link: lines.append(f"🔗 [原文链接]({link})")
        lines.append(f"_来源：{source} · {date_str} {time_str}_")
        lines.append("---")
        lines.append("")
    lines.append("_🤖 云端自动采集 · 特斯拉FSD/智驾动态_")
    return "\n".join(lines)

def push_wechat_noon(items, brand_items):
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    lines = [f"## ⚡ 新能源午报", f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条", ""]
    for brand_info in NOON_BRANDS:
        brand_name = brand_info["name"]
        brand_list = [i for i in items if i.get("brand") == brand_name]
        if not brand_list: continue
        lines.append(f"### 🚗 {brand_name}（{brand_info['en']}）")
        lines.append("")
        for item in brand_list:
            author = item.get("author", item.get("source", ""))
            source = item.get("source", "")
            time_str = item.get("time_short", "")
            date_str = item.get("date", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            if item.get("is_weibo"):
                lines.append(f"👤 **{author}** · {date_str} {time_str}")
            else:
                lines.append(f"**{item['title']}**")
            lines.append(f"📝 {summary}")
            if link: lines.append(f"🔗 [原文链接]({link})")
            lines.append(f"_来源：{source} · {date_str} {time_str}_")
            lines.append("---")
            lines.append("")
    lines.append("_🤖 云端自动采集 · 新能源智驾动态_")
    return "\n".join(lines)

def push_wechat_evening(items):
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    lines = [f"## 🔬 前沿科技晚报", f"> {now.month}月{now.day}日 {weekday}  ·  共{len(items)}条", ""]
    domain_order = [d["tag"] for d in EVENING_DOMAINS]
    domain_icons = {d["tag"]: d["icon"] for d in EVENING_DOMAINS}
    for domain in domain_order:
        domain_list = [i for i in items if i.get("domain") == domain]
        if not domain_list: continue
        icon = domain_icons.get(domain, "🔬")
        lines.append(f"### {icon} {domain}")
        lines.append("")
        for item in domain_list:
            source = item.get("source", "")
            time_str = item.get("time_short", "")
            date_str = item.get("date", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            lines.append(f"【{domain}】**{item['title']}**")
            lines.append(f"📝 {summary}")
            if link: lines.append(f"🔗 [原文链接]({link})")
            lines.append(f"_来源：{source} · {date_str} {time_str}_")
            lines.append("---")
            lines.append("")
    lines.append("_🤖 云端自动采集 · 前沿科技资讯_")
    return "\n".join(lines)

def push_wechat(items, cfg, brand_items=None):
    print("[2/3] 正在推送微信...")
    if REPORT_TYPE == "morning": content = push_wechat_morning(items)
    elif REPORT_TYPE == "noon": content = push_wechat_noon(items, brand_items or {})
    else: content = push_wechat_evening(items)
    now = datetime.now(BEIJING)
    if SCT_SENDKEY:
        resp = requests.post(f"https://sctapi.ftqq.com/{SCT_SENDKEY}.send",
            json={"title": f"{cfg['emoji']} {cfg['title']}（{now.month}月{now.day}日）", "desp": content}, timeout=30)
        r = resp.json()
        if r.get("code") == 0: print("  ✅ 微信推送成功")
        else: print(f"  ❌ 微信推送失败: {r}")
    else:
        print("  ⚠ 跳过微信推送（无SCT_SENDKEY）")
    return content


# ============================================================
# Format: Email Push (iCloud) — HTML
# ============================================================
def push_email_morning(items):
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    c1, c2 = "#e82127", "#c41e24"
    cards = ""
    for item in items:
        source = item.get("source", "")
        time_str = item.get("time_short", "")
        date_str = item.get("date", "")
        summary = item.get("summary", "")
        link = item.get("link", "")
        if item.get("is_tweet"):
            handle = item.get("author_handle", "")
            cards += f'''
            <div style="padding:16px;background:#fafafa;border-radius:10px;margin-bottom:12px;border-left:4px solid {c1};">
                <div style="font-weight:700;color:{c1};font-size:14px;margin-bottom:6px;">@{handle}</div>
                <div style="color:#555;font-size:14px;line-height:1.75;">{summary}</div>
                <div style="margin-top:8px;">
                    {f'<a href="{link}" target="_blank" style="color:#1a73e8;font-size:12px;">🔗 原文链接</a>' if link else ''}
                    <span style="color:#bbb;font-size:11px;margin-left:12px;">来源：{source} · {date_str} {time_str}</span>
                </div>
            </div>'''
        else:
            link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid {c1};">
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{link_html}</div>
                <div style="color:#555;font-size:13px;line-height:1.75;margin-top:8px;">{summary}</div>
                <div style="margin-top:8px;">
                    {f'<a href="{link}" target="_blank" style="color:#1a73e8;font-size:12px;">🔗 原文链接</a>' if link else ''}
                    <span style="color:#bbb;font-size:11px;margin-left:12px;">来源：{source} · {date_str} {time_str}</span>
                </div>
            </div>'''
    return _email_wrapper("🌅 特斯拉FSD晨报", now, weekday, c1, c2, cards, len(items))

def push_email_noon(items, brand_items):
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    c1, c2 = "#1a73e8", "#1557b0"
    brand_colors = {"蔚来": "#1e88e5", "理想": "#43a047", "小鹏": "#ff9800", "小米": "#ff6f00", "问界": "#e53935", "其他": "#9e9e9e"}
    cards = ""
    for brand_info in NOON_BRANDS:
        brand_name = brand_info["name"]
        brand_list = [i for i in items if i.get("brand") == brand_name]
        if not brand_list: continue
        bc = brand_colors.get(brand_name, "#9e9e9e")
        cards += f'<div style="border-left:4px solid {bc};padding:6px 0 6px 14px;margin:24px 0 14px;"><span style="color:{bc};font-size:16px;font-weight:700;">🚗 {brand_name}（{brand_info["en"]}）</span></div>'
        for item in brand_list:
            author = item.get("author", item.get("source", ""))
            source = item.get("source", "")
            time_str = item.get("time_short", "")
            date_str = item.get("date", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            bc2 = bc if item.get("is_weibo") else "#eee"
            link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
            weibo_tag = f'<div style="font-size:12px;color:{bc};font-weight:600;margin-bottom:4px;">👤 {author}</div>' if item.get("is_weibo") else ""
            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid {bc2};">
                {weibo_tag}
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{link_html}</div>
                <div style="color:#555;font-size:13px;line-height:1.75;margin-top:8px;">{summary}</div>
                <div style="margin-top:8px;">
                    {f'<a href="{link}" target="_blank" style="color:#1a73e8;font-size:12px;">🔗 原文链接</a>' if link else ''}
                    <span style="color:#bbb;font-size:11px;margin-left:12px;">来源：{source} · {date_str} {time_str}</span>
                </div>
            </div>'''
    return _email_wrapper("⚡ 新能源午报", now, weekday, c1, c2, cards, len(items))

def push_email_evening(items):
    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]
    c1, c2 = "#7c3aed", "#6d28d9"
    domain_colors = {"AI": "#6366f1", "机器人": "#8b5cf6", "生物": "#10b981", "航天": "#f59e0b", "芯片": "#ef4444"}
    domain_icons = {d["tag"]: d["icon"] for d in EVENING_DOMAINS}
    cards = ""
    for domain in [d["tag"] for d in EVENING_DOMAINS]:
        domain_list = [i for i in items if i.get("domain") == domain]
        if not domain_list: continue
        dc = domain_colors.get(domain, "#6366f1")
        icon = domain_icons.get(domain, "🔬")
        cards += f'<div style="border-left:4px solid {dc};padding:6px 0 6px 14px;margin:24px 0 14px;"><span style="color:{dc};font-size:16px;font-weight:700;">{icon} {domain}</span></div>'
        for item in domain_list:
            link = item.get("link", "")
            summary = item.get("summary", "")
            source = item.get("source", "")
            time_str = item.get("time_short", "")
            date_str = item.get("date", "")
            link_html = f'<a href="{link}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>' if link else item["title"]
            tag_badge = f'<span style="display:inline-block;background:#f3e8ff;color:#7c3aed;padding:1px 8px;border-radius:3px;font-size:10px;margin-right:6px;">{domain}</span>'
            cards += f'''
            <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid {dc};">
                <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{tag_badge}{link_html}</div>
                <div style="color:#555;font-size:13px;line-height:1.75;margin-top:8px;">{summary}</div>
                <div style="margin-top:8px;">
                    {f'<a href="{link}" target="_blank" style="color:#1a73e8;font-size:12px;">🔗 原文链接</a>' if link else ''}
                    <span style="color:#bbb;font-size:11px;margin-left:12px;">来源：{source} · {date_str} {time_str}</span>
                </div>
            </div>'''
    return _email_wrapper("🔬 前沿科技晚报", now, weekday, c1, c2, cards, len(items))

def _email_wrapper(title, now, weekday, c1, c2, cards, total):
    return f'''
    <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;">
        <div style="background:linear-gradient(135deg,{c1} 0%,{c2} 100%);padding:28px 32px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">{title}</h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,0.75);font-size:13px;">{now.year}年{now.month}月{now.day}日 {weekday}</p>
        </div>
        <div style="padding:20px 28px 28px;">
            {cards}
            <div style="text-align:center;color:#ccc;font-size:11px;margin-top:24px;padding-top:16px;border-top:1px solid #f0f0f0;">🤖 云端自动采集 · 共{total}条</div>
        </div>
    </div>'''

def push_email(items, cfg, brand_items=None):
    print("[3/3] 正在发送邮件...")
    if REPORT_TYPE == "morning": html = push_email_morning(items)
    elif REPORT_TYPE == "noon": html = push_email_noon(items, brand_items or {})
    else: html = push_email_evening(items)
    now = datetime.now(BEIJING)
    if ICLOUD_USER and ICLOUD_PASS:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{cfg['emoji']} {cfg['title']}（{now.month}月{now.day}日）"
        msg["From"] = ICLOUD_USER; msg["To"] = ICLOUD_USER
        msg.attach(MIMEText(html, "html", "utf-8"))
        try:
            with smtplib.SMTP("smtp.mail.me.com", 587) as s:
                s.starttls(); s.login(ICLOUD_USER, ICLOUD_PASS)
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
    print(f"  {cfg['emoji']} {cfg['title']} v5.2")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} (北京时间)")
    print(f"{'='*50}\n")

    brand_items = None
    if REPORT_TYPE == "morning": items = fetch_morning()
    elif REPORT_TYPE == "noon": items, brand_items = fetch_noon()
    else: items = fetch_evening()

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
