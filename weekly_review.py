#!/usr/bin/env python3
"""
週次レビュー：リサーチャー→アナリスト→コピーライター→戦略家の4役が順に検討し、
次週の方針（スタイル配分・カテゴリ配分・重点/回避方針）を決定して strategy.json を更新する。

  python3 weekly_review.py            # 実行して strategy.json を更新
  python3 weekly_review.py --dry-run  # 分析だけして更新しない

結果は reports/YYYY-MM-DD.json に蓄積され、ダッシュボードの元データになる。
"""
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env", override=True)

REPORTS_DIR = BASE_DIR / "reports"
STRATEGY_FILE = BASE_DIR / "strategy.json"
JST = timezone(timedelta(hours=9))

# 分析対象のスタイル名（post.py と一致させる）
STYLE_NAMES = [
    "見落とし指摘型", "ムダの可視化型", "損失提示型",
    "Before-After型", "共感・問いかけ型", "実績シェア型",
]


# ---------- リサーチャー：データ収集 ----------
def collect_posts(days: int = 15) -> list[dict]:
    """
    Threads APIから投稿と指標を収集。
    APIは1回50件までのため、指定日数分をカバーするまでページネーションする。
    （これをしないと古い週のデータが打ち切られ、前週比が誤って算出される）
    """
    token = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = "https://graph.threads.net/v1.0"
    cutoff = datetime.now(JST).date() - timedelta(days=days)

    raw, after, pages = [], None, 0
    while pages < 8:  # 安全弁（最大400件）
        params = {"fields": "id,text,timestamp", "limit": 50, "access_token": token}
        if after:
            params["after"] = after
        res = requests.get(f"{base}/{uid}/threads", params=params, timeout=30)
        res.raise_for_status()
        body = res.json()
        batch = body.get("data", [])
        if not batch:
            break
        raw.extend(batch)
        pages += 1
        # 最古の投稿が期間外まで遡れたら終了
        oldest = datetime.strptime(batch[-1]["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST).date()
        if oldest < cutoff:
            break
        after = body.get("paging", {}).get("cursors", {}).get("after")
        if not after:
            break

    rows = []
    for p in raw:
        jst = datetime.strptime(p["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
        if jst.date() < cutoff:
            continue
        ins = requests.get(f"{base}/{p['id']}/insights", params={
            "metric": "views,likes,replies,reposts", "access_token": token,
        }, timeout=30)
        if ins.status_code != 200:
            continue
        m = {x["name"]: x["values"][0]["value"] for x in ins.json().get("data", [])}
        rows.append({
            "date": jst.strftime("%Y-%m-%d"),
            "hour": jst.hour,
            "text": p.get("text") or "",
            "views": m.get("views", 0),
            "likes": m.get("likes", 0),
            "replies": m.get("replies", 0),
            "reposts": m.get("reposts", 0),
        })
    return rows


def split_this_week(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """直近7日とその前7日に分ける"""
    today = datetime.now(JST).date()
    wk1, wk2 = [], []
    for r in rows:
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        delta = (today - d).days
        if delta <= 7:
            wk1.append(r)
        elif delta <= 14:
            wk2.append(r)
    return wk1, wk2


# ---------- アナリスト：数値分析 ----------
def analyze(rows: list[dict]) -> dict:
    if not rows:
        return {}
    v = [r["views"] for r in rows]
    by_hour = {}
    for lo, hi, name in [(7, 9, "朝7-9"), (10, 12, "午前10-12"), (13, 15, "昼13-15"),
                         (16, 18, "夕16-18"), (20, 23, "夜20-23")]:
        s = [r["views"] for r in rows if lo <= r["hour"] <= hi]
        if s:
            by_hour[name] = {"件数": len(s), "平均": round(statistics.mean(s)), "最高": max(s)}
    return {
        "投稿数": len(rows),
        "合計views": sum(v),
        "中央値": round(statistics.median(v)),
        "平均": round(statistics.mean(v)),
        "最高": max(v),
        "likes計": sum(r["likes"] for r in rows),
        "replies計": sum(r["replies"] for r in rows),
        "時間帯別": by_hour,
        "上位5件": [{"views": r["views"], "hook": r["text"].split("\n")[0][:45]}
                    for r in sorted(rows, key=lambda x: -x["views"])[:5]],
        "下位5件": [{"views": r["views"], "hook": r["text"].split("\n")[0][:45]}
                    for r in sorted(rows, key=lambda x: x["views"])[:5]],
    }


# ---------- コピーライター＆戦略家：AIによる合議 ----------
def confer(this_week: dict, last_week: dict, strategy: dict) -> dict:
    """3つの専門家役が順に検討し、次週の方針をJSONで返す"""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""あなたは3人の専門家チームです。順番に検討し、最後に次週の方針を決めてください。

【クライアント】
鈴木貴大（神奈川県小田原市・WEB制作/動画制作/AI活用支援のフリーランス）
ターゲット：従業員1〜30名の中小企業経営者
信条：親身に伴走する・ぼったくらない・嘘をつかない
現状の課題：LINE登録が0名。まずThreadsでの影響力（リーチとエンゲージメント）を高める段階。

【今週の実測データ】
{json.dumps(this_week, ensure_ascii=False, indent=2)}

【前週の実測データ】
{json.dumps(last_week, ensure_ascii=False, indent=2)}

【データ品質の注意】
投稿本数は毎日5回で固定運用しており、鈴木さんが投稿数を増減させることはない。
もし両週の投稿数に大きな差がある場合、それは運用の変化ではなくAPIの取得漏れである。
その場合は合計値ではなく「中央値」「平均」で比較し、投稿数の差を根拠に結論を出してはいけない。

【現在の設定】
スタイル配分: {json.dumps(strategy.get('style_weights', {}), ensure_ascii=False)}
重点方針: {strategy.get('focus_note', '')}
回避方針: {strategy.get('avoid_note', '')}

──────────────────
【検討の順番】

■ アナリスト（数字担当）
今週と前週を比較し、何が起きたかを数字で述べる。伸びた要因・落ちた要因を特定する。
サンプル数が少ない項目については「断定できない」と正直に述べること。
1件だけの成功を過度に一般化してはいけない（過去にこの失敗をしている）。

■ コピーライター（文章担当）
上位5件と下位5件の書き出しを読み比べ、言葉のレベルで何が違うのかを specific に述べる。
主語は誰か、読者は自分ごとと感じるか、スクロールを止める力があるかを見る。

■ 戦略家（方針担当）
上記2名の意見を踏まえ、次週の方針を決める。
・スタイル配分は現状から大きく変えすぎない（1週間のデータは母数が小さいため）
・変更する場合は必ず数字の根拠を示す
・影響力を高める段階なので、売り込みより価値提供を優先する

──────────────────
【出力形式】
必ず以下のJSONのみを出力してください（前後に説明文を書かない）:

{{
  "analyst": "アナリストの所見（200字程度）",
  "copywriter": "コピーライターの所見（200字程度）",
  "strategist": "戦略家の判断と根拠（200字程度）",
  "verdict": "今週の総括を1文で",
  "style_weights": {{ {", ".join(f'"{n}": 数値' for n in STYLE_NAMES)} }},
  "focus_note": "次週の重点方針（投稿生成AIへの指示文。80字以内）",
  "avoid_note": "次週の回避方針（投稿生成AIへの指示文。80字以内）",
  "next_actions": ["鈴木さん自身がやるべきこと（1〜3個）"]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # ```json ``` で囲まれている場合を剥がす
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def main():
    dry_run = "--dry-run" in sys.argv
    print("■ リサーチャー：データ収集中...")
    rows = collect_posts()
    wk1, wk2 = split_this_week(rows)
    print(f"  取得 {len(rows)}件（今週 {len(wk1)}件 / 前週 {len(wk2)}件）")

    if not wk1:
        print("今週のデータがありません。終了します。")
        return

    print("■ アナリスト：数値集計中...")
    this_week, last_week = analyze(wk1), analyze(wk2)
    print(f"  今週 合計{this_week['合計views']}views 中央値{this_week['中央値']}")
    if last_week:
        diff = this_week["合計views"] - last_week["合計views"]
        print(f"  前週比 {diff:+d} views")

    strategy = json.loads(STRATEGY_FILE.read_text()) if STRATEGY_FILE.exists() else {}

    print("■ コピーライター＆戦略家：検討中...")
    result = confer(this_week, last_week, strategy)

    print("\n" + "=" * 50)
    print(f"【総括】{result['verdict']}")
    print(f"\n[アナリスト] {result['analyst']}")
    print(f"\n[コピーライター] {result['copywriter']}")
    print(f"\n[戦略家] {result['strategist']}")
    print(f"\n【次週の配分】{json.dumps(result['style_weights'], ensure_ascii=False)}")
    print(f"【重点】{result['focus_note']}")
    print(f"【回避】{result['avoid_note']}")
    print("\n【鈴木さんへの提案】")
    for a in result.get("next_actions", []):
        print(f"  ・{a}")
    print("=" * 50)

    # レポート保存
    today = datetime.now(JST).strftime("%Y-%m-%d")
    REPORTS_DIR.mkdir(exist_ok=True)
    report = {
        "date": today,
        "this_week": this_week,
        "last_week": last_week,
        "review": result,
        "posts": sorted(wk1, key=lambda x: -x["views"]),
    }
    if not dry_run:
        (REPORTS_DIR / f"{today}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2))
        strategy.update({
            "updated_at": today,
            "updated_by": "weekly_review",
            "style_weights": result["style_weights"],
            "focus_note": result["focus_note"],
            "avoid_note": result["avoid_note"],
        })
        STRATEGY_FILE.write_text(json.dumps(strategy, ensure_ascii=False, indent=2))
        print(f"\n✓ strategy.json を更新（次週の投稿から反映）")
        print(f"✓ reports/{today}.json に保存")
    else:
        print("\n【DRY RUN】ファイルは更新していません")


if __name__ == "__main__":
    main()
