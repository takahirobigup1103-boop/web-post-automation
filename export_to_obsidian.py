#!/usr/bin/env python3
"""
週次レポートとリサーチ結果を Obsidian Vault（Markdown）として書き出す。

  python3 export_to_obsidian.py

Obsidian未インストールでも動作する（ただのMarkdownファイル群）。
後でObsidianを入れて knowledge/ フォルダを Vault として開けばそのまま使える。
"""
import glob
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
VAULT = BASE_DIR / "knowledge"


def slug(text: str) -> str:
    """Obsidianのファイル名に使えない文字を除去"""
    for ch in '\\/:*?"<>|#^[]':
        text = text.replace(ch, "")
    return text.strip()[:60]


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def export_weekly_reports():
    """reports/*.json → knowledge/週次レポート/*.md"""
    files = sorted(glob.glob(str(BASE_DIR / "reports" / "*.json")))
    if not files:
        return []

    written = []
    for f in files:
        rep = json.loads(Path(f).read_text())
        date = rep["date"]
        tw, lw, r = rep["this_week"], rep["last_week"], rep["review"]
        posts = rep["posts"]

        def diff(key):
            if not lw.get(key):
                return ""
            d = tw[key] - lw[key]
            return f"（前週比 {'+' if d > 0 else ''}{d}）"

        top = "\n".join(
            f"| {i+1} | {p['views']} | {p['likes']} | {p['replies']} | {p['text'].splitlines()[0][:40]} |"
            for i, p in enumerate(posts[:10])
        )
        weights = "\n".join(f"- {k}: **{v}**" for k, v in
                            sorted(r["style_weights"].items(), key=lambda x: -x[1]))
        actions = "\n".join(f"- [ ] {a}" for a in r.get("next_actions", []))

        md = f"""---
tags: [threads, 週次レポート]
date: {date}
---

# 📊 週次レポート {date}

> [!abstract] 今週の総括
> {r['verdict']}

## 数字

| 指標 | 今週 | 前週比 |
|------|------|--------|
| 合計views | {tw['合計views']} | {diff('合計views')} |
| 中央値 | {tw['中央値']} | {diff('中央値')} |
| 最高 | {tw['最高']} | {diff('最高')} |
| リプライ | {tw['replies計']} | {diff('replies計')} |
| いいね | {tw['likes計']} | {diff('likes計')} |
| 投稿数 | {tw['投稿数']} | {diff('投稿数')} |

## 時間帯別

| 時間帯 | 件数 | 平均 | 最高 |
|--------|------|------|------|
""" + "\n".join(
            f"| {name} | {s['件数']} | {s['平均']} | {s['最高']} |"
            for name, s in tw["時間帯別"].items()
        ) + f"""

## 専門家の所見

### 📈 アナリスト（数字）
{r['analyst']}

### ✍️ コピーライター（言葉）
{r['copywriter']}

### 🎯 戦略家（方針）
{r['strategist']}

## 次週の方針

> [!tip] 重点すること
> {r['focus_note']}

> [!warning] 避けること
> {r['avoid_note']}

### スタイル配分
{weights}

## 鈴木さんへの提案
{actions}

## 上位10投稿

| # | views | ♥ | 返信 | 書き出し |
|---|-------|---|------|----------|
{top}

---
関連: [[00_ダッシュボード]] | [[勝ちパターン集]] | [[Threadsアルゴリズム]]
"""
        p = VAULT / "週次レポート" / f"{date}.md"
        write(p, md)
        written.append((date, rep))
    return written


def export_win_patterns(reports):
    """全レポートから高viewsの投稿を集約 → 勝ちパターン集"""
    all_posts = []
    for _, rep in reports:
        all_posts.extend(rep["posts"])
    all_posts.sort(key=lambda p: -p["views"])

    rows = "\n".join(
        f"| {p['views']} | {p['likes']} | {p['date']} | {p['text'].splitlines()[0][:50]} |"
        for p in all_posts[:30]
    )
    low = "\n".join(
        f"| {p['views']} | {p['date']} | {p['text'].splitlines()[0][:50]} |"
        for p in sorted(all_posts, key=lambda p: p["views"])[:15]
    )

    md = f"""---
tags: [threads, 勝ちパターン]
updated: {datetime.now().strftime('%Y-%m-%d')}
---

# 🏆 勝ちパターン集

実測データから抽出した、反応が良かった投稿と悪かった投稿のアーカイブ。
新しい投稿を作るときはここを見返す。

## 🔥 高views TOP30

| views | ♥ | 日付 | 書き出し |
|-------|---|------|----------|
{rows}

## ❄️ 低views（反面教師）

| views | 日付 | 書き出し |
|-------|------|----------|
{low}

## 抽出された法則

- 主語が「読者の会社」の投稿が伸びる。「鈴木さんの実績」は伸びない
- 数字＋具体的な場面（議事録45分、見積書2時間）が強い
- 停滞をなぞる独白（「まあいいか」「動けてない」）は反応が悪い
- 鍵括弧の引用で始めると下位に沈みやすい

---
関連: [[00_ダッシュボード]] | [[Threadsアルゴリズム]]
"""
    write(VAULT / "リサーチ" / "勝ちパターン集.md", md)


