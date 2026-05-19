#!/usr/bin/env python3
"""
Tesla & NEV News Bot - Cloud RSS Version (v2)
- Free RSS feeds, no API keys
- Auto-translate English to Chinese
- Hidden links (title is clickable, URL not visible)
- Source + precise time + summary
- Dual push: WeChat (Server酱 Markdown) + iCloud Email (HTML)
"""

import os
import sys
import smtplib
import re
import time
import feedparser
import requests
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
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORTS = {
    "morning":  {"title": "特斯拉晨报", "emoji": "🌅", "hours": 12},
    "noon":    {"title": "新能源午报", "emoji": "⚡", "hours": 6},
    "evening": {"title": "特斯拉晚报", "emoji": "🌙", "hours": 12},
}

# ============================================================
# RSS Sources (Chinese first for quality)
# ============================================================
TESLA_FEEDS = [
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["特斯拉", "Tesla", "马斯克", "Musk", "FSD", "自动驾驶", "Robotaxi", "Cybertruck", "机器人"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["特斯拉", "Tesla", "马斯克", "FSD", "Model Y", "Model 3", "Cybertruck"]},
    {"name": "Electrek", "url": "https://electrek.co/feed/", "lang": "en",
     "keywords": ["tesla", "model y", "model 3", "model s", "model x",
                  "cybertruck", "fsd", "autopilot", "musk", "supercharger",
                  "giga", "robotaxi", "optimus"]},
    {"name": "TeslaRati", "url": "https://www.teslarati.com/feed/", "lang": "en",
     "keywords": ["tesla", "model y", "model 3", "fsd", "autopilot", "musk", "giga"]},
    {"name": "InsideEVs", "url": "https://insideevs.com/rssfeeds/all.xml", "lang": "en",
     "keywords": ["tesla", "model y", "model 3", "fsd", "autopilot", "musk", "cybertruck"]},
]

NEV_FEEDS = [
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh",
     "keywords": ["新能源", "问界", "理想", "小鹏", "蔚来", "小米汽车", "小米SU7",
                  "比亚迪", "极氪", "智驾", "NOA", "智己", "特斯拉", "电车",
                  "充电", "续航", "固态电池", "造车", "鸿蒙智行", "享界"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh",
     "keywords": ["汽车", "新能源", "问界", "理想", "小鹏", "蔚来", "小米",
                  "比亚迪", "智驾", "特斯拉", "充电", "续航", "交付", "销量"]},
    {"name": "InsideEVs", "url": "https://insideevs.com/rssfeeds/all.xml", "lang": "en",
     "keywords": ["BYD", "NIO", "XPeng", "Li Auto", "Xiaomi", "Aito", "Zeekr", "EV sales"]},
]


# ============================================================
# Utility Functions
# ============================================================
def clean_html(text):
    """Remove HTML tags and clean up text."""
    text = unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common boilerplate
    for pattern in [r'Read more.*', r'Continue reading.*', r'Click here.*',
                    r'Source:.*', r'Image via.*', r'\[…\]', r'\.{3,}']:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
    return text


def truncate_text(text, max_len=180):
    """Smart truncate with Chinese-friendly ellipsis."""
    if not text or len(text) <= max_len:
        return text
    return text[:max_len].rstrip(' .,:;！？，。、；：""''') + "……"


def is_chinese(text):
    """Check if text contains significant Chinese characters."""
    if not text:
        return False
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    return chinese > len(text) * 0.15


def parse_pub_time(entry):
    """Parse publication time, return Beijing timezone datetime."""
    try:
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub:
            return datetime(*pub[:6], tzinfo=timezone.utc).astimezone(BEIJING)
    except Exception:
        pass
    return None


def format_time(dt):
    """Format datetime as '5月19日 08:30'."""
    if dt:
        return f"{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
    now = datetime.now(BEIJING)
    return f"{now.month}月{now.day}日 {now.hour:02d}:{now.minute:02d}"


