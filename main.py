#!/usr/bin/env python3
"""
Discord市況レポートBot
毎朝、日本株・米国株・為替・商品の市況とAI分析をDiscordに投稿する
"""

import os
import sys
from datetime import datetime
from typing import Optional, Dict, List

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import requests
import yfinance as yf
from openai import OpenAI


JST = ZoneInfo("Asia/Tokyo")

MARKET_DATA = {
    "japan": {
        "title": "日本市場",
        "symbols": {
            "^N225": "日経平均",
            "1306.T": "TOPIX連動",
        }
    },
    "us": {
        "title": "米国市場（前日終値）",
        "symbols": {
            "^GSPC": "S&P 500",
            "^IXIC": "NASDAQ",
            "^DJI": "ダウ平均",
        }
    },
    "fx": {
        "title": "為替",
        "symbols": {
            "USDJPY=X": "ドル円",
        }
    },
    "indicators": {
        "title": "指標・商品",
        "symbols": {
            "^VIX": "VIX",
            "GC=F": "金",
            "CL=F": "原油",
            "^SOX": "SOX",
        }
    },
}


def is_weekday() -> bool:
    """土日かどうかをチェック"""
    now = datetime.now(JST)
    return now.weekday() < 5


def get_stock_data(symbol: str) -> Optional[dict]:
    """指定シンボルの株価データを取得"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        
        if len(hist) < 1:
            return None
        
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else latest
        
        price = latest["Close"]
        prev_close = prev["Close"]
        change = price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close != 0 else 0
        
        return {
            "price": price,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}", file=sys.stderr)
        return None


def fetch_all_market_data() -> Dict[str, Dict[str, dict]]:
    """全市場データを取得"""
    results = {}
    
    for category, config in MARKET_DATA.items():
        results[category] = {
            "title": config["title"],
            "data": {}
        }
        for symbol, name in config["symbols"].items():
            data = get_stock_data(symbol)
            if data:
                results[category]["data"][name] = data
    
    return results


def format_market_section(title: str, data: Dict[str, dict]) -> str:
    """市場セクションをフォーマット"""
    if not data:
        return ""
    
    lines = [f"**【{title}】**"]
    
    for name, values in data.items():
        sign = "+" if values["change"] >= 0 else ""
        
        if "ドル円" in name:
            price_fmt = f"{values['price']:.2f}"
        elif values["price"] >= 1000:
            price_fmt = f"{values['price']:,.0f}"
        else:
            price_fmt = f"{values['price']:,.2f}"
        
        lines.append(f"  {name}: {price_fmt} ({sign}{values['change_pct']:.2f}%)")
    
    return "\n".join(lines)


def generate_ai_analysis(market_data: Dict[str, Dict[str, dict]], openai_key: str) -> str:
    """OpenAI GPTで市況分析を生成"""
    try:
        client = OpenAI(api_key=openai_key)
        
        data_summary = []
        for category, info in market_data.items():
            for name, values in info["data"].items():
                sign = "+" if values["change_pct"] >= 0 else ""
                data_summary.append(f"{name}: {sign}{values['change_pct']:.2f}%")
        
        data_text = "\n".join(data_summary)
        
        prompt = f"""あなたは専業投資家として、以下の市況データを分析し、簡潔な一言コメントを5行程度で作成してください。

【本日の市況データ】
{data_text}

【出力ルール】
- 専業投資家・トレーダー目線で分析
- 各市場の動向と相関関係を簡潔に解説
- 本日注目すべきポイントを1〜2点挙げる
- 絵文字は使わない
- 5行以内で簡潔に"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは経験豊富な専業投資家です。市況を簡潔かつ的確に分析します。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Error generating AI analysis: {e}", file=sys.stderr)
        return "AI分析を生成できませんでした。"


def format_message(market_data: Dict[str, Dict[str, dict]], ai_analysis: str) -> str:
    """Discord投稿用のメッセージをフォーマット"""
    now = datetime.now(JST)
    date_str = now.strftime("%Y/%m/%d %H:%M")
    
    lines = [f"📈 **本日の市況レポート**（{date_str} JST）\n"]
    
    for category in ["japan", "us", "fx", "indicators"]:
        if category in market_data:
            section = format_market_section(
                market_data[category]["title"],
                market_data[category]["data"]
            )
            if section:
                lines.append(section)
                lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 **専業投資家の視点**\n")
    lines.append(ai_analysis)
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    
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
