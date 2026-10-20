import json
import os
import time
import urllib.parse
import urllib.request

BASE = "https://api.india.delta.exchange"
SYMBOL = os.getenv("SYMBOL", "BTCUSD")
RESOLUTION = os.getenv("RESOLUTION", "5m")
MINUTES = {"1m": 60, "3m": 180, "5m": 300, "15m": 900,
           "30m": 1800, "1h": 3600}
TF = MINUTES[RESOLUTION]


def get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "crossover-alert/1.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())


def send_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": message
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode())
    if not result.get("ok"):
        raise RuntimeError("Telegram message failed")


def main():
    now = int(time.time())
    params = urllib.parse.urlencode({
        "resolution": RESOLUTION,
        "symbol": SYMBOL,
        "start": now - TF * 500,
        "end": now
    })
    data = get_json(f"{BASE}/v2/history/candles?{params}")
    if not data.get("success") or not data.get("result"):
        raise RuntimeError(f"Delta candle API error: {data}")

    candles = sorted(data["result"], key=lambda c: int(c["time"]))
    candles = [
        c for c in candles
        if int(c["time"]) + TF <= now
    ]
    closes = [float(c["close"]) for c in candles]

    if len(closes) < 250:
        raise RuntimeError(f"Not enough closed candles: {len(closes)}")

    # EMA 50
    ema_values = []
    ema = closes[0]
    alpha = 2 / (50 + 1)
    for price in closes:
        ema = alpha * price + (1 - alpha) * ema
        ema_values.append(ema)

    # WMA 200: newest price gets the highest weight
    wma_values = [None] * len(closes)
    weights = list(range(1, 201))
    denominator = sum(weights)
    for i in range(199, len(closes)):
        window = closes[i - 199:i + 1]
        wma_values[i] = sum(
            p * w for p, w in zip(window, weights)
        ) / denominator

    prev_ema, curr_ema = ema_values[-2], ema_values[-1]
    prev_wma, curr_wma = wma_values[-2], wma_values[-1]

    # Optional one-time test message via manual GitHub Actions run
    if os.getenv("TEST_ALERT") == "1":
        send_telegram(
            f"TEST OK: {SYMBOL} crossover bot connected. "
            f"Latest closed candle: {RESOLUTION}."
        )

    if prev_ema <= prev_wma and curr_ema > curr_wma:
        send_telegram(
            f"🟢 BULLISH CROSSOVER\n{SYMBOL} | {RESOLUTION}\n"
            f"EMA50: {curr_ema:.2f}\nWMA200: {curr_wma:.2f}"
        )
    elif prev_ema >= prev_wma and curr_ema < curr_wma:
        send_telegram(
            f"🔴 BEARISH CROSSOVER\n{SYMBOL} | {RESOLUTION}\n"
            f"EMA50: {curr_ema:.2f}\nWMA200: {curr_wma:.2f}"
        )
    else:
        print(f"No new crossover: {SYMBOL} {RESOLUTION}")


if __name__ == "__main__":
    main()