def time_within(entry, hours):
    """Check if entry was published within given hours."""
    dt = parse_pub_time(entry)
    if not dt:
        return True  # Unknown time, include it
    elapsed = (datetime.now(BEIJING) - dt).total_seconds()
    return elapsed <= hours * 3600


# ============================================================
# Translation (Free APIs, no keys needed)
# ============================================================
def translate_en_to_zh(text):
    """Translate English text to Chinese using free translation APIs."""
    if not text or len(text) < 3 or is_chinese(text):
        return text

    # Method 1: Google Translate (unofficial endpoint)
    try:
        resp = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text[:800]},
            timeout=10,
            headers={"User-Agent": USER_AGENT}
        )
        if resp.status_code == 200:
            parts = resp.json()
            result = "".join(part[0] for part in parts[0] if part[0])
            if result and is_chinese(result):
                return result
    except Exception:
        pass

    time.sleep(0.3)

    # Method 2: MyMemory fallback
    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": "en|zh-CN"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("responseStatus") == 200:
                translated = data["responseData"]["translatedText"]
                if translated != text and is_chinese(translated):
                    return translated
    except Exception:
        pass

    return text


# ============================================================
# RSS Feed Fetching
# ============================================================
def fetch_feed(feed_info, hours):
    """Fetch and filter entries from a single RSS feed."""
    try:
        d = feedparser.parse(feed_info["url"])
        if not d.entries:
            return []

        keywords = [k.lower() for k in feed_info["keywords"]]
        lang = feed_info["lang"]
        results = []

        for entry in d.entries[:25]:
            if not time_within(entry, hours):
                continue

            title = clean_html(entry.get("title", ""))
            summary = clean_html(entry.get("summary", "") or entry.get("description", ""))

            if not title or len(title) < 5:
                continue

            # Keyword matching (title + summary)
            text_to_match = (title + " " + summary).lower()
            if not any(kw in text_to_match for kw in keywords):
                continue

            # Parse time
            dt = parse_pub_time(entry)
            time_str = format_time(dt)

            # Translate English content to Chinese
            if lang == "en":
                title = translate_en_to_zh(title)
                time.sleep(0.2)
                if summary:
                    summary = translate_en_to_zh(summary)
                    time.sleep(0.2)

            # Remove title repetition from summary
            if summary and len(title) > 8:
                title_prefix = title[:15]
                if title_prefix in summary:
                    summary = summary.replace(title_prefix, '', 1).strip()
                    summary = re.sub(r'^[\s\-_|，,：:]+', '', summary).strip()

            results.append({
                "title": title,
                "source": feed_info["name"],
                "time": time_str,
                "summary": truncate_text(summary, 180) if summary else "",
                "link": entry.get("link", ""),
            })

        return results
    except Exception as e:
        print(f"  ⚠ {feed_info['name']}: {e}")
        return []


def deduplicate(items):
    """Remove near-duplicate items by title similarity."""
    seen = []
    unique = []
    for item in items:
        norm = re.sub(r'[\s\-_|,，.。:：!！?？""\'\'（）()]+', '', item["title"].lower())[:30]
        if not any(norm in s or s in norm for s in seen):
            seen.append(norm)
            unique.append(item)
    return unique


def fetch_all_news(report_type):
    """Fetch and organize news for the given report type."""
    config = REPORTS[report_type]
    feeds = TESLA_FEEDS if report_type in ("morning", "evening") else NEV_FEEDS
    hours = config["hours"]

    print(f"[1/3] 正在采集新闻（最近 {hours} 小时）...")

    all_items = []
    for feed in feeds:
        items = fetch_feed(feed, hours)
        print(f"  {feed['name']}: {len(items)} 条")
        all_items.extend(items)

    all_items = deduplicate(all_items)

    # Separate Chinese and English (translated) items
    zh_items = [i for i in all_items if is_chinese(i["title"])]
    en_items = [i for i in all_items if not is_chinese(i["title"])]

    # Build sections
    sections = []
    if report_type in ("morning", "evening"):
        if zh_items:
            sections.append({"name": "🇨🇳 国内动态", "news": zh_items[:10]})
        if en_items:
            sections.append({"name": "🌍 海外动态", "news": en_items[:5]})
    else:
        if zh_items:
            sections.append({"name": "🚗 新能源汽车资讯", "news": zh_items[:12]})
        if en_items:
            sections.append({"name": "🌍 海外动态", "news": en_items[:5]})

    total = sum(len(s["news"]) for s in sections)
    print(f"  共 {total} 条")
    return {"sections": sections, "total": total}


