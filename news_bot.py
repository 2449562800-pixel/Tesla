import os
import sys
import json
import smtplib
import re
import feedparser
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from html import unescape

# ============================================================
# CONFIG - No API keys needed!
# ============================================================
SCT_SENDKEY = os.environ.get("SCT_SENDKEY", "")
ICLOUD_USER = os.environ.get("ICLOUD_USER", "")
ICLOUD_PASS = os.environ.get("ICLOUD_PASS", "")

REPORT_TYPE = sys.argv[1] if len(sys.argv) > 1 else "morning"

BEIJING = timezone(timedelta(hours=8))

REPORTS = {
    "morning": {"title": "特斯拉晨报", "emoji": "🚗"},
    "noon": {"title": "新能源午报", "emoji": "⚡"},
    "evening": {"title": "特斯拉晚报", "emoji": "🌙"},
}

# ============================================================
# RSS Sources
# ============================================================
TESLA_FEEDS = [
    {"name": "Electrek", "url": "https://electrek.co/feed/", "lang": "en", "keywords": ["tesla", "model y", "model 3", "model s", "model x", "cybertruck", "fsd", "autopilot", "musk", "elon"]},
    {"name": "TeslaRati", "url": "https://www.teslarati.com/feed/", "lang": "en", "keywords": ["tesla", "model y", "model 3", "fsd", "autopilot", "musk"]},
    {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh", "keywords": ["特斯拉", "Tesla", "马斯克", "Musk", "FSD"]},
    {"name": "InsideEVs", "url": "https://insideevs.com/rssfeeds/all.xml", "lang": "en", "keywords": ["tesla", "model y", "model 3", "fsd", "autopilot", "musk"]},
]

NEV_FEEDS = [
    {"name": "36氪汽车", "url": "https://36kr.com/feed", "lang": "zh", "keywords": ["新能源汽车", "问界", "理想", "小鹏", "蔚来", "小米汽车", "比亚迪", "极氪", "智驾", "NOA", "智己", "特斯拉"]},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "lang": "zh", "keywords": ["汽车", "新能源", "问界", "理想", "小鹏", "蔚来", "小米", "比亚迪", "智驾", "特斯拉"]},
    {"name": "InsideEVs", "url": "https://insideevs.com/rssfeeds/all.xml", "lang": "en", "keywords": ["BYD", "NIO", "XPeng", "Li Auto", "Xiaomi", "Aito"]},
]


def clean_html(text):
    """Remove HTML tags and clean up text."""
    text = unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def strip_text(text, max_len=300):
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(' ', 1)[0] + "..."


def time_ago(entry, hours=24):
    """Check if entry was published within the given hours."""
    try:
        pub_time = entry.get("published_parsed") or entry.get("updated_parsed")
        if not pub_time:
            return True
        dt = datetime(*pub_time[:6], tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() <= hours * 3600
    except Exception:
        return True


def fetch_feed(feed_info, hours=24):
    """Fetch and filter RSS feed entries."""
    try:
        d = feedparser.parse(feed_info["url"])
        results = []
        keywords = [k.lower() for k in feed_info["keywords"]]
        lang = feed_info["lang"]

        for entry in d.entries[:30]:
            if not time_ago(entry, hours):
                continue

            title = clean_html(entry.get("title", ""))
            summary = clean_html(entry.get("summary", "") or entry.get("description", ""))

            if not title:
                continue

            # Keyword matching
            title_lower = title.lower()
            matched = any(kw in title_lower for kw in keywords)
            if not matched and summary:
                summary_lower = summary.lower()
                matched = any(kw in summary_lower for kw in keywords)
            if not matched:
                continue

            # Get date
            date_str = ""
            try:
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                if pub:
                    dt_bj = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(BEIJING)
                    date_str = f"{dt_bj.month}月{dt_bj.day}日"
            except Exception:
                date_str = datetime.now(BEIJING).strftime("%-m月%-d日")

            results.append({
                "title": title,
                "source": feed_info["name"],
                "date": date_str,
                "summary": strip_text(summary, 250) if summary else "",
                "link": entry.get("link", ""),
            })

        return results
    except Exception as e:
        print(f"  Warning: Failed to fetch {feed_info['name']}: {e}")
        return []


def deduplicate(items):
    """Remove duplicate news by similar title."""
    seen = []
    unique = []
    for item in items:
        title = item["title"].lower()[:40]
        if not any(title in s for s in seen):
            seen.append(title)
            unique.append(item)
    return unique


def fetch_all_news(report_type):
    """Fetch news from all relevant RSS feeds."""
    if report_type in ("morning", "evening"):
        feeds = TESLA_FEEDS
        hours = 24 if report_type == "morning" else 12
        label = "Tesla & EV News"
    else:
        feeds = NEV_FEEDS
        hours = 6
        label = "NEV News"

    print(f"[1/3] Fetching {label} from RSS (last {hours}h)...")

    all_items = []
    for feed in feeds:
        items = fetch_feed(feed, hours)
        print(f"  {feed['name']}: {len(items)} items")
        all_items.extend(items)

    # Deduplicate and limit
    all_items = deduplicate(all_items)
    all_items = all_items[:15]

    # Group by source for sections
    if report_type in ("morning", "evening"):
        en_items = [i for i in all_items if i["source"] in ("Electrek", "TeslaRati", "InsideEVs")]
        zh_items = [i for i in all_items if i["source"] not in ("Electrek", "TeslaRati", "InsideEVs")]

        sections = []
        if en_items:
            sections.append({"name": "🇺🇸 国际动态", "news": en_items[:8]})
        if zh_items:
            sections.append({"name": "🇨🇳 国内动态", "news": zh_items[:8]})
    else:
        sections = [{"name": "🚗 新能源汽车资讯", "news": all_items[:12]}]

    data = {"sections": sections, "total": sum(len(s["news"]) for s in sections)}
    print(f"  Total: {data['total']} items across {len(sections)} sections")
    return data


# ============================================================
# Push to WeChat (Server Chan) - Markdown
# ============================================================
def push_to_wechat(data, report_config):
    print("[2/3] Pushing to WeChat via Server Chan...")

    now = datetime.now(BEIJING)
    md_lines = [
        f"# {report_config['emoji']} {report_config['title']}（{now.month}月{now.day}日）",
        "---",
    ]

    for section in data.get("sections", []):
        md_lines.append(f"## {section['name']}")
        for i, item in enumerate(section.get("news", []), 1):
            md_lines.append(f"**{i}. {item['title']}**")
            md_lines.append(f"来源：{item['source']} · {item['date']}")
            if item.get("summary"):
                md_lines.append(f"> {item['summary']}")
            if item.get("link"):
                md_lines.append(f"[阅读原文]({item['link']})")
            md_lines.append("")
        md_lines.append("---")

    md_lines.append(f"> 📊 共{data.get('total', 0)}条 | RSS自动采集")

    markdown_content = "\n".join(md_lines)

    if SCT_SENDKEY:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SCT_SENDKEY}.send",
            json={"title": f"{report_config['emoji']} {report_config['title']}", "desp": markdown_content},
            timeout=30,
        )
        result = resp.json()
        if result.get("code") == 0:
            print("  ✓ WeChat push SUCCESS")
        else:
            print(f"  ✗ WeChat push FAILED: {result}")
    else:
        print("  ⊘ WeChat push SKIPPED (no SCT_SENDKEY)")

    return markdown_content


