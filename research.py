#!/usr/bin/env python3
"""
Web検索でThreads運用・中小企業向け発信の最新情報を自動リサーチし、
Obsidian Vault にノートとして蓄積する。

  python3 research.py              # デフォルトのテーマでリサーチ
  python3 research.py "調べたいこと"  # テーマを指定

蓄積されたリサーチは post.py が投稿生成時に参照する。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env", override=True)

VAULT = BASE_DIR / "knowledge"
RESEARCH_DIR = VAULT / "リサーチ"
INSIGHTS_FILE = BASE_DIR / "research_insights.json"

# 週替わりで回すデフォルトのリサーチテーマ
DEFAULT_TOPICS = [
    "2026年 Threads アルゴリズム 最新 変更点 伸ばし方",
    "中小企業 経営者 悩み 2026 事務作業 人手不足 調査データ",
    "地方 中小企業 Web集客 成功事例 2026",
    "SNS 中小企業 BtoB 集客 リード獲得 手法 2026",
    "AI活用 中小企業 導入率 効果 統計 2026",
]


def pick_topic() -> str:
    """週ごとに違うテーマを選ぶ（週番号でローテーション）"""
    week = int(datetime.now().strftime("%V"))
    return DEFAULT_TOPICS[week % len(DEFAULT_TOPICS)]


def research(topic: str) -> dict:
    """Web検索して調査結果を構造化して返す"""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""あなたはSNSマーケティングのリサーチャーです。
以下のテーマについてWeb検索し、実務で使える知見をまとめてください。

【テーマ】
{topic}

【クライアント背景】
鈴木貴大（神奈川県小田原市・WEB制作/動画制作/AI活用支援のフリーランス）
ターゲット：従業員1〜30名の中小企業経営者（製造業・建設業・士業・飲食・美容・小売）
現状の課題：Threadsでの影響力（リーチ）が伸び悩んでいる。LINE登録0名。
信条：親身に伴走する・ぼったくらない・嘘をつかない

【調べてほしいこと】
1. このテーマの最新の事実・統計・調査データ（出典を明記）
2. 鈴木さんの投稿に今日から使える具体的な示唆
3. 投稿のネタとして使える切り口（3つ以上）

【重要な制約】
- 実際に検索して確認できた情報のみ書くこと。推測で数字を書かない
- 「〜と言われている」ではなく、出典のある事実を優先する
- 中小企業経営者にとって実用的かどうかを基準に取捨選択する

必ず以下のJSONのみを出力してください（前後に説明文を書かない）:

{{
  "summary": "この調査で分かったことの要約（200字程度）",
  "facts": [
    {{"fact": "確認できた事実や統計", "source": "出典（サイト名やURL）"}}
  ],
  "implications": ["鈴木さんの投稿に使える示唆（3〜5個）"],
  "post_angles": ["投稿のネタになる切り口（3〜5個）"]
}}"""

    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4000,
        thinking={"type": "adaptive"},
        tools=[{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 6,
        }],
        messages=[{"role": "user", "content": prompt}],
    )

    # 最後のテキストブロックからJSONを取り出す
    text = ""
    for block in msg.content:
        if block.type == "text":
            text = block.text
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def save_note(topic: str, result: dict):
    """Obsidianノートとして保存"""
    today = datetime.now().strftime("%Y-%m-%d")
    facts = "\n".join(
        f"- {f['fact']}\n  - 出典: {f.get('source', '不明')}" for f in result.get("facts", [])
    )
    impl = "\n".join(f"- {x}" for x in result.get("implications", []))
    angles = "\n".join(f"- [ ] {x}" for x in result.get("post_angles", []))

    safe = topic.replace("/", "／")[:40]
    md = f"""---
tags: [threads, リサーチ, 自動収集]
date: {today}
topic: {topic}
---

# 🔍 {safe}

> [!abstract] 要約
> {result.get('summary', '')}

## 確認できた事実
{facts}

## 鈴木さんの投稿への示唆
{impl}

## 投稿ネタの候補
{angles}

---
*{today} に research.py が自動収集*
関連: [[00_ダッシュボード]] | [[勝ちパターン集]] | [[Threadsアルゴリズム]]
"""
    path = RESEARCH_DIR / "自動収集" / f"{today}_{safe}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")
    return path


def save_insights(topic: str, result: dict):
    """post.py が参照する形式で蓄積（直近3件だけ保持）"""
    try:
        data = json.loads(INSIGHTS_FILE.read_text())
    except Exception:
        data = {"insights": []}

    data["insights"].insert(0, {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "topic": topic,
        "facts": [f["fact"] for f in result.get("facts", [])][:5],
        "angles": result.get("post_angles", [])[:5],
    })
    data["insights"] = data["insights"][:3]
    INSIGHTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else pick_topic()
    print(f"🔍 リサーチ中: {topic}\n")

    result = research(topic)

    print(f"【要約】{result.get('summary', '')}\n")
    print("【確認できた事実】")
    for f in result.get("facts", []):
        print(f"  ・{f['fact']}")
        print(f"    出典: {f.get('source', '不明')}")
    print("\n【投稿への示唆】")
    for x in result.get("implications", []):
        print(f"  ・{x}")
    print("\n【投稿ネタ候補】")
    for x in result.get("post_angles", []):
        print(f"  ・{x}")

    path = save_note(topic, result)
    save_insights(topic, result)
    print(f"\n✓ ノート保存: {path.relative_to(BASE_DIR)}")
    print(f"✓ 投稿生成用に research_insights.json を更新")


if __name__ == "__main__":
    main()
