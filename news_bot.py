#!/usr/bin/env python3
"""
News Bot v3 - Multi-topic Daily Briefing
  Morning 08:00 : Tesla + FSD updates + video links + blogger highlights
  Noon    12:00 : Chinese NEV + smart driving (Li/Huawei/XPeng/Xiaomi) + KOL opinions
  Evening 17:00 : Frontier tech / AI / biotech breakthroughs

Free RSS-based, auto-translate English→Chinese, hidden clickable links.
Dual push: WeChat (Server酱 Markdown) + iCloud Email (HTML).
"""

import os, sys, smtplib, re, time, feedparser, requests
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
UA = "Mozilla/5.0 (compatible; NewsBot/3.0)"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORTS = {
    "morning":  {"title": "特斯拉晨报", "emoji": "🌅", "hours": 10},
    "noon":    {"title": "新能源午报", "emoji": "⚡", "hours": 6},
    "evening": {"title": "前沿晚报",   "emoji": "🔬", "hours": 8},
}

# ============================================================
# RSS Feed Sources
# ============================================================

MORNING_FEEDS = [
    # --- Chinese Tesla news ---
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["特斯拉", "Tesla", "马斯克", "Musk", "FSD", "自动驾驶",
                  "Robotaxi", "Cybertruck", "机器人", "Optimus", "超级充电",
                  "Model Y", "Model 3", "Model S", "Model X", "能量回收"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["特斯拉", "Tesla", "马斯克", "FSD", "Model Y", "Model 3",
                  "Cybertruck", "自动驾驶", "充电"]},
    # --- English Tesla news ---
    {"name": "Electrek", "url": "https://electrek.co/feed/", "lang": "en",
     "keywords": ["tesla", "model y", "model 3", "model s", "model x",
                  "cybertruck", "fsd", "autopilot", "musk", "supercharger",
                  "giga", "robotaxi", "optimus", "full self-driving",
                  "software update", "recall"]},
    {"name": "TeslaRati", "url": "https://www.teslarati.com/feed/", "lang": "en",
     "keywords": ["tesla", "model y", "model 3", "fsd", "autopilot", "musk",
                  "giga", "robotaxi", "optimus", "cybertruck", "update"]},
    {"name": "Not a Tesla App", "url": "https://www.notateslaapp.com/rss", "lang": "en",
     "keywords": ["tesla", "fsd", "autopilot", "software", "update", "model y",
                  "model 3", "cybertruck", "supercharger", "app"]},
    {"name": "InsideEVs", "url": "https://insideevs.com/rssfeeds/all.xml", "lang": "en",
     "keywords": ["tesla", "model y", "model 3", "fsd", "autopilot",
                  "musk", "cybertruck", "update"]},
    # --- YouTube FSD videos ---
    {"name": "YouTube FSD实测", "url": "https://www.youtube.com/feeds/videos.xml?search_query=tesla+fsd+test+drive+2025", "lang": "en", "type": "video",
     "keywords": ["fsd", "tesla", "full self-driving", "autopilot", "drive"]},
    {"name": "YouTube特斯拉", "url": "https://www.youtube.com/feeds/videos.xml?search_query=tesla+update+review+2025", "lang": "en", "type": "video",
     "keywords": ["tesla", "update", "review", "model"]},
    # --- Reddit Tesla community ---
    {"name": "Reddit r/teslamotors", "url": "https://www.reddit.com/r/teslamotors/new/.rss", "lang": "en",
     "keywords": ["tesla", "fsd", "model y", "model 3", "autopilot", "update", "musk"]},
    {"name": "Reddit r/RealTesla", "url": "https://www.reddit.com/r/RealTesla/new/.rss", "lang": "en",
     "keywords": ["fsd", "tesla", "autopilot", "drive", "fail", "save"]},
]

