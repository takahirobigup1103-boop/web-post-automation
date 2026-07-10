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


def load_real_cases() -> list[dict]:
    """鈴木さんの実際の制作実績のみ。架空の事例は使わない。"""
    try:
        with open(BASE_DIR / "real_cases.json") as f:
            return json.load(f)["cases"]
    except Exception:
        return []


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


def record_post(slot_name: str, hook: str = ""):
    """投稿済みを記録。hookにはメイン投稿の書き出しを保存（重複防止に使う）"""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    except Exception:
        history = {}
    if today not in history:
        history[today] = {}
    # 文字列も真値なので already_posted / ワークフローの事前チェックと互換
    # 書き出し＋2行目（業種・人物が入る行）まで保存して、業種の使い回しも防ぐ
    history[today][slot_name] = hook[:110] if hook else True
    # 7日分だけ保持
    keys = sorted(history.keys())
    if len(keys) > 7:
        for old in keys[:-7]:
            del history[old]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_recent_hooks() -> list[str]:
    """直近7日間に投稿したメイン投稿の書き出しを返す（重複防止用）"""
    try:
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    except Exception:
        return []
    hooks = []
    for day in sorted(history.keys()):
        for slot, value in history[day].items():
            if isinstance(value, str):
                hooks.append(value)
    return hooks


# 反応が高いカテゴリは出現率を上げる（インプレッション実績に応じて調整）
# 2026-07-05 インサイト実測に基づく重み（views上位: 事務作業156/HP必要性154/スマホ対応142）
CATEGORY_WEIGHTS = {
    "事務作業の負担": 2.5,      # 実測1位。数字フックとの相性が最高
    "AI活用": 2.0,            # 実測上位常連・中小企業の関心が高い
    "機会損失": 2.0,           # 「HPなくても大丈夫」＋統計が実測2位
    "古いサイトの弊害": 2.0,     # 「スマホで崩れてた」実話引用が実測3位
    "スマホ対応": 1.5,
    "やりたいけどできない": 1.5,  # 共感系。views中位だがLINE登録に直結
    "人手不足": 2.0,           # 月額伴走プランへの導線
    "外部パートナー活用": 1.5,   # 伴走プラン直結（出しすぎると売り込み臭）
    "費用対効果": 1.5,
    "リニューアル事例": 1.5,
}


def pick_topic(topics: list[dict], slot_index: int) -> dict:
    """スロットごとに異なるトピックを選ぶ（カテゴリ重み付き）"""
    now = datetime.now()
    random.seed(now.strftime("%Y%m%d") + str(slot_index))
    weights = [CATEGORY_WEIGHTS.get(t["category"], 1.0) for t in topics]
    return random.choices(topics, weights=weights, k=1)[0]


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


def generate_post(topic: dict, recent_hooks: list[str] = None) -> tuple[str, str, str]:
    """
    3投稿スレッド形式で生成。スタイルを重み付きローテーション。
    recent_hooks: 直近7日間のメイン投稿の書き出しリスト（重複防止用）
    Returns: (メイン投稿, コメント1, コメント2)
    ※Threadsではハッシュタグは逆効果（1つしか機能せずbot臭になる）のため付けない
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    angle = random.choice(topic["angles"])
    recent_hooks_block = "\n".join(f"- {h}" for h in (recent_hooks or [])) or "（履歴なし）"

    # 実際の制作実績（架空の事例は絶対に使わない）
    real_cases = load_real_cases()
    case = random.choice(real_cases) if real_cases else None
    if case:
        case_block = f"""【実際の制作実績（この事例だけを題材にできる。他の架空事例は禁止）】
