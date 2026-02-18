#!/usr/bin/env python3
"""
Discord日本株市況Bot
毎朝、日経平均・TOPIXなどの指数をDiscordに投稿する
"""

import os
import sys
from datetime import datetime
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import requests
import yfinance as yf


INDICES = {
    "^N225": "日経平均",
    "1306.T": "TOPIX連動ETF",
}

JST = ZoneInfo("Asia/Tokyo")


def is_weekday() -> bool:
    """土日かどうかをチェック"""
    now = datetime.now(JST)
    return now.weekday() < 5


def get_stock_data(symbol: str) -> Optional[dict]:
    """指定シンボルの株価データを取得"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        
        if len(hist) < 1:
            return None
        
        today = hist.iloc[-1]
        prev_close = hist.iloc[-2]["Close"] if len(hist) >= 2 else today["Open"]
        
        return {
            "open": today["Open"],
            "close": today["Close"],
            "prev_close": prev_close,
            "change": today["Open"] - prev_close,
            "change_pct": ((today["Open"] - prev_close) / prev_close) * 100,
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}", file=sys.stderr)
        return None


def format_message() -> str:
    """Discord投稿用のメッセージをフォーマット"""
    now = datetime.now(JST)
    date_str = now.strftime("%Y/%m/%d")
    
    lines = [f"📈 **本日の日本株市況**（{date_str}）\n"]
    
    for symbol, name in INDICES.items():
        data = get_stock_data(symbol)
        
        if data is None:
            lines.append(f"**【{name}】**\n  データ取得エラー\n")
            continue
        
        sign = "+" if data["change"] >= 0 else ""
        
        lines.append(
            f"**【{name}】**\n"
            f"  始値: {data['open']:,.2f}\n"
            f"  前日終値: {data['prev_close']:,.2f}\n"
            f"  変動: {sign}{data['change']:,.2f} ({sign}{data['change_pct']:.2f}%)\n"
        )
    
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
    
    message = format_message()
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