NOON_FEEDS = [
    # --- Chinese NEV + smart driving ---
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["新能源", "问界", "理想", "小鹏", "蔚来", "小米汽车", "小米SU7",
                  "比亚迪", "极氪", "智驾", "NOA", "智己", "特斯拉", "电车",
                  "充电", "续航", "固态电池", "造车", "鸿蒙智行", "享界",
                  "华为智驾", "ADS", "文远知行", "HSD", "自动驾驶", "高阶智驾",
                  "城市NOA", "端到端", "理想汽车", "小鹏汽车", "蔚来汽车",
                  "华为", "阿维塔", "极越", "零跑", "岚图", "深蓝", "哪吒"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["汽车", "新能源", "问界", "理想", "小鹏", "蔚来", "小米",
                  "比亚迪", "智驾", "特斯拉", "充电", "续航", "交付", "销量",
                  "自动驾驶", "华为", "ADS", "NOA", "文远知行", "极氪", "智己"]},
    # --- English NEV coverage ---
    {"name": "InsideEVs", "url": "https://insideevs.com/rssfeeds/all.xml", "lang": "en",
     "keywords": ["BYD", "NIO", "XPeng", "Li Auto", "Xiaomi", "Aito", "Zeekr",
                  "EV sales", "Chinese EV", "smart driving", "NOA", "Huawei",
                  "WeRide", "HSD", "IM Motors", "Avatr"]},
    {"name": "CarNewsChina", "url": "https://www.carnewschina.com/feed/", "lang": "en",
     "keywords": ["BYD", "NIO", "XPeng", "Li Auto", "Xiaomi", "Aito", "Zeekr",
                  "Huawei", "smart driving", "EV", "China", "sales", "launch"]},
    # --- Reddit ---
    {"name": "Reddit r/electricvehicles", "url": "https://www.reddit.com/r/electricvehicles/new/.rss", "lang": "en",
     "keywords": ["BYD", "NIO", "XPeng", "Li Auto", "Xiaomi", "Chinese EV", "Huawei"]},
]

EVENING_FEEDS = [
    # --- AI ---
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "lang": "en",
     "keywords": ["AI", "artificial intelligence", "GPT", "LLM", "openai",
                  "google", "anthropic", "nvidia", "deep learning", "model",
                  "robot", "startup", "foundation model", "claude", "gemini",
                  "chatbot", "copilot", "agent", "reasoning"]},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "lang": "en",
     "keywords": ["AI", "artificial intelligence", "GPT", "LLM", "generative",
                  "nvidia", "deep learning", "model", "robot", "autonomous",
                  "openai", "google", "microsoft", "apple", "meta"]},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/", "lang": "en",
     "keywords": ["AI", "artificial intelligence", "biotech", "gene", "quantum",
                  "breakthrough", "climate", "energy", "robot", "research",
                  "CRISPR", "neural", "space", "nuclear"]},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en",
     "keywords": ["AI", "artificial intelligence", "OpenAI", "Google", "Apple",
                  "breakthrough", "research", "science", "space", "quantum",
                  "robot", "nvidia", "chip", "GPT", "model"]},
    # --- Science & Biotech ---
    {"name": "Science Daily", "url": "https://www.sciencedaily.com/rss/top.xml", "lang": "en",
     "keywords": ["breakthrough", "discovery", "research", "gene", "CRISPR",
                  "brain", "cancer", "quantum", "AI", "climate", "space",
                  "stem cell", "protein", "neural", "evolution", "mars"]},
    {"name": "Nature", "url": "https://www.nature.com/nature.rss", "lang": "en",
     "keywords": ["breakthrough", "discovery", "gene", "CRISPR", "AI", "quantum",
                  "brain", "science", "research", "protein", "cell", "cancer",
                  "climate", "physics", "neuroscience"]},
    # --- Chinese tech/science ---
    {"name": "36氪科技", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["AI", "人工智能", "大模型", "GPT", "芯片", "量子", "生物",
                  "基因", "科学", "突破", "OpenAI", "Google", "苹果", "微软",
                  "英伟达", "机器人", "SpaceX", "火箭", "马斯克", "脑机",
                  "CRISPR", "可控核聚变", "量子计算"]},
    {"name": "IT之家科技", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["AI", "人工智能", "大模型", "芯片", "量子", "生物", "基因编辑",
                  "科学突破", "OpenAI", "英伟达", "苹果", "微软", "脑机",
                  "核聚变", "火星"]},
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
              r'Photo credit.*', r'Posted by.*', r'Leave a comment.*']:
        text = re.sub(p, '', text, flags=re.IGNORECASE).strip()
    return text


def truncate(text, max_len=180):
    if not text or len(text) <= max_len:
        return text
    return text[:max_len].rstrip(' .,:;！？，。、；：""''…') + "……"


def is_chinese(text):
    if not text:
        return False
    return len(re.findall(r'[\u4e00-\u9fff]', text)) > len(text) * 0.15


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
        return f"{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
    now = datetime.now(BEIJING)
    return f"{now.month}月{now.day}日"


def within_hours(entry, hours):
    dt = parse_time(entry)
    if not dt:
        return True
    return (datetime.now(BEIJING) - dt).total_seconds() <= hours * 3600