業種：{case['industry']}
やったこと：{case['work']}
結果：{case.get('result') or '（結果は語らず、取り組み自体を題材にする）'}
※この事例を使う場合、上に書かれていない数字や成果を足してはいけない。
※「PVが2倍」など具体的すぎる数字は書かない。「アクセスが伸びた」「問い合わせが増えた」程度の事実に留める。
※必ずしも事例を主役にしなくてよい。テーマに合わなければ一般論で書き、その場合も嘘の事例は作らない。"""
    else:
        case_block = "【事例なし】架空の事例は作らないこと。一般論で書く。"

    # 投稿スタイルを重み付きで選択（実測: 行動→結果型が高view）
    styles = [
        {
            "name": "実績シェア型",
            "weight": 3.0,
            "main_hint": "上記の【実際の制作実績】を題材に、「〇〇（業種）のホームページで△△をしたら、□□につながった」という事実を書く。誇張ゼロ、盛らない。数字は書かず「増えた」「掲載されるようになった」程度に留める。鈴木さん自身の実体験として、謙虚に淡々と語る",
            "body_hint": "何をどう変えたのかを具体的に見せ、「特別なことをしたわけではない」という等身大の姿勢を保つ",
        },
        {
            "name": "損失提示型",
            "weight": 1.0,
            "main_hint": "「毎月〇〇人のお客さんが競合に流れている」など、損失や危機感を数字・具体例で提示してスクロールを止める",
            "body_hint": "「このままだと〇〇を損し続ける」という現実を番号リストで整理し、今すぐできる一歩で締める",
        },
        {
            "name": "Before-After型",
            "weight": 1.0,
            "main_hint": "「〇〇しているとこうなります」「〇〇している方へ、それ〇〇が原因です」など状況描写から入る",
            "body_hint": "【Before】よくある失敗 → 【After】改善後の変化を対比で見せる。読者が「これ変えられそう」と思える構造にする",
        },
        {
            "name": "共感・問いかけ型",
            "weight": 0.8,
            "main_hint": "読者（経営者）が日々感じている本音を、鈴木さん自身の言葉でそっと言語化する。事例は使わず、読者の状況に寄り添う一言から入る",
            "body_hint": "悩みの正体をやさしく整理し、「一人で抱えなくていい」という安心につなげる",
        },
    ]
    style = random.choices(styles, weights=[s["weight"] for s in styles], k=1)[0]

    # CTAの型をローテーション（毎回同じ定型文はbot臭・売り込み臭になるため）
    cta_types = [
        ("配布型", "「スマホでできる集客チェックリストの完全版、LINEで無料配布してます。プロフィールからどうぞ」のような、登録する理由を渡す締め方", 0.35),
        ("宣言型", "「困ったら小田原の鈴木を思い出してください。プロフィールにLINEがあります」のような、押しつけない存在表明の締め方", 0.25),
        ("無CTA型", "CTAを完全に省き、価値提供だけで気持ちよく終える（信頼残高を貯める回）。LINEにもプロフィールにも一切触れない", 0.20),
        ("相談型", "「気軽にLINEで相談してみてください😊（プロフィールから）」のような直接の相談呼びかけ", 0.20),
    ]
    cta = random.choices(cta_types, weights=[c[2] for c in cta_types], k=1)[0]

    # 月額伴走プランへの言及（約4割の投稿にだけ入れる。毎回だと売り込み臭くなる）
    mention_plan = random.random() < 0.4
    plan_block = """
【月額伴走プランの紹介（コメント2に自然に組み込む）】
以下の趣旨を、押しつけがましくない自分の言葉で1〜2文だけ入れてください：
「ホームページの更新・SNS・AI活用など、手が回らない作業を月々定額でまるごとお手伝いする伴走プランをやっています。人を1人雇うより、ずっと小さな負担で。金額は最初に全部お見せします」
※「〜円」など具体的な金額は書かない。「定額」「続けられる金額」という表現に留める
""" if mention_plan else ""

    prompt = f"""
あなたは「鈴木貴大」として、Threadsのスレッド投稿を書いてください。
神奈川県小田原市でWEB制作・動画制作・AI活用支援をしているフリーランスです。

【人柄・信条（必ず投稿全体に滲ませること）】
- 「親身に伴走する」：お客さんと一緒に考え、押しつけない。「まず話すだけでいい」を大切にする
- 「ぼったくらない」：0円でできることを先に提案し、費用は正直に開示する。売り込みは絶対しない
- 優しくて実直、正直な性格。自慢や煽りは絶対にしない
- 話しかけるような温かみがある文体

【ターゲット読者＝中小企業の経営者（従業員1〜30名規模）】
飲食・美容・小売だけでなく、製造業・建設業・士業・卸売など「地方の会社の社長」を強く意識する。
彼らの本音：
- 「見積書・請求書・日報…事務作業に追われて本業の時間がない」
- 「人を雇う余裕はない。でも手が足りない」
- 「HPもSNSもAIも、やった方がいいのは分かってる。誰かに任せたい」
- 「業者は高そうだし、何をされるか分からなくて怖い」
- 「一人で決めるのが不安。相談相手がいない」

【今回のテーマ】
カテゴリ: {topic["category"]}
テーマ: {topic["theme"]}
切り口: {angle}

【今回の投稿スタイル：{style["name"]}】
■ メイン投稿のフック方針：{style["main_hint"]}
■ コメント1〜2の展開方針：{style["body_hint"]}

{case_block}