def export_dashboard(reports):
    """ハブノート"""
    links = "\n".join(
        f"- [[{date}]] — 合計{rep['this_week']['合計views']}views / 中央値{rep['this_week']['中央値']}"
        for date, rep in reversed(reports)
    )
    latest = reports[-1][1] if reports else None
    summary = ""
    if latest:
        r = latest["review"]
        summary = f"""
> [!abstract] 最新の総括（{latest['date']}）
> {r['verdict']}

**今の重点**: {r['focus_note']}
**今の回避**: {r['avoid_note']}
"""

    md = f"""---
tags: [threads, ダッシュボード]
updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
---

# 🏠 Threads運用ダッシュボード

鈴木貴大（小田原・WEB制作/動画/AI活用支援）のThreads運用ナレッジベース。
{summary}
## 📊 週次レポート
{links}

## 📚 リサーチ
- [[勝ちパターン集]] — 実測データから抽出した伸びる投稿・沈む投稿
- [[Threadsアルゴリズム]] — 2026年のアルゴリズム仕様と対策
- [[ターゲット像]] — 中小企業経営者のペルソナと本音

## 🎯 KPI
- LINE登録: **0名** / 目標10名
- 現状の課題: 影響力（リーチ）を高める段階

## 🔧 システム構成
- 投稿: 毎日5回（7/10/13/16/20時）GitHub Actions
- 週次レビュー: 毎週日曜21時、4役が合議して方針を自動更新
- 設定ファイル: `strategy.json`（週次レビューが自動更新）
- 実績データ: `real_cases.json`（架空事例は禁止）

---
*このVaultは `export_to_obsidian.py` が自動生成しています*
"""
    write(VAULT / "00_ダッシュボード.md", md)


def export_static_notes():
    """恒久的なリサーチノート（初回のみ生成、既存なら上書きしない）"""
    notes = {
        "リサーチ/Threadsアルゴリズム.md": """---
tags: [threads, リサーチ, アルゴリズム]
---

# 🧠 Threadsアルゴリズム（2026年）

## ランキングシグナル（重要度順）
1. **リプライ（会話の往復）** — 最強シグナル。Metaは「リプライがビュー全体の約半分」と発信
2. **最初の1時間のエンゲージメント速度** — 初動が配信量を決める
3. **保存・共有** — 実用的なコンテンツが有利
4. **滞在時間** — 長く読まれる投稿が評価される

## 実務上の含意
- 質問で締めてリプライを誘発する
- チェックリスト形式で保存を促す
- 投稿時間帯は読者が活動している時間に（朝・夜）
- ハッシュタグは1つしか機能しない。複数付けるとbot臭くなる

## 小さいアカウントの戦略
検索結果が一致して指摘するのは「**自分の投稿より、他人の投稿への気の利いたリプライのほうが伸びる**」という点。
1日10分の手動リプライが、フォロワー初動問題の最も安い解決策。

---
関連: [[00_ダッシュボード]] | [[勝ちパターン集]]
""",
        "リサーチ/ターゲット像.md": """---
tags: [threads, リサーチ, ターゲット]
---

# 👤 ターゲット像

## 誰か
従業員1〜30名の中小企業経営者。
飲食・美容・小売だけでなく、**製造業・建設業・士業・卸売**など「地方の会社の社長」。

## 本音
- 「見積書・請求書・日報…事務作業に追われて本業の時間がない」
- 「人を雇う余裕はない。でも手が足りない」
- 「HPもSNSもAIも、やった方がいいのは分かってる。誰かに任せたい」
- 「業者は高そうだし、何をされるか分からなくて怖い」
- 「一人で決めるのが不安。相談相手がいない」

## 刺さる/刺さらない
| 刺さる | 刺さらない |
|--------|-----------|
| 自分の会社の見落とし | 他人（鈴木さん）の成功事例 |
| 具体的な数字と場面 | 抽象的な啓発 |
| 今日5分でできること | 大きな投資が前提の話 |
| 「一緒に考えます」 | 「相談してください」の連呼 |

## 心理的な注意
**いいねを押さない層**。図星を突かれた投稿にいいねすると「自分が該当する」と認めることになるため。
viewsとプロフィール遷移で評価すべきで、いいね率で判断してはいけない。

---
関連: [[00_ダッシュボード]] | [[勝ちパターン集]]
""",
    }
    for rel, content in notes.items():
        p = VAULT / rel
        if not p.exists():  # 既存は上書きしない（手動編集を尊重）
            write(p, content)


def main():
    reports = export_weekly_reports()
    if not reports:
        print("レポートがまだありません。先に weekly_review.py を実行してください。")
        return
    export_win_patterns(reports)
    export_static_notes()
    export_dashboard(reports)

    files = list(VAULT.rglob("*.md"))
    print(f"✓ Obsidian Vault を生成しました: {VAULT}")
    print(f"  {len(files)}ファイル / 週次レポート{len(reports)}件")
    for f in sorted(files):
        print(f"   - {f.relative_to(VAULT)}")


if __name__ == "__main__":
    main()