# ============================================================
# Translation (Free, no API key)
# ============================================================
def translate(text):
    """Translate English to Chinese via free APIs."""
    if not text or len(text) < 3 or is_chinese(text):
        return text

    # Google Translate (unofficial)
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text[:1000]},
            timeout=8, headers={"User-Agent": UA},
        )
        if r.status_code == 200:
            parts = r.json()
            result = "".join(p[0] for p in parts[0] if p[0])
            if result and is_chinese(result):
                return result
    except Exception:
        pass
    time.sleep(0.3)

    # MyMemory fallback
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": "en|zh-CN"}, timeout=8,
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
# Feed Fetching
# ============================================================
def fetch_feed(feed, hours):
    try:
        d = feedparser.parse(feed["url"])
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

            dt = parse_time(entry)
            time_str = fmt_time(dt)

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
                    summary = re.sub(r'^[\s\-_|,，：:]+', '', summary).strip()

            # Detect if it's a video (YouTube links)
            link = entry.get("link", "")
            if "youtube.com" in link or "youtu.be" in link:
                is_video = True

            results.append({
                "title": title,
                "source": feed["name"],
                "time": time_str,
                "summary": truncate(summary, 160) if summary else "",
                "link": link,
                "is_video": is_video,
            })

        return results
    except Exception as e:
        print(f"  ⚠ {feed['name']}: {e}")
        return []


def dedup(items):
    seen, unique = [], []
    for item in items:
        norm = re.sub(r'[\s\-_|,，.。:：!！?？""\'\'（）()\[\]]+', '', item["title"].lower())[:30]
        if not any(norm in s or s in norm for s in seen):
            seen.append(norm)
            unique.append(item)
    return unique


# ============================================================
# News Organization
# ============================================================
def organize_morning(items):
    """Morning: Tesla news + FSD videos, Chinese first."""
    zh = [i for i in items if is_chinese(i["title"])]
    en = [i for i in items if not is_chinese(i["title"])]
    videos = [i for i in en if i.get("is_video")]
    articles = [i for i in en if not i.get("is_video")]

    sections = []
    if zh:
        sections.append({"name": "🇨🇳 国内动态", "icon": "newspaper", "news": zh[:8]})
    if videos:
        sections.append({"name": "🎬 FSD 实测 & 视频", "icon": "video", "news": videos[:6]})
    if articles:
        sections.append({"name": "🌍 海外资讯", "icon": "newspaper", "news": articles[:6]})
    return sections


def organize_noon(items):
    """Noon: NEV + smart driving, 10-15 items."""
    zh = [i for i in items if is_chinese(i["title"])]
    en = [i for i in items if not is_chinese(i["title"])]

    sections = []
    if zh:
        sections.append({"name": "🚗 新能源 & 智驾动态", "icon": "newspaper", "news": zh[:12]})
    if en:
        sections.append({"name": "🌍 海外动态", "icon": "newspaper", "news": en[:5]})
    return sections


def organize_evening(items):
    """Evening: AI + biotech + frontier science."""
    zh = [i for i in items if is_chinese(i["title"])]
    en = [i for i in items if not is_chinese(i["title"])]

    # Split English into AI vs Science
    ai_kw = ["ai", "gpt", "openai", "model", "llm", "machine learning", "deep learning",
             "nvidia", "robot", "chip", "artificial"]
    sci_kw = ["gene", "crispr", "brain", "cancer", "protein", "quantum", "stem cell",
              "climate", "physics", "neuroscience", "space", "nuclear", "evolution",
              "mars", "biotech", "cell"]

    ai_items, sci_items = [], []
    for item in en:
        t = item["title"].lower()
        if any(k in t for k in ai_kw):
            ai_items.append(item)
        elif any(k in t for k in sci_kw):
            sci_items.append(item)
        else:
            ai_items.append(item)  # default to AI section

    sections = []
    if zh:
        sections.append({"name": "🇨🇳 国内科技动态", "icon": "newspaper", "news": zh[:8]})
    if ai_items:
        sections.append({"name": "🤖 人工智能", "icon": "newspaper", "news": ai_items[:6]})
    if sci_items:
        sections.append({"name": "🔬 前沿科学", "icon": "newspaper", "news": sci_items[:5]})
    return sections


def fetch_all_news(report_type):
    config = REPORTS[report_type]
    feed_map = {"morning": MORNING_FEEDS, "noon": NOON_FEEDS, "evening": EVENING_FEEDS}
    feeds = feed_map[report_type]
    hours = config["hours"]

    print(f"[1/3] 正在采集「{config['title']}」（最近 {hours} 小时）...")

    all_items = []
    for feed in feeds:
        items = fetch_feed(feed, hours)
        if items:
            print(f"  {feed['name']}: {len(items)} 条")
        all_items.extend(items)

    all_items = dedup(all_items)

    # Organize by report type
    org_map = {"morning": organize_morning, "noon": organize_noon, "evening": organize_evening}
    sections = org_map[report_type](all_items)

    total = sum(len(s["news"]) for s in sections)
    print(f"  共 {total} 条（{len(sections)} 个板块）")
    return {"sections": sections, "total": total}


