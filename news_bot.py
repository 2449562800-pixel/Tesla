import os
import sys
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from openai import OpenAI

# ============================================================
# CONFIG
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SCT_SENDKEY = os.environ.get("SCT_SENDKEY")
ICLOUD_USER = os.environ.get("ICLOUD_USER")
ICLOUD_PASS = os.environ.get("ICLOUD_PASS")

REPORT_TYPE = sys.argv[1] if len(sys.argv) > 1 else "morning"

REPORTS = {
    "morning": {
        "title": "特斯拉晨报",
        "emoji": "🚗",
        "prompt": (
            "你是一个特斯拉新闻编辑。请搜索并整理过去12小时内（从昨晚到今早）的特斯拉相关重要新闻。\n"
            "搜索来源包括：Electrek、Tesla官方、马斯克X(Twitter)动态、36氪、虎嗅等。\n"
            "重点关注：FSD自动驾驶进展、特斯拉新车/产品动态、中国市场消息、股价重要变动、马斯克言论。\n"
            "请用中文整理，每条新闻包含：标题、来源、日期、简短摘要。\n"
            "按板块分类：FSD动态、产品/市场、中国动态、其他重要消息。\n"
            "每个板块2-4条新闻，总共8-12条。如果没有某板块的新闻就省略该板块。"
        ),
    },
    "noon": {
        "title": "新能源午报",
        "emoji": "⚡",
        "prompt": (
            "你是一个中国新能源汽车新闻编辑。请搜索并整理过去4-6小时内（今上午）的中国新能源车相关重要新闻。\n"
            "重点关注品牌：AITO问界、理想、小鹏、小米、蔚来、比亚迪、极氪、智己等。\n"
            "关注领域：智驾更新（NOA/城市NOA）、新车发布/上市、销量数据、KOL/媒体评测观点、政策动态。\n"
            "搜索来源：36氪、虎嗅、汽车之家、懂车帝、各品牌官方微博/公众号。\n"
            "请用中文整理，每条新闻包含：标题、来源、日期、简短摘要。\n"
            "按板块分类：智驾动态、新车/产品、行业/政策、KOL观点。\n"
            "每个板块2-4条新闻，总共8-12条。如果没有某板块的新闻就省略该板块。"
        ),
    },
    "evening": {
        "title": "特斯拉晚报",
        "emoji": "🌙",
        "prompt": (
            "你是一个特斯拉新闻编辑。请搜索并整理今天白天（从早上到现在）的特斯拉相关重要新闻。\n"
            "搜索来源包括：Electrek、Tesla官方、马斯克X(Twitter)动态、36氪、虎嗅等。\n"
            "重点关注：FSD自动驾驶进展、特斯拉新车/产品动态、中国市场消息、股价重要变动、马斯克言论。\n"
            "请用中文整理，每条新闻包含：标题、来源、日期、简短摘要。\n"
            "按板块分类：FSD动态、产品/市场、中国动态、其他重要消息。\n"
            "每个板块2-4条新闻，总共8-12条。如果没有某板块的新闻就省略该板块。"
        ),
    },
}

