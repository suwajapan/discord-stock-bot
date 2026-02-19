#!/usr/bin/env python3
"""
Discord日本株ニュースBot
毎昼、日本株関連のニュースをピックアップして要約し、Discordに投稿する
"""

import os
import sys
import re
from datetime import datetime
from typing import List, Dict

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import requests
import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI


JST = ZoneInfo("Asia/Tokyo")


def fetch_google_news() -> List[Dict]:
    """Google Newsから日本株関連ニュースを取得"""
    news_items = []
    
    queries = [
        "日本株",
        "日経平均",
        "東証",
    ]
    
    for query in queries:
        try:
            url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                source = entry.get("source", {}).get("title", "")
                
                if title and link:
                    news_items.append({
                        "title": title,
                        "link": link,
                        "source": source,
                        "origin": "Google News"
                    })
        except Exception as e:
            print(f"Error fetching Google News for '{query}': {e}", file=sys.stderr)
    
    return news_items


def fetch_yahoo_finance_news() -> List[Dict]:
    """Yahoo ファイナンスから日本株ニュースを取得"""
    news_items = []
    
    try:
        url = "https://finance.yahoo.co.jp/news/list/stock"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        articles = soup.select("a[href*='/news/detail/']")[:10]
        
        for article in articles:
            title = article.get_text(strip=True)
            link = article.get("href", "")
            
            if not link.startswith("http"):
                link = "https://finance.yahoo.co.jp" + link
            
            if title and len(title) > 10:
                news_items.append({
                    "title": title,
                    "link": link,
                    "source": "Yahoo ファイナンス",
                    "origin": "Yahoo Finance"
                })
    except Exception as e:
        print(f"Error fetching Yahoo Finance news: {e}", file=sys.stderr)
    
    return news_items


def deduplicate_news(news_items: List[Dict]) -> List[Dict]:
    """重複ニュースを除去"""
    seen_titles = set()
    unique_items = []
    
    for item in news_items:
        title_normalized = re.sub(r'\s+', '', item["title"])[:30]
        
        if title_normalized not in seen_titles:
            seen_titles.add(title_normalized)
            unique_items.append(item)
    
    return unique_items


def summarize_news_with_ai(news_items: List[Dict], openai_key: str) -> str:
    """AIでニュースを要約・分析"""
    try:
        client = OpenAI(api_key=openai_key)
        
        news_text = "\n".join([
            f"- {item['title']}（{item['source']}）"
            for item in news_items[:15]
        ])
        
        now = datetime.now(JST)
        weekday_jp = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
        
        prompt = f"""あなたは日本株投資コミュニティ向けのニュースキュレーターです。
以下の本日のニュース一覧から、投資家にとって重要なニュースを5〜7件ピックアップし、
初心者にもわかりやすく要約してください。

【本日】{now.strftime('%Y年%m月%d日')}（{weekday_jp}）

【ニュース一覧】
{news_text}

【出力ルール】
1. 重要度の高い順に5〜7件を選定
2. 各ニュースは1〜2行で簡潔に要約
3. なぜ投資家にとって重要かを簡潔に補足
4. 絵文字を適度に使用して読みやすく
5. 最後に「📌 本日の注目ポイント」として1〜2行でまとめ

【出力フォーマット例】
1️⃣ **〇〇会社が△△を発表**
決算好調で株価上昇の材料に。半導体関連に注目。

2️⃣ **日銀が□□について言及**
金融政策の変更示唆。銀行株に影響か。

（続く...）

📌 **本日の注目ポイント**
〜〜〜"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは日本株投資コミュニティ向けに毎日のニュースをキュレーションする専門家です。初心者から上級者まで役立つ、正確で簡潔な要約を提供します。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.5,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Error summarizing news: {e}", file=sys.stderr)
        return "ニュースの要約を生成できませんでした。"


def format_message(summary: str) -> str:
    """Discord投稿用のメッセージをフォーマット"""
    now = datetime.now(JST)
    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
    date_str = now.strftime(f"%m月%d日（{weekday_jp}）")
    
    lines = [
        "📰 **日本株ニュースまとめ**",
        f"🗓️ {date_str} 12:00 配信",
        "",
        "━━━━━━━━━━━━━━━━",
        "",
        summary,
        "",
        "━━━━━━━━━━━━━━━━",
        "午後のトレードにお役立てください！📊",
    ]
    
    return "\n".join(lines)


def send_to_discord(message: str, webhook_url: str) -> bool:
    """DiscordのWebhookにメッセージを送信"""
    payload = {"content": message}
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error sending to Discord: {e}", file=sys.stderr)
        return False


def main():
    webhook_url = os.environ.get("DISCORD_NEWS_WEBHOOK_URL")
    if not webhook_url:
        print("Error: DISCORD_NEWS_WEBHOOK_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("Error: OPENAI_API_KEY environment variable is not set", file=sys.stderr)
        sys.exit(1)
    
    print("Fetching news from Google News...")
    google_news = fetch_google_news()
    print(f"  Found {len(google_news)} articles")
    
    print("Fetching news from Yahoo Finance...")
    yahoo_news = fetch_yahoo_finance_news()
    print(f"  Found {len(yahoo_news)} articles")
    
    all_news = google_news + yahoo_news
    unique_news = deduplicate_news(all_news)
    print(f"Total unique articles: {len(unique_news)}")
    
    if not unique_news:
        print("Error: No news articles found", file=sys.stderr)
        sys.exit(1)
    
    print("Summarizing news with AI...")
    summary = summarize_news_with_ai(unique_news, openai_key)
    
    message = format_message(summary)
    print("Message to send:")
    print(message)
    print("-" * 40)
    
    if send_to_discord(message, webhook_url):
        print("Successfully sent to Discord!")
    else:
        print("Failed to send to Discord.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