# ============================================================
# Push to Email (iCloud) - HTML
# ============================================================
def push_to_email(data, report_config):
    print("[3/3] Pushing to Email via iCloud SMTP...")

    now = datetime.now(BEIJING)
    cards_html = ""

    for section in data.get("sections", []):
        cards_html += f'<div style="color:#e82127;font-size:17px;font-weight:bold;border-left:4px solid #e82127;padding-left:10px;margin-top:20px;margin-bottom:10px;">{section["name"]}</div>'
        for item in section.get("news", []):
            cards_html += f"""
            <div style="padding:14px 16px;background:#f8f8f8;border-radius:8px;margin-bottom:10px;">
                <div style="font-weight:bold;color:#333;font-size:15px;">{item["title"]}</div>
                <div style="color:#999;font-size:12px;margin-top:4px;">{item["source"]} · {item["date"]}</div>
                <div style="color:#555;font-size:14px;line-height:1.7;margin-top:6px;">{item.get("summary", "")}</div>
            </div>"""

    html_body = f"""
    <div style="max-width:620px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <div style="background:linear-gradient(135deg,#e82127,#c41e24);padding:28px 32px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:24px;">{report_config['emoji']} {report_config['title']}</h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,0.8);font-size:14px;">{now.year}年{now.month}月{now.day}日</p>
        </div>
        <div style="padding:24px 32px;">
            {cards_html}
            <div style="text-align:center;color:#ccc;font-size:12px;margin-top:20px;padding-top:16px;border-top:1px solid #eee;">
                📊 共{data.get('total', 0)}条 · RSS自动采集
            </div>
        </div>
    </div>"""

    if ICLOUD_USER and ICLOUD_PASS:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{report_config['emoji']} {report_config['title']}（{now.month}月{now.day}日）"
        msg["From"] = ICLOUD_USER
        msg["To"] = ICLOUD_USER
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP("smtp.mail.me.com", 587) as server:
                server.starttls()
                server.login(ICLOUD_USER, ICLOUD_PASS)
                server.sendmail(ICLOUD_USER, ICLOUD_USER, msg.as_string())
            print("  ✓ Email push SUCCESS")
        except Exception as e:
            print(f"  ✗ Email push FAILED: {e}")
    else:
        print("  ⊘ Email push SKIPPED (no ICLOUD creds)")

    return html_body


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"\n{'='*50}")
    print(f"  {REPORTS[REPORT_TYPE]['title']} - Cloud RSS Bot")
    print(f"  {datetime.now(BEIJING).strftime('%Y-%m-%d %H:%M:%S')} (Beijing)")
    print(f"{'='*50}\n")

    report_config = REPORTS[REPORT_TYPE]

    data = fetch_all_news(REPORT_TYPE)

    if data["total"] == 0:
        print("No news found. Skipping push.")
        return

    push_to_wechat(data, report_config)
    push_to_email(data, report_config)

    print(f"\n{'='*50}")
    print("  All done!")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