# ============================================================
# WeChat Push (Server酱) - Markdown
# ============================================================
def push_wechat(data, cfg):
    print("[2/3] 正在推送微信...")

    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    lines = [
        f"## {cfg['emoji']} {cfg['title']}",
        f"> {now.month}月{now.day}日 {weekday}  ·  共{data['total']}条",
        "",
    ]

    for section in data["sections"]:
        lines.append(f"### {section['name']}")
        lines.append("")
        for item in section["news"]:
            # Video items: add 🎬 prefix
            prefix = "🎬 " if item.get("is_video") else ""

            # Title as hidden clickable link
            if item.get("link"):
                lines.append(f"{prefix}**[{item['title']}]({item['link']})**")
            else:
                lines.append(f"{prefix}**{item['title']}**")

            # Source + time
            lines.append(f"_{item['source']}  ·  {item['time']}_")

            # Summary
            if item.get("summary"):
                lines.append(f"> {item['summary']}")
            lines.append("")

    lines.append("---")
    lines.append("_🤖 RSS自动采集 · 云端推送_")

    content = "\n".join(lines)

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
        print("  ⚠ 跳过微信推送")

    return content


# ============================================================
# Email Push (iCloud) - HTML
# ============================================================
def push_email(data, cfg):
    print("[3/3] 正在发送邮件...")

    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    # Build gradient colors per report type
    colors = {
        "morning": ("#e82127", "#c41e24", "特斯拉红"),
        "noon":    ("#1a73e8", "#1557b0", "科技蓝"),
        "evening": ("#7c3aed", "#6d28d9", "前沿紫"),
    }
    c1, c2, _ = colors.get(REPORT_TYPE, colors["morning"])

    cards = ""
    for section in data["sections"]:
        cards += f'''
        <div style="border-left:4px solid {c1};padding:6px 0 6px 14px;margin:24px 0 14px;">
            <span style="color:{c1};font-size:16px;font-weight:700;">{section["name"]}</span>
        </div>'''

        for item in section["news"]:
            video_tag = '<span style="display:inline-block;background:#fff3cd;color:#856404;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:6px;">🎬 视频</span>' if item.get("is_video") else ""

            # Hidden link (color matches text, no underline)
            if item.get("link"):
                title_html = f'<a href="{item["link"]}" target="_blank" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>'
            else:
                title_html = item["title"]

            summary_html = ""
            if item.get("summary"):
                summary_html = f'''
            <div style="color:#666;font-size:13px;line-height:1.75;margin-top:8px;">
                {item["summary"]}
            </div>'''

            cards += f'''
        <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #eee;">
            <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">
                {title_html}{video_tag}
            </div>
            <div style="margin-top:6px;">
                <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:500;">{item["source"]}</span>
                <span style="color:#bbb;font-size:12px;margin-left:8px;">{item["time"]}</span>
            </div>{summary_html}
        </div>'''

    html = f'''
    <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;">
        <div style="background:linear-gradient(135deg,{c1} 0%,{c2} 100%);padding:28px 32px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">{cfg["emoji"]} {cfg["title"]}</h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,0.75);font-size:13px;">{now.year}年{now.month}月{now.day}日 {weekday}</p>
        </div>
        <div style="padding:20px 28px 28px;">
            {cards}
            <div style="text-align:center;color:#ccc;font-size:11px;margin-top:24px;padding-top:16px;border-top:1px solid #f0f0f0;">
                🤖 RSS自动采集 · 云端推送 · 共{data["total"]}条
            </div>
        </div>
    </div>'''

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
        print("  ⚠ 跳过邮件发送")

    return html


# ============================================================
# Main
# ============================================================
def main():
    cfg = REPORTS[REPORT_TYPE]
    now = datetime.now(BEIJING)

    print(f"\n{'='*50}")
    print(f"  {cfg['emoji']} {cfg['title']} v3")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} (北京时间)")
    print(f"{'='*50}\n")

    data = fetch_all_news(REPORT_TYPE)

    if data["total"] == 0:
        print("未采集到新闻，跳过推送。")
        return

    push_wechat(data, cfg)
    push_email(data, cfg)

    print(f"\n{'='*50}")
    print("  ✅ 全部完成！")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