# ============================================================
# STEP 1: Fetch news via OpenAI (with web search)
# ============================================================
def fetch_news(report_config):
    print(f"[1/3] Fetching news for {report_config['title']}...")
    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": report_config["prompt"],
            }
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for the latest news",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            }
                        },
                        "required": ["query"],
                    },
                },
            }
        ],
        tool_choice="auto",
    )

    # Check if model wants to call web_search
    message = response.choices[0].message
    if message.tool_calls:
        # Execute web searches
        news_results = []
        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            print(f"  Searching: {args['query']}")

            search_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": args["query"]}
                ],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"}
                            },
                            "required": ["query"],
                        },
                    }
                }],
                tool_choice={"type": "function", "function": {"name": "web_search"}},
            )

            search_message = search_response.choices[0].message
            if search_message.tool_calls:
                for sc in search_message.tool_calls:
                    result = json.loads(sc.function.arguments)
                    news_results.append(result.get("query", ""))
                    print(f"  Found: {result.get('query', '')}")

        # Now ask model to compile the news
        compile_prompt = (
            report_config["prompt"] + "\n\n"
            "以下是我搜索到的相关关键词和来源，请根据这些信息整理新闻：\n"
            + "\n".join(f"- {r}" for r in news_results) + "\n\n"
            "请用以下JSON格式返回（不要包含markdown代码块）：\n"
            '{"sections": [{"name": "板块名称", "news": [{"title": "标题", "source": "来源", "date": "M月D日", "summary": "摘要"}]}], "total": N}'
        )

        compile_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": compile_prompt}],
            temperature=0.3,
        )
        content = compile_response.choices[0].message.content.strip()
    else:
        content = message.content.strip()

    # Parse JSON from response
    try:
        # Remove markdown code blocks if present
        clean = content
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        data = json.loads(clean)
    except json.JSONDecodeError:
        print(f"  Warning: Could not parse JSON, using raw content")
        print(f"  Raw: {content[:200]}...")
        data = {
            "sections": [{"name": "新闻", "news": [{"title": "今日新闻汇总", "source": "AI", "date": datetime.now().strftime("%-m月%-d日"), "summary": content[:500]}]}],
            "total": 1,
        }

    print(f"  Found {data.get('total', '?')} news items across {len(data.get('sections', []))} sections")
    return data


# ============================================================
# STEP 2: Format and push to Server Chan (WeChat)
# ============================================================
def push_to_wechat(data, report_config):
    print("[2/3] Pushing to WeChat via Server Chan...")

    now = datetime.now()
    md_lines = [
        f"# {report_config['emoji']} {report_config['title']}（{now.month}月{now.day}日）",
        "---",
    ]

    for section in data.get("sections", []):
        md_lines.append(f"## {section['name']}")
        for i, item in enumerate(section.get("news", []), 1):
            md_lines.append(f"**{i}. {item['title']}**")
            md_lines.append(f"来源：{item['source']} · {item['date']}")
            md_lines.append(f"> {item['summary']}")
            md_lines.append("")
        md_lines.append("---")

    md_lines.append(f"> 📊 共{data.get('total', '?')}条 | AI自动采集翻译")

    markdown_content = "\n".join(md_lines)

    resp = requests.post(
        "https://sctapi.ftqq.com/SCT351050TfLhDDxCIsH2WUicG3fAelrR3.send",
        json={"title": f"{report_config['emoji']} {report_config['title']}", "desp": markdown_content},
        timeout=30,
    )
    result = resp.json()
    if result.get("code") == 0:
        print(f"  ✓ WeChat push SUCCESS")
    else:
        print(f"  ✗ WeChat push FAILED: {result}")
    return markdown_content


# ============================================================
# STEP 3: Format and push to Email (iCloud HTML)
# ============================================================
def push_to_email(data, report_config):
    print("[3/3] Pushing to Email via iCloud SMTP...")

    now = datetime.now()
    cards_html = ""

    for section in data.get("sections", []):
        cards_html += f'<div style="color:#e82127;font-size:17px;font-weight:bold;border-left:4px solid #e82127;padding-left:10px;margin-top:20px;margin-bottom:10px;">{section["name"]}</div>'
        for item in section.get("news", []):
            cards_html += f"""
            <div style="padding:14px 16px;background:#f8f8f8;border-radius:8px;margin-bottom:10px;">
                <div style="font-weight:bold;color:#333;font-size:15px;">{item["title"]}</div>
                <div style="color:#999;font-size:12px;margin-top:4px;">{item["source"]} · {item["date"]}</div>
                <div style="color:#555;font-size:14px;line-height:1.7;margin-top:6px;">{item["summary"]}</div>
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
                📊 共{data.get('total', '?')}条 · AI自动采集翻译
            </div>
        </div>
    </div>"""

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

    return html_body


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"\n{'='*50}")
    print(f"  {REPORTS[REPORT_TYPE]['title']} - Cloud Push Bot")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    report_config = REPORTS[REPORT_TYPE]

    # Step 1: Fetch news
    data = fetch_news(report_config)

    # Step 2: Push to WeChat
    push_to_wechat(data, report_config)

    # Step 3: Push to Email
    push_to_email(data, report_config)

    print(f"\n{'='*50}")
    print("  All done!")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
