#!/usr/bin/env python3
"""
中小企業向けWEB制作啓発 Threads自動投稿スクリプト
ターゲット：ホームページがない・古いサイトのまま運用している中小企業の経営者
"""
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env", override=True)


def load_topics() -> list[dict]:
    with open(BASE_DIR / "topics.json") as f:
        return json.load(f)["topics"]


HISTORY_FILE = BASE_DIR / "post_history.json"

# 投稿スロット定義: (スロット名, 開始時刻, 終了時刻)
SLOTS = [
    ("morning",        7,  9),   # 7:00〜9:59
    ("midmorning",    10, 12),   # 10:00〜12:59
    ("afternoon",     13, 15),   # 13:00〜15:59
    ("late_afternoon",16, 18),   # 16:00〜18:59
    ("evening",       20, 23),   # 20:00〜23:59
]


def get_current_slot():
    """現在時刻が対象スロット内かチェック。(スロット名, slot_index) or None"""
    hour = datetime.now().hour
    for i, (name, start, end) in enumerate(SLOTS):
        if start <= hour <= end:
            return name, i
    return None


def already_posted(slot_name: str) -> bool:
    """今日のスロットにすでに投稿済みかチェック"""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(HISTORY_FILE) as f:
            history = json.load(f)
        return history.get(today, {}).get(slot_name, False)
    except Exception:
        return False


def record_post(slot_name: str):
    """投稿済みを記録"""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    except Exception:
        history = {}
    if today not in history:
        history[today] = {}
    history[today][slot_name] = True
    # 7日分だけ保持
    keys = sorted(history.keys())
    if len(keys) > 7:
        for old in keys[:-7]:
            del history[old]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def pick_topic(topics: list[dict], slot_index: int) -> dict:
    """スロットごとに異なるトピックを選ぶ"""
    now = datetime.now()
    random.seed(now.strftime("%Y%m%d") + str(slot_index))
    return random.choice(topics)


def get_greeting() -> str:
    """時間帯に合った挨拶を返す。3回に1回は天気を添える"""
    hour = datetime.now().hour
    if hour < 12:
        greeting = "おはようございます☀️"
    elif hour < 18:
        greeting = "こんにちは😊"
    else:
        greeting = "こんばんは🌙"

    # 3回に1回は天気を添える（日付ベースで決定）
    day = datetime.now().day
    if day % 3 == 0:
        try:
            weather_map = {
                "Sunny": "晴れ☀️", "Clear": "晴れ☀️",
                "Partly cloudy": "曇り時々晴れ⛅", "Cloudy": "曇り☁️",
                "Overcast": "どんより曇り☁️",
                "Light rain": "小雨🌧️", "Moderate rain": "雨🌧️",
                "Heavy rain": "大雨🌧️", "Rain": "雨🌧️",
                "Light snow": "小雪❄️", "Snow": "雪❄️",
                "Mist": "霧🌫️", "Fog": "霧🌫️",
                "Thunder": "雷雨⛈️",
            }
            res = requests.get("https://wttr.in/Odawara?format=%C+%t", timeout=5)
            raw = res.text.strip()
            condition, temp = raw.rsplit(" ", 1)
            condition_jp = weather_map.get(condition, condition)
            greeting += f"\n今日の小田原は{condition_jp}、{temp}です。"
        except Exception:
            pass

    return greeting


