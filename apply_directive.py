#!/usr/bin/env python3
"""
自然言語の指示を解釈して strategy.json / topics.json を書き換える。

  python3 apply_directive.py "動画の話をもっと増やして"
  python3 apply_directive.py --dry-run "建設業向けを強化したい"

安全設計：AIが変更できるのは以下だけ。任意のコード実行やファイル操作はできない。
  - カテゴリ配分 / スタイル配分 / CTA配分（0〜3.0の範囲）
  - 重点方針 / 回避方針のテキスト
  - 新しいトピックの追加
変更は必ず差分を表示し、ログとして knowledge/指示ログ/ に残す。
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

STRATEGY_FILE = BASE_DIR / "strategy.json"
TOPICS_FILE = BASE_DIR / "topics.json"
LOG_DIR = BASE_DIR / "knowledge" / "指示ログ"

# AIが選べるスタイル名（post.py と一致させる）
STYLE_NAMES = [
    "見落とし指摘型", "ムダの可視化型", "損失提示型",
    "Before-After型", "共感・問いかけ型", "実績シェア型",
]
CTA_NAMES = ["配布型", "宣言型", "相談型", "無CTA型"]

WEIGHT_MIN, WEIGHT_MAX = 0.0, 3.0


def clamp(v) -> float:
    """重みを安全な範囲に収める"""
    try:
        return round(max(WEIGHT_MIN, min(WEIGHT_MAX, float(v))), 2)
    except (TypeError, ValueError):
        return 1.0


def interpret(directive: str, strategy: dict, categories: list[str]) -> dict:
    """指示を解釈して、変更内容をJSONで返す"""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""鈴木貴大さんのThreads自動投稿システムの設定を、指示に従って調整してください。

【鈴木さんからの指示】
{directive}

【現在の設定】
カテゴリ配分: {json.dumps(strategy.get('category_weights', {}), ensure_ascii=False, indent=2)}
スタイル配分: {json.dumps(strategy.get('style_weights', {}), ensure_ascii=False, indent=2)}
CTA配分: {json.dumps(strategy.get('cta_weights', {}), ensure_ascii=False, indent=2)}
重点方針: {strategy.get('focus_note', '')}
回避方針: {strategy.get('avoid_note', '')}

【選べるカテゴリ（既存）】
{', '.join(categories)}

【選べるスタイル】
- 見落とし指摘型：読者が気づいていない穴を指摘する（実測で最も伸びる）
- ムダの可視化型：日常に埋もれた時間のムダを数字で可視化する
- 損失提示型：損失や危機感を提示する
- Before-After型：失敗例→改善後を対比する
- 共感・問いかけ型：読者の本音を言語化して寄り添う
- 実績シェア型：鈴木さんの制作実績を語る（実測で最も伸びない。上げないこと）

【選べるCTA】
配布型（無料プレゼントで登録動機を作る）／宣言型（押しつけない存在表明）／相談型（相談呼びかけ）／無CTA型（価値提供のみ）

【ルール】
- 重みは 0.0〜3.0。合計を1にする必要はない（相対的な比率）
- 指示に関係ない項目は変更しない（変更する項目だけJSONに含める）
- 「増やして」なら現在値の1.5〜2倍程度、「減らして」なら半分程度、「やめて」なら0.1〜0.3が目安
- 新カテゴリが必要な場合のみ new_topics に追加する。既存カテゴリで対応できるなら追加しない
- 鈴木さんの信条（親身に伴走・ぼったくらない・嘘をつかない）に反する指示は reject に理由を書く

必ず以下のJSONのみを出力（前後に説明文を書かない）:

{{
  "understanding": "指示をどう理解したか（1〜2文）",
  "changes": [
    "変更内容を人が読める形で列挙（例：動画制作カテゴリを1.0→2.5に強化）"
  ],
  "category_weights": {{ "カテゴリ名": 数値 }},
  "style_weights": {{ "スタイル名": 数値 }},
  "cta_weights": {{ "CTA名": 数値 }},
  "focus_note": "新しい重点方針（変更しないなら省略）",
  "avoid_note": "新しい回避方針（変更しないなら省略）",
  "new_topics": [
    {{"id": "英数字のID", "category": "カテゴリ名", "theme": "テーマ", "angles": ["切り口1", "切り口2", "切り口3"]}}
  ],
  "reject": "実行できない場合のみ理由。実行できるなら空文字"
}}"""

    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=3000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
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


