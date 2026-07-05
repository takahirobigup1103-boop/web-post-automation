#!/usr/bin/env python3
"""
Threads投稿のインサイト分析スクリプト
使い方: python3 analyze_insights.py
直近25件のviews/likes/repliesをviews順で表示する
"""
import os
import requests
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env", override=True)

token = os.environ["THREADS_ACCESS_TOKEN"]
user_id = os.environ["THREADS_USER_ID"]
base = "https://graph.threads.net/v1.0"

res = requests.get(f"{base}/{user_id}/threads", params={
    "fields": "id,text,timestamp",
    "limit": 25,
    "access_token": token,
}, timeout=30)
res.raise_for_status()
posts = res.json().get("data", [])

results = []
for p in posts:
    ins = requests.get(f"{base}/{p['id']}/insights", params={
        "metric": "views,likes,replies,reposts",
        "access_token": token,
    }, timeout=30)
    if ins.status_code != 200:
        continue
    m = {x["name"]: x["values"][0]["value"] for x in ins.json().get("data", [])}
    results.append((p["timestamp"][:10], (p.get("text") or "")[:45].replace("\n", "／"), m))

results.sort(key=lambda r: -r[2].get("views", 0))
total_views = sum(r[2].get("views", 0) for r in results)
total_likes = sum(r[2].get("likes", 0) for r in results)

print(f"=== 直近{len(results)}件（views順）合計views={total_views} likes={total_likes} ===")
for date, text, m in results:
    print(f"{date} | views={m.get('views',0):>4} likes={m.get('likes',0):>3} | {text}")