def generate_post(topic: dict) -> tuple[str, str, str]:
    """
    3投稿スレッド形式で生成。スタイルをランダムにローテーション。
    Returns: (メイン投稿, コメント1, コメント2)
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    hashtags = os.environ.get(
        "POST_HASHTAGS",
        "#ホームページ制作 #中小企業 #集客 #web制作"
    )
    angle = random.choice(topic["angles"])

    # 投稿スタイルをランダムに選択（4種類ローテーション）
    styles = [
        {
            "name": "損失提示型",
            "main_hint": "「え、まだ〇〇してないの？」「毎月〇〇人のお客さんが競合に流れていますか」など、損失や危機感を数字・具体例で提示してスクロールを止める",
            "body_hint": "「このままだと〇〇を損し続ける」という現実を番号リストで整理し、今すぐできる一歩で締める",
        },
        {
            "name": "Before-After型",
            "main_hint": "「〇〇しているとこうなります」「〇〇している方へ、それ〇〇が原因です」など状況描写から入る",
            "body_hint": "【Before】よくある失敗 → 【After】改善後の変化を対比で見せる。読者が「これ変えられそう」と思える構造にする",
        },
        {
            "name": "実績・共感型",
            "main_hint": "「〇〇したら△△になったという連絡をもらいました」など実話ベースの一言から入る",
            "body_hint": "変わる前後の具体的な数字やエピソードを示してから、読者の悩みへの共感に展開する",
        },
        {
            "name": "悩み言語化型",
            "main_hint": "「〇〇で△△が続いている方へ」「やりたいけど〇〇で動けていない方へ」など当事者に語りかける",
            "body_hint": "悩みの正体をやさしく言語化して「実はこういうことなんです」という気づきを与え、解決の入口をほのめかす",
        },
    ]
    style = random.choice(styles)

    # 締め文言をランダムに選択（多様性を出す）
    closings = [
        "まずは話すだけで大丈夫です",
        "費用の相場感も正直にお伝えします",
        "0円でできることから一緒に整理します",
        "一緒に一歩だけ動いてみませんか",
        "神奈川・小田原を拠点に活動しています",
        "何から始めるか、一緒に考えましょう",
        "ぼったくりません。正直にお話しします",
    ]
    closing = random.choice(closings)

    prompt = f"""
あなたは「鈴木貴大」として、Threadsのスレッド投稿を書いてください。
神奈川県小田原市でWEB制作・動画制作・AI活用支援をしているフリーランスです。

【人柄・信条（必ず投稿全体に滲ませること）】
- 「親身に伴走する」：お客さんと一緒に考え、押しつけない。「まず話すだけでいい」を大切にする
- 「ぼったくらない」：0円でできることを先に提案し、費用は正直に開示する。売り込みは絶対しない
- 優しくて実直、正直な性格。自慢や煽りは絶対にしない
- 話しかけるような温かみがある文体

【ターゲット読者の本音】
- 「やりたいけど、時間がない・お金が怖い・ITが苦手」
- 「一人でやってるから相談できない」
- 「業者に頼むと丸投げになりそうで不安」
- 「やらないといけないのはわかってる。でも動けない」
対象：飲食店・美容室・小売店などの店舗経営者、中小企業・個人事業主

【今回のテーマ】
カテゴリ: {topic["category"]}
テーマ: {topic["theme"]}
切り口: {angle}

【今回の投稿スタイル：{style["name"]}】
■ メイン投稿のフック方針：{style["main_hint"]}
■ コメント1〜2の展開方針：{style["body_hint"]}

【リサーチ・根拠】
投稿内に具体的な数字・統計・調査結果を1つ含めてください。
例：「スマホ検索の6割以上が購買行動に繋がる」「採用活動でHPを確認する候補者は9割以上」など
実際の調査・統計に基づく内容を自然に使ってください。

【3投稿スレッドのフォーマット（厳守）】

■ メイン投稿（80〜120文字）
- フィードをスクロールしている人が思わず止まるキャッチ1〜2文
- 「これ自分のことだ」と感じさせる
- 続きへの期待を残して終わる（「続きはコメントで」は書かない）
- ハッシュタグ・URLは書かない

■ コメント1（120〜160文字）
- {style["name"]}のスタイルで展開する
- 「実はこういうことなんです」という気づきを与える
- 解決策の存在をほのめかすが、まだ言わない
- URLは書かない

■ コメント2（120〜160文字）
- 今日からできる具体的な一歩を1つだけ（無料・簡単・すぐできる）
- 親身に伴走する姿勢・ぼったくらない姿勢を自然に表現する
- 「{closing}」という一文を自然な形で入れる
- 最後は「気軽にLINEで相談してみてください😊（プロフィールから）」
- URLは書かない

必ず以下の形式のみで出力してください（説明文なし、区切り文字を正確に使う）:
[MAIN]
メイン投稿文をここに書く
[COMMENT1]
コメント1の文をここに書く
[COMMENT2]
コメント2の文をここに書く
[END]
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text.strip()

    def extract(text, tag):
        start = text.find(f"[{tag}]")
        if start == -1:
            return ""
        start += len(f"[{tag}]")
        for end_tag in ["[COMMENT1]", "[COMMENT2]", "[END]", "[MAIN]"]:
            end = text.find(end_tag, start)
            if end != -1:
                return text[start:end].strip()
        return text[start:].strip()

    main     = extract(response_text, "MAIN").replace("**", "")
    comment1 = extract(response_text, "COMMENT1").replace("**", "")
    comment2 = extract(response_text, "COMMENT2").replace("**", "")

    return f"{main}\n{hashtags}", comment1, comment2