def apply(result: dict, strategy: dict, topics_doc: dict) -> list[str]:
    """変更を適用し、実際に行った差分の説明を返す"""
    applied = []

    # 重み系（範囲を強制）
    for key, valid in (("category_weights", None),
                       ("style_weights", STYLE_NAMES),
                       ("cta_weights", CTA_NAMES)):
        patch = result.get(key) or {}
        if not patch:
            continue
        current = strategy.setdefault(key, {})
        for name, value in patch.items():
            if valid and name not in valid:
                applied.append(f"⚠️ 不明な項目のためスキップ: {name}")
                continue
            before = current.get(name, "未設定")
            current[name] = clamp(value)
            applied.append(f"{key}: {name} {before} → {current[name]}")

    # 方針テキスト
    for key, label in (("focus_note", "重点方針"), ("avoid_note", "回避方針")):
        new = result.get(key)
        if new and new.strip() and new != strategy.get(key):
            strategy[key] = new.strip()[:200]
            applied.append(f"{label}を更新: {strategy[key]}")

    # 新トピック追加
    existing_ids = {t["id"] for t in topics_doc["topics"]}
    for t in result.get("new_topics") or []:
        tid = str(t.get("id", "")).strip()
        if not tid or tid in existing_ids:
            continue
        angles = [str(a) for a in (t.get("angles") or [])][:6]
        if not (t.get("category") and t.get("theme") and angles):
            continue
        topics_doc["topics"].append({
            "id": tid,
            "category": str(t["category"]),
            "theme": str(t["theme"]),
            "angles": angles,
        })
        existing_ids.add(tid)
        applied.append(f"新トピック追加: {t['category']} - {t['theme']}")

    return applied


def save_log(directive: str, result: dict, applied: list[str]):
    """Obsidianノートとして指示の履歴を残す"""
    now = datetime.now()
    body = "\n".join(f"- {a}" for a in applied) or "- （変更なし）"
    changes = "\n".join(f"- {c}" for c in result.get("changes", []))
    md = f"""---
tags: [threads, 指示ログ]
date: {now.strftime('%Y-%m-%d')}
---

# 🗣️ 指示: {directive[:40]}

**日時**: {now.strftime('%Y-%m-%d %H:%M')}

## 鈴木さんの指示
> {directive}

## AIの理解
{result.get('understanding', '')}

## 意図した変更
{changes}

## 実際に適用された変更
{body}

---
関連: [[00_ダッシュボード]]
"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{now.strftime('%Y-%m-%d_%H%M')}.md"
    path.write_text(md, encoding="utf-8")
    return path


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv
    if not args:
        print("使い方: python3 apply_directive.py \"指示の内容\"")
        sys.exit(1)
    directive = " ".join(args).strip()

    strategy = json.loads(STRATEGY_FILE.read_text())
    topics_doc = json.loads(TOPICS_FILE.read_text())
    categories = sorted({t["category"] for t in topics_doc["topics"]})

    print(f"📣 指示: {directive}\n")
    result = interpret(directive, strategy, categories)

    if result.get("reject"):
        print(f"❌ 実行できません: {result['reject']}")
        sys.exit(2)

    print(f"【理解】{result.get('understanding', '')}\n")
    print("【変更内容】")
    for c in result.get("changes", []):
        print(f"  ・{c}")

    applied = apply(result, strategy, topics_doc)
    print("\n【適用される差分】")
    for a in applied:
        print(f"  ・{a}")

    if dry_run:
        print("\n【DRY RUN】ファイルは変更していません")
        return

    strategy["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    strategy["updated_by"] = "directive"
    STRATEGY_FILE.write_text(json.dumps(strategy, ensure_ascii=False, indent=2))
    TOPICS_FILE.write_text(json.dumps(topics_doc, ensure_ascii=False, indent=2))
    path = save_log(directive, result, applied)

    print(f"\n✓ 設定を更新しました（次の投稿から反映）")
    print(f"✓ ログ: {path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