【絶対厳守・嘘をつかない（最優先ルール）】
- 鈴木さんは「正直・実直」が信条。事実でないことは一切書かない
- 架空のお客さん・架空のエピソードを作ってはいけない。事例を出すなら上の【実際の制作実績】だけ
- 「〇〇が2倍」「売上△△％アップ」のような、確認できない・盛った数字を書かない
- 「たくさんの方が…」「多くの社長が…」のような、根拠のない大げさな一般化をしない
- 事例が今回のテーマに合わないなら、無理に事例を使わず一般的な役立つ話として書く（それでも嘘は書かない）

【フックの強化ルール（最重要）】
- 1行目は22文字以内。数字・断言・会話の引用のどれかで始める
- 「〜ませんか？」「〜ありませんか？」は使用禁止（使いすぎて読者に飽きられているため）
- 良い1行目の例：
  ・「電話番号を上に移したら、電話が増えた」（行動→結果。実測で最も反応が良い）
  ・「月3万円の求人広告、応募ゼロ。」（数字＋現実）
  ・「見積書1枚に2時間。」（数字＋断言）
- 【フックのNGパターン（実測で反応が悪い。絶対に避ける）】
  ・停滞独白：「まあいいか」「動けてない」「変わってないな…」など読者の不作為をなぞるだけの引用。罪悪感を刺激するだけで、いいねを押すと図星を認めることになるため経営者は絶対に押さない
  ・説教・啓発：「AIって大手のものでしょ」型の、読者を「遅れている側」に置く構図。防衛反応を生む
- 2行目以降で状況を具体化し、「これ、うちのことだ」と思わせる

【リプライ誘発（メイン投稿の締め・必須）】
メイン投稿の最後の1行は、読者が10秒で答えられる質問で締めること。以下のどれかの型を使う：
・二択型「みなさんの会社は、電話派ですか？LINE派ですか？」
・自分の答え先出し型「ちなみにうちは〇〇でした。みなさんの業種ではどうですか？」
・数字記入型「見積書1枚、何分かかってますか？」
※抽象的な質問（「どう思いますか？」）は禁止。「〜ませんか？」も禁止。

【重複禁止（厳守）】
以下は直近に投稿した書き出しです。テーマ・言い回し・フックが類似する投稿を作ってはいけません。
同じ悩みを扱う場合も、必ず別の業種・別の場面・別の切り口で書くこと：
{recent_hooks_block}
- 上記リストと同じ書き出し・同じ言い回しを避ける。語り出しや切り口を毎回変える
- 実績を語るときも「先月〜から連絡をもらいました」のような同じ定型を繰り返さない。事実の範囲で自然に表現を変える

【リサーチ・根拠】
コメント1またはコメント2に、具体的な数字・統計・調査結果を1つ自然に含めてください。
※メイン投稿には統計を入れない（長くなりフックが薄まるため）。「※」や出典の括弧書きは使わず、文章に溶け込ませること。
{plan_block}
【3投稿スレッドのフォーマット（厳守）】

■ メイン投稿（80〜120文字）
- 上記フックルールに従った、スクロールが止まる書き出し
- 最後は10秒で答えられる質問で締める（リプライ誘発ルール参照）
- ハッシュタグ・URLは書かない

■ コメント1（120〜160文字）
- 「今すぐスマホで確認できる3点チェック」のような番号付きリスト形式にすること
  例：「①電話番号は画面の上半分にあるか ②スマホで文字がつぶれていないか ③営業時間は最新か」
- 読者が「あとで見返したい」と保存したくなる実用性を最優先する。抽象論・共感の繰り返しは禁止
- 3つのうち1つは今日5分でできるものにする
- URLは書かない

■ コメント2（120〜160文字）
- 今日からできる具体的な一歩を1つだけ（無料・簡単・すぐできる）
- 親身に伴走する姿勢・ぼったくらない姿勢を自然に表現する
- 締め方は【{cta[0]}】：{cta[1]}
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

    return main, comment1, comment2


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

    main_post, comment1, comment2 = generate_post(topic, recent_hooks=get_recent_hooks())
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

    # X投稿（.envのPOST_TO_X=trueで有効化）。Xではハッシュタグが機能するので付ける
    if os.environ.get("POST_TO_X", "false").lower() == "true":
        hashtags = os.environ.get("POST_HASHTAGS", "")
        try:
            time.sleep(5)
            xr = post_to_x(f"{main_post}\n{hashtags}".strip())
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

    record_post(slot_name, hook=" ／ ".join(l for l in main_post.split("\n") if l.strip())[:110])
    log("=== 投稿完了 ===")


if __name__ == "__main__":
    main()