def post_to_x(text: str, reply_to_id: str = None) -> dict:
    """X (Twitter) API v2でツイート投稿。reply_to_id指定でリプライ"""
    from requests_oauthlib import OAuth1
    auth = OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    payload = {"text": text}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
    res = requests.post(
        "https://api.twitter.com/2/tweets",
        auth=auth,
        json=payload,
        timeout=30,
    )
    res.raise_for_status()
    return {"id": res.json()["data"]["id"]}


def post_to_threads(text: str, reply_to_id: str = None) -> dict:
    """Threads API（Meta Graph API）で投稿。reply_to_id指定で返信投稿"""
    user_id = os.environ["THREADS_USER_ID"]
    access_token = os.environ["THREADS_ACCESS_TOKEN"]
    base_url = "https://graph.threads.net/v1.0"

    payload = {"media_type": "TEXT", "text": text, "access_token": access_token}
    if reply_to_id:
        payload["reply_to_id"] = reply_to_id

    container_res = requests.post(
        f"{base_url}/{user_id}/threads",
        data=payload,
        timeout=30,
    )
    container_res.raise_for_status()
    container_id = container_res.json()["id"]

    import time; time.sleep(15)  # Threads APIがコンテナを処理するのを待つ

    publish_res = requests.post(
        f"{base_url}/{user_id}/threads_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    publish_res.raise_for_status()
    return {"id": publish_res.json()["id"]}


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    print(line, end="")
    with open(BASE_DIR / "post.log", "a") as f:
        f.write(line)


def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    # --slot SLOTNAME で時間外でも指定スロットで投稿（GitHub Actions用）
    slot_override = None
    if "--slot" in sys.argv:
        idx = sys.argv.index("--slot")
        if idx + 1 < len(sys.argv):
            slot_override = sys.argv[idx + 1]

    if slot_override:
        slot_index = next((i for i, (n, s, e) in enumerate(SLOTS) if n == slot_override), 0)
        slot = (slot_override, slot_index)
    else:
        slot = get_current_slot()

    if slot is None and not dry_run and not force:
        print(f"[{datetime.now().strftime('%H:%M')}] 投稿時間外のためスキップ")
        return

    slot_name = slot[0] if slot else "morning"
    slot_index = slot[1] if slot else 0

    if already_posted(slot_name) and not dry_run and not force:
        log(f"本日の{slot_name}スロットは投稿済み。スキップ")
        return

    log("=== 自動投稿開始 ===")

    topics = load_topics()
    topic = pick_topic(topics, slot_index)
    log(f"トピック: {topic['category']} - {topic['theme']}")

    main_post, comment1, comment2 = generate_post(topic)
    log(f"--- メイン ---\n{main_post}\n")
    log(f"--- コメント1 ---\n{comment1}\n")
    log(f"--- コメント2 ---\n{comment2}\n")

    if dry_run:
        log("【DRY RUN】実際の投稿はスキップされました")
        return

    import time

    try:
        result = post_to_threads(main_post)
        main_id = result["id"]
        log(f"Threads メイン投稿成功: ID={main_id}")

        time.sleep(5)
        r2 = post_to_threads(comment1, reply_to_id=main_id)
        log(f"Threads コメント1成功: ID={r2['id']}")

        time.sleep(5)
        r3 = post_to_threads(comment2, reply_to_id=main_id)
        log(f"Threads コメント2成功: ID={r3['id']}")
    except Exception as e:
        log(f"Threads投稿エラー: {e}")
        sys.exit(1)

    # X投稿（.envのPOST_TO_X=trueで有効化）
    if os.environ.get("POST_TO_X", "false").lower() == "true":
        try:
            time.sleep(5)
            xr = post_to_x(main_post)
            xid = xr["id"]
            log(f"X メイン投稿成功: ID={xid}")
            time.sleep(5)
            xr2 = post_to_x(comment1, reply_to_id=xid)
            log(f"X コメント1成功: ID={xr2['id']}")
            time.sleep(5)
            xr3 = post_to_x(comment2, reply_to_id=xr2["id"])
            log(f"X コメント2成功: ID={xr3['id']}")
        except Exception as e:
            log(f"X投稿エラー（Threadsは成功済み）: {e}")

    record_post(slot_name)
    log("=== 投稿完了 ===")


if __name__ == "__main__":
    main()
