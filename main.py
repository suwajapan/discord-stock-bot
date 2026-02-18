#!/usr/bin/env python3
"""
Discord市況レポートBot
毎朝、日本株・米国株・為替の市況とAI分析をDiscordに投稿する
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import requests
import yfinance as yf
from openai import OpenAI


JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")

MARKET_DATA = {
    "japan": {
        "title": "日本市場",
        "emoji": "🇯🇵",
        "symbols": {
            "^N225": "日経平均",
            "1306.T": "TOPIX",
        }
    },
    "us": {
        "title": "米国市場（前日）",
        "emoji": "🇺🇸",
        "symbols": {
            "^GSPC": "S&P 500",
            "^IXIC": "NASDAQ",
            "^DJI": "ダウ",
        }
    },
    "fx": {
        "title": "為替",
        "emoji": "💱",
        "symbols": {
            "USDJPY=X": "ドル円",
        }
    },
}


def is_weekday() -> bool:
    """土日かどうかをチェック"""
    now = datetime.now(JST)
    return now.weekday() < 5


def get_stock_data(symbol: str) -> Optional[dict]:
    """指定シンボルの株価データを取得（複数回リトライ）"""
    for attempt in range(3):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", interval="1d")
            
            if hist.empty or len(hist) < 2:
                print(f"Warning: Insufficient data for {symbol}, attempt {attempt + 1}", file=sys.stderr)
                continue
            
            hist = hist.dropna()
            if len(hist) < 2:
                continue
            
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            
            price = float(latest["Close"])
            prev_close = float(prev["Close"])
            
            if price <= 0 or prev_close <= 0:
                print(f"Warning: Invalid price for {symbol}", file=sys.stderr)
                continue
            
            change = price - prev_close
            change_pct = (change / prev_close) * 100
            
            latest_date = hist.index[-1]
            if hasattr(latest_date, 'tz_localize'):
                latest_date = latest_date.tz_localize(UTC)
            
            return {
                "price": price,
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
                "date": latest_date,
                "verified": True,
            }
        except Exception as e:
            print(f"Error fetching {symbol} (attempt {attempt + 1}): {e}", file=sys.stderr)
            continue
    
    return None


def fetch_all_market_data() -> Dict[str, Dict]:
    """全市場データを取得"""
    results = {}
    errors = []
    
    for category, config in MARKET_DATA.items():
        results[category] = {
            "title": config["title"],
            "emoji": config["emoji"],
            "data": {}
        }
        for symbol, name in config["symbols"].items():
            data = get_stock_data(symbol)
            if data and data.get("verified"):
                results[category]["data"][name] = data
            else:
                errors.append(f"{name}({symbol})")
    
    if errors:
        print(f"Failed to fetch: {', '.join(errors)}", file=sys.stderr)
    
    return results


def format_price(price: float, name: str) -> str:
    """価格をフォーマット"""
    if "ドル円" in name:
        return f"{price:.2f} 円"
    elif price >= 10000:
        return f"{price:,.0f}"
    elif price >= 100:
        return f"{price:,.0f}"
    else:
        return f"{price:,.2f}"


def get_trend_emoji(change_pct: float) -> str:
    """変動率に応じた絵文字"""
    if change_pct >= 1.0:
        return "🚀"
    elif change_pct >= 0.3:
        return "📈"
    elif change_pct > -0.3:
        return "➡️"
    elif change_pct > -1.0:
        return "📉"
    else:
        return "⚠️"


def generate_ai_analysis(market_data: Dict[str, Dict], openai_key: str) -> str:
    """OpenAI GPTで市況分析を生成"""
    try:
        client = OpenAI(api_key=openai_key)
        
        data_lines = []
        for category, info in market_data.items():
            for name, values in info["data"].items():
                sign = "+" if values["change_pct"] >= 0 else ""
                data_lines.append(f"- {name}: {values['price']:.2f} ({sign}{values['change_pct']:.2f}%)")
        
        data_text = "\n".join(data_lines)
        now = datetime.now(JST)
        weekday_jp = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
        
        prompt = f"""あなたは経験豊富な専業投資家です。以下の市況データを分析し、今日のポイントを作成してください。

【本日】{now.strftime('%Y年%m月%d日')}（{weekday_jp}）

【市況データ】
{data_text}

【出力ルール】
1. 3〜4行で簡潔にまとめる
2. 数値データに基づいた客観的な分析のみ
3. 「〜が予想されます」「〜かもしれません」など推測は控えめに
4. 初心者にもわかりやすい表現を使う
5. 絵文字は使わない
6. 最後に「🎯 注目：」で今日注目すべき1点を挙げる

【禁止事項】
- 具体的な銘柄の推奨
- 売買の指示
- 根拠のない予測"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは日本株投資コミュニティ向けに毎朝の市況解説を担当する専業投資家です。初心者から上級者まで参考になる、正確で簡潔な分析を提供します。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.5,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Error generating AI analysis: {e}", file=sys.stderr)
        return "本日の分析を生成できませんでした。"


def format_message(market_data: Dict[str, Dict], ai_analysis: str) -> str:
    """Discord投稿用のメッセージをフォーマット"""
    now = datetime.now(JST)
    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
    date_str = now.strftime(f"%m月%d日（{weekday_jp}）")
    
    lines = [
        "☀️ おはようございます！",
        f"📊 **{date_str}の市況レポート**",
        "",
        "━━━━━━━━━━━━━━━━",
    ]
    
    for category in ["japan", "us", "fx"]:
        if category not in market_data or not market_data[category]["data"]:
            continue
        
        info = market_data[category]
        lines.append("")
        lines.append(f"{info['emoji']} **{info['title']}**")
        
        for name, values in info["data"].items():
            price_str = format_price(values["price"], name)
            sign = "+" if values["change_pct"] >= 0 else ""
            trend = get_trend_emoji(values["change_pct"])
            lines.append(f"┃ {name}　{price_str}（{sign}{values['change_pct']:.2f}%）{trend}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("💡 **今日のポイント**")
    lines.append("")
    lines.append(ai_analysis)
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("良い一日を！🍀")
    
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
    if not is_weekday():
        print("Today is weekend. Skipping.")
        return
    
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Error: DISCORD_WEBHOOK_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("Error: OPENAI_API_KEY environment variable is not set", file=sys.stderr)
        sys.exit(1)
    
    print("Fetching market data...")
    market_data = fetch_all_market_data()
    
    total_items = sum(len(info["data"]) for info in market_data.values())
    if total_items == 0:
        print("Error: No market data could be fetched", file=sys.stderr)
        sys.exit(1)
    
    print(f"Successfully fetched {total_items} items")
    
    print("Generating AI analysis...")
    ai_analysis = generate_ai_analysis(market_data, openai_key)
    
    message = format_message(market_data, ai_analysis)
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