# ============================================================
# Push to WeChat (Server酱) - Markdown
# ============================================================
def push_wechat(data, report_config):
    print("[2/3] 正在推送微信...")

    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    lines = [
        f"## {report_config['emoji']} {report_config['title']}",
        f"> {now.month}月{now.day}日 {weekday}  ·  共{data['total']}条",
        "",
    ]

    for section in data["sections"]:
        lines.append(f"### {section['name']}")
        lines.append("")
        for item in section["news"]:
            # Title as hidden clickable link
            if item.get("link"):
                lines.append(f"**[{item['title']}]({item['link']})**")
            else:
                lines.append(f"**{item['title']}**")
            # Source + time in subtle format
            lines.append(f"_{item['source']}  ·  {item['time']}_")
            # Summary in blockquote
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
                "title": f"{report_config['emoji']} {report_config['title']}（{now.month}月{now.day}日）",
                "desp": content
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
# Push to Email (iCloud) - HTML
# ============================================================
def push_email(data, report_config):
    print("[3/3] 正在发送邮件...")

    now = datetime.now(BEIJING)
    weekday = WEEKDAYS[now.weekday()]

    cards = ""

    for section in data["sections"]:
        cards += f'''
        <div style="border-left:4px solid #e82127;padding:6px 0 6px 14px;margin:22px 0 14px;">
            <span style="color:#e82127;font-size:16px;font-weight:700;">{section["name"]}</span>
        </div>'''

        for item in section["news"]:
            # Title: hidden link (text color matches, no underline)
            if item.get("link"):
                title_html = f'<a href="{item["link"]}" style="color:#1a1a1a;text-decoration:none;">{item["title"]}</a>'
            else:
                title_html = item["title"]

            summary_html = ""
            if item.get("summary"):
                summary_html = f'''
            <div style="color:#666;font-size:13px;line-height:1.75;margin-top:8px;">
                {item["summary"]}
            </div>'''

            cards += f'''
        <div style="padding:14px 16px;background:#fafafa;border-radius:8px;margin-bottom:10px;border-left:3px solid #e8e8e8;">
            <div style="font-weight:700;color:#1a1a1a;font-size:15px;line-height:1.55;">{title_html}</div>
            <div style="margin-top:6px;">
                <span style="display:inline-block;background:#f0f0f0;color:#888;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:500;">{item["source"]}</span>
                <span style="color:#bbb;font-size:12px;margin-left:8px;">{item["time"]}</span>
            </div>{summary_html}
        </div>'''

    html = f'''
    <div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;">
        <div style="background:linear-gradient(135deg,#e82127 0%,#c41e24 100%);padding:28px 32px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">{report_config["emoji"]} {report_config["title"]}</h1>
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
        msg["Subject"] = f"{report_config['emoji']} {report_config['title']}（{now.month}月{now.day}日）"
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
        print("  ⚠ 跳过邮件发送（无iCloud凭据）")

    return html


# ============================================================
# Main
# ============================================================
def main():
    config = REPORTS[REPORT_TYPE]
    now = datetime.now(BEIJING)

    print(f"\n{'='*50}")
    print(f"  {config['emoji']} {config['title']}")
    print(f"  {now.strftime('%Y-%m-%d %H:%M')} (北京时间)")
    print(f"{'='*50}\n")

    data = fetch_all_news(REPORT_TYPE)

    if data["total"] == 0:
        print("未采集到新闻，跳过推送。")
        return

    push_wechat(data, config)
    push_email(data, config)

    print(f"\n{'='*50}")
    print("  全部完成！")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
