#!/usr/bin/env python3
"""
reports/*.json から週次ダッシュボード（index.html）を生成する。
週を重ねるごとに推移グラフが伸びていく。スマホ対応・ライト/ダーク両対応。

  python3 generate_dashboard.py
"""
import glob
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUT = BASE_DIR / "docs" / "index.html"

# 指示Issueの投稿先（ダッシュボードの「指示を出す」ボタン）
REPO = "takahirobigup1103-boop/web-post-automation"


def esc(s):
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_reports():
    files = sorted(glob.glob(str(BASE_DIR / "reports" / "*.json")))
    return [json.loads(Path(f).read_text()) for f in files]


def collect_posts(reports) -> list[dict]:
    """全レポートの投稿を統合（重複除去）。期間切替はこのデータから再計算する。"""
    seen, out = set(), []
    for rep in reports:
        for p in rep.get("posts", []):
            hook = (p.get("text") or "").split("\n")[0]
            key = (p["date"], p["hour"], hook[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "d": p["date"],
                "h": p["hour"],
                "v": p.get("views", 0),
                "l": p.get("likes", 0),
                "r": p.get("replies", 0),
                "t": hook[:70],
            })
    out.sort(key=lambda p: (p["d"], p["h"]))
    return out


def build(reports):
    if not reports:
        return "<p>レポートがまだありません。</p>"
    latest = reports[-1]
    r, tw, lw = latest["review"], latest["this_week"], latest["last_week"]
    posts = latest["posts"]

    # ---- 指標カード ----
    def delta(now, prev):
        if not prev:
            return "", "flat"
        diff = now - prev
        if diff == 0:
            return "±0", "flat"
        return f"{'+' if diff > 0 else ''}{diff}", ("up" if diff > 0 else "down")

    cards = [("合計 views", tw["合計views"], lw.get("合計views")),
             ("中央値", tw["中央値"], lw.get("中央値")),
             ("最高", tw["最高"], lw.get("最高")),
             ("リプライ", tw["replies計"], lw.get("replies計")),
             ("いいね", tw["likes計"], lw.get("likes計")),
             ("投稿数", tw["投稿数"], lw.get("投稿数"))]
    card_html = ""
    for label, now, prev in cards:
        dtxt, cls = delta(now, prev)
        pw = '<span class="pw"> 前週比</span>' if dtxt else ""
        card_html += (f'<div class="card"><div class="k">{label}</div>'
                      f'<div class="v">{now:,}</div><div class="d {cls}">{dtxt}{pw}</div></div>')

    # ---- 週次推移（2週以上あれば折れ線）----
    trend_html = ""
    if len(reports) >= 2:
        pts = [(rp["date"][5:], rp["this_week"]["中央値"], rp["this_week"]["合計views"])
               for rp in reports]
        mx = max(p[2] for p in pts) or 1
        mxm = max(p[1] for p in pts) or 1
        W, H = 100, 40
        step = W / max(len(pts) - 1, 1)
        line_v = " ".join(f"{i*step:.1f},{H - p[2]/mx*H:.1f}" for i, p in enumerate(pts))
        line_m = " ".join(f"{i*step:.1f},{H - p[1]/mxm*H:.1f}" for i, p in enumerate(pts))
        dots = "".join(f'<circle cx="{i*step:.1f}" cy="{H - p[2]/mx*H:.1f}" r="1.1" class="dv"/>'
                       for i, p in enumerate(pts))
        labels = "".join(f"<span>{p[0]}</span>" for p in pts)
        trend_html = f'''<h2>週次の推移</h2>
<div class="pane">
  <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" class="chart">
    <polyline points="{line_v}" class="lv"/><polyline points="{line_m}" class="lm"/>{dots}
  </svg>
  <div class="xlab">{labels}</div>
  <div class="legend"><span class="lg lgv">合計views</span><span class="lg lgm">中央値</span></div>
</div>'''

    # ---- 時間帯 ----
    slots = tw["時間帯別"]
    mx = max(s["平均"] for s in slots.values()) or 1
    slot_html = ""
    for name, s in slots.items():
        best = " best" if s["平均"] == mx else ""
        slot_html += (f'<div class="slot{best}"><div class="sn">{name}</div>'
                      f'<div class="bar"><span style="width:{round(s["平均"]/mx*100)}%"></span></div>'
                      f'<div class="sv">{s["平均"]}<small> 平均 / 最高{s["最高"]}</small></div></div>')

    # ---- 専門家 ----
    voices = [("アナリスト", "数字", r["analyst"]), ("コピーライター", "言葉", r["copywriter"]),
              ("戦略家", "方針", r["strategist"])]
    voice_html = "".join(
        f'<div class="voice"><div class="vh"><span class="role">{n}</span>'
        f'<span class="tag">{t}</span></div><p>{esc(x)}</p></div>' for n, t, x in voices)

    # ---- スタイル配分 ----
    sw = r["style_weights"]
    swmax = max(sw.values()) or 1
    sw_html = "".join(
        f'<div class="sw"><span class="swn">{esc(k)}</span>'
        f'<div class="bar"><span style="width:{round(v/swmax*100)}%"></span></div>'
        f'<span class="swv">{v}</span></div>'
        for k, v in sorted(sw.items(), key=lambda x: -x[1]))

    # ---- 投稿一覧 ----
    pmax = max(p["views"] for p in posts) or 1
    rows = ""
    for i, p in enumerate(posts):
        hook = esc(p["text"].split("\n")[0][:60])
        rank = "top" if i < 3 else ""
        rows += (f'<tr class="{rank}"><td class="rk">{i+1}</td>'
                 f'<td class="hk">{hook}<div class="meta">{p["date"]} {p["hour"]}時</div></td>'
                 f'<td class="nm"><div class="mini"><span style="width:{round(p["views"]/pmax*100)}%">'
                 f'</span></div>{p["views"]}</td>'
                 f'<td class="nm sm">{p["likes"]}</td><td class="nm sm">{p["replies"]}</td></tr>')

    acts = "".join(f"<li>{esc(a)}</li>" for a in r.get("next_actions", []))

    directive_ui = f'''<h2>指示を出す</h2>
<div class="pane directive">
  <p class="dhint">今後の方向性を書いて送信すると、AIが解釈して<strong>次の投稿から自動で反映</strong>されます。
  （例：「動画の話をもっと増やして」「建設業向けを強化」「AIの話は減らして」）</p>
  <textarea id="dtext" rows="3" placeholder="例）飲食店向けの投稿を増やして、朝の時間帯を厚くしたい"></textarea>
  <div class="drow">
    <button id="dsend" type="button">この内容で指示を出す</button>
    <span id="dnote" class="dnote"></span>
  </div>
  <details class="dex">
    <summary>指示の書き方の例</summary>
    <ul>
      <li>「動画制作の話を増やして、実績の話は減らして」</li>
      <li>「建設業と製造業の社長に刺さる内容を強化したい」</li>
      <li>「もう少しやわらかい口調にして、売り込み感をさらに減らして」</li>
      <li>「AIの話は当面やめて、事務作業の悩みに集中して」</li>
    </ul>
  </details>
</div>
<script>
(function () {{
  var btn = document.getElementById('dsend');
  var box = document.getElementById('dtext');
  var note = document.getElementById('dnote');
  if (!btn) return;
  btn.addEventListener('click', function () {{
    var v = (box.value || '').trim();
    if (!v) {{ note.textContent = '指示を入力してください'; box.focus(); return; }}
    var url = 'https://github.com/{REPO}/issues/new'
      + '?labels=' + encodeURIComponent('指示')
      + '&title=' + encodeURIComponent('【指示】' + v.slice(0, 40))
      + '&body=' + encodeURIComponent(v);
    note.textContent = 'GitHubを開きます。緑の «Create» を押すと反映されます。';
    window.open(url, '_blank', 'noopener');
  }});
}})();
</script>'''

    tabs = '''<div class="tabs" role="tablist">
  <button class="tab" type="button" role="tab" data-period="1" aria-selected="false">1日</button>
  <button class="tab" type="button" role="tab" data-period="3" aria-selected="false">3日</button>
  <button class="tab on" type="button" role="tab" data-period="7" aria-selected="true">週間</button>
</div>'''

    return f'''<span class="eyebrow"><i></i>THREADS 週次レポート</span>
<h1>{latest["date"]} の週</h1>
<p class="sub">4つの役割が実測データを検討し、次週の方針を決定しました。</p>
<div class="verdict"><b>今週の総括</b>{esc(r["verdict"])}</div>
{directive_ui}

<h2>数字</h2>
{tabs}
<div class="grid" id="metrics"></div>
{trend_html}
<h2>時間帯別の伸び</h2>
<div class="pane" id="slots"></div>

<h2>投稿一覧（<span id="pcount">0</span>件）</h2>
<div id="postlist"></div>

<h2>専門家の所見<span class="wk">週次</span></h2>
{voice_html}

<h2>次週の方針<span class="wk">週次</span></h2>
<div class="two">
<div class="pane"><div class="k">重点すること</div><p>{esc(r["focus_note"])}</p></div>
<div class="pane avoid"><div class="k">避けること</div><p>{esc(r["avoid_note"])}</p></div>
</div>
<div class="pane" style="margin-top:12px"><div class="k">スタイル配分（次週の投稿に自動反映済み）</div>{sw_html}</div>

<h2>鈴木さんへの提案<span class="wk">週次</span></h2>
<div class="pane"><ol>{acts}</ol></div>'''


APP_JS = r'''
(function () {
  var POSTS = window.__POSTS__ || [];
  var ANCHOR = window.__ANCHOR__;           // データ内の最新日を「今日」とみなす
  var PERIODS = { '1': 1, '3': 3, '7': 7 };

  function dayNum(s) {                       // "YYYY-MM-DD" → 経過日数
    var p = s.split('-');
    return Math.floor(Date.UTC(+p[0], +p[1] - 1, +p[2]) / 86400000);
  }
  var anchorDay = dayNum(ANCHOR);

  function slice(days, offset) {             // offset=0:今期 / 1:前期
    var end = anchorDay - days * offset;
    var start = end - days;
    return POSTS.filter(function (p) {
      var d = dayNum(p.d);
      return d > start && d <= end;
    });
  }

  function stats(rows) {
    if (!rows.length) return null;
    var v = rows.map(function (p) { return p.v; }).sort(function (a, b) { return a - b; });
    var mid = Math.floor(v.length / 2);
    return {
      total: v.reduce(function (a, b) { return a + b; }, 0),
      median: v.length % 2 ? v[mid] : Math.round((v[mid - 1] + v[mid]) / 2),
      max: v[v.length - 1],
      likes: rows.reduce(function (a, p) { return a + p.l; }, 0),
      replies: rows.reduce(function (a, p) { return a + p.r; }, 0),
      count: rows.length
    };
  }

  function card(label, now, prev) {
    var d = '', cls = 'flat';
    if (prev != null) {
      var diff = now - prev;
      if (diff === 0) { d = '±0'; }
      else { d = (diff > 0 ? '+' : '') + diff; cls = diff > 0 ? 'up' : 'down'; }
    }
    var suffix = d ? '<span class="pw"> 前の期間比</span>' : '';
    return '<div class="card"><div class="k">' + label + '</div><div class="v">'
      + now.toLocaleString() + '</div><div class="d ' + cls + '">' + d + suffix + '</div></div>';
  }

  var SLOTS = [[7, 9, '朝7-9'], [10, 12, '午前10-12'], [13, 15, '昼13-15'],
               [16, 18, '夕16-18'], [20, 23, '夜20-23']];

  function renderSlots(rows) {
    var groups = SLOTS.map(function (s) {
      var hit = rows.filter(function (p) { return p.h >= s[0] && p.h <= s[1]; });
      var avg = hit.length
        ? Math.round(hit.reduce(function (a, p) { return a + p.v; }, 0) / hit.length) : 0;
      var max = hit.length ? Math.max.apply(null, hit.map(function (p) { return p.v; })) : 0;
      return { name: s[2], n: hit.length, avg: avg, max: max };
    }).filter(function (g) { return g.n > 0; });

    if (!groups.length) return '<p class="empty">この期間のデータがありません</p>';
    var top = Math.max.apply(null, groups.map(function (g) { return g.avg; })) || 1;
    return groups.map(function (g) {
      var best = g.avg === top ? ' best' : '';
      return '<div class="slot' + best + '"><div class="sn">' + g.name + '</div>'
        + '<div class="bar"><span style="width:' + Math.round(g.avg / top * 100) + '%"></span></div>'
        + '<div class="sv">' + g.avg + '<small> 平均 / ' + g.n + '件 / 最高' + g.max + '</small></div></div>';
    }).join('');
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderTable(rows) {
    if (!rows.length) return '<p class="empty">この期間のデータがありません</p>';
    var sorted = rows.slice().sort(function (a, b) { return b.v - a.v; });
    var top = sorted[0].v || 1;
    var body = sorted.map(function (p, i) {
      var rank = i < 3 ? ' class="top"' : '';
      return '<tr' + rank + '><td class="rk">' + (i + 1) + '</td>'
        + '<td class="hk">' + escapeHtml(p.t) + '<div class="meta">' + p.d + ' ' + p.h + '時</div></td>'
        + '<td class="nm"><div class="mini"><span style="width:'
        + Math.round(p.v / top * 100) + '%"></span></div>' + p.v + '</td>'
        + '<td class="nm sm">' + p.l + '</td><td class="nm sm">' + p.r + '</td></tr>';
    }).join('');
    return '<div class="tbl"><table><thead><tr><th></th><th>投稿の書き出し</th>'
      + '<th class="ta">views</th><th class="ta">♥</th><th class="ta">返信</th></tr></thead>'
      + '<tbody>' + body + '</tbody></table></div>';
  }

  function render(key) {
    var days = PERIODS[key];
    var cur = slice(days, 0), prev = slice(days, 1);
    var s = stats(cur), ps = stats(prev);

    var metrics = document.getElementById('metrics');
    if (!s) {
      metrics.innerHTML = '<p class="empty">この期間のデータがありません</p>';
    } else {
      metrics.innerHTML =
        card('合計 views', s.total, ps && ps.total) +
        card('中央値', s.median, ps && ps.median) +
        card('最高', s.max, ps && ps.max) +
        card('リプライ', s.replies, ps && ps.replies) +
        card('いいね', s.likes, ps && ps.likes) +
        card('投稿数', s.count, ps && ps.count);
    }
    document.getElementById('slots').innerHTML = renderSlots(cur);
    document.getElementById('postlist').innerHTML = renderTable(cur);
    document.getElementById('pcount').textContent = cur.length;

    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) {
      var on = b.dataset.period === key;
      b.classList.toggle('on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    try { localStorage.setItem('threads_period', key); } catch (e) {}
  }

  Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) {
    b.addEventListener('click', function () { render(b.dataset.period); });
  });

  var saved = null;
  try { saved = localStorage.getItem('threads_period'); } catch (e) {}
  render(PERIODS[saved] ? saved : '7');
})();
'''

CSS = '''
:root{--bg:#F7F8F7;--card:#fff;--ink:#1D2622;--soft:#66746D;--line:#E3E7E4;
--pine:#1F4A42;--pine-s:#E8EFEC;--mikan:#DC6C2A;--up:#1F7A5C;--down:#B4462F;
--sh:0 1px 2px rgba(29,38,34,.04),0 6px 20px rgba(29,38,34,.05);
--f:"Hiragino Kaku Gothic ProN","Hiragino Sans","Yu Gothic","Noto Sans JP",system-ui,sans-serif;
--m:"Hiragino Mincho ProN","Yu Mincho",serif}
@media(prefers-color-scheme:dark){:root{--bg:#141917;--card:#1E2522;--ink:#E9EDE9;--soft:#98A49D;
--line:#2E3833;--pine:#79B9A7;--pine-s:#1F2C28;--mikan:#EE8B4E;--up:#5FBF98;--down:#E0805F;
--sh:0 1px 2px rgba(0,0,0,.25),0 8px 24px rgba(0,0,0,.3)}}
:root[data-theme=light]{--bg:#F7F8F7;--card:#fff;--ink:#1D2622;--soft:#66746D;--line:#E3E7E4;--pine:#1F4A42;--pine-s:#E8EFEC;--mikan:#DC6C2A;--up:#1F7A5C;--down:#B4462F}
:root[data-theme=dark]{--bg:#141917;--card:#1E2522;--ink:#E9EDE9;--soft:#98A49D;--line:#2E3833;--pine:#79B9A7;--pine-s:#1F2C28;--mikan:#EE8B4E;--up:#5FBF98;--down:#E0805F}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f);line-height:1.7;-webkit-font-smoothing:antialiased}
.wrap{max-width:840px;margin:0 auto;padding:30px 16px 56px}
.eyebrow{display:inline-flex;gap:8px;align-items:center;font-size:12px;letter-spacing:.12em;font-weight:700;color:var(--pine);background:var(--pine-s);padding:6px 12px;border-radius:99px}
.eyebrow i{width:6px;height:6px;border-radius:50%;background:var(--mikan)}
h1{font-family:var(--m);font-weight:600;font-size:clamp(23px,5.5vw,33px);margin:15px 0 5px}
.sub{color:var(--soft);font-size:13.5px;margin:0}
.verdict{margin:20px 0 0;background:var(--pine);color:#F2F7F4;border-radius:14px;padding:17px 19px;font-size:14.5px;line-height:1.75}
.verdict b{display:block;font-size:11px;letter-spacing:.14em;opacity:.75;margin-bottom:5px}
h2{font-family:var(--m);font-size:18px;font-weight:600;margin:34px 0 13px;display:flex;align-items:center;gap:10px}
h2::after{content:"";flex:1;height:1px;background:var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:10px}
.card,.pane,.voice,.tbl{background:var(--card);border:1px solid var(--line);border-radius:13px;box-shadow:var(--sh)}
.card{padding:14px 15px}
.k{font-size:12px;color:var(--soft)}
.v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px;line-height:1.2}
.d{font-size:12.5px;font-weight:700;font-variant-numeric:tabular-nums}
.d.up{color:var(--up)}.d.down{color:var(--down)}.d.flat{color:var(--soft)}
.pw{font-weight:400;color:var(--soft)}
.pane{padding:15px 17px}
.pane .k{font-weight:700;color:var(--ink);margin-bottom:5px;font-size:13px}
.pane p{margin:0;font-size:13px;color:var(--soft);line-height:1.75}
.pane.avoid .k{color:var(--mikan)}
.chart{width:100%;height:120px;overflow:visible}
.chart polyline{fill:none;stroke-width:1.6;vector-effect:non-scaling-stroke;stroke-linejoin:round;stroke-linecap:round}
.lv{stroke:var(--pine)}.lm{stroke:var(--mikan);stroke-dasharray:3 2}
.dv{fill:var(--pine)}
.xlab{display:flex;justify-content:space-between;font-size:11px;color:var(--soft);margin-top:6px}
.legend{display:flex;gap:14px;margin-top:9px;font-size:11.5px;color:var(--soft)}
.lg::before{content:"";display:inline-block;width:14px;height:2px;margin-right:5px;vertical-align:middle}
.lgv::before{background:var(--pine)}.lgm::before{background:var(--mikan)}
.slot{display:grid;grid-template-columns:84px 1fr auto;gap:11px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}
.slot:last-child{border:0}
.sn{font-size:13px;color:var(--soft)}
.slot.best .sn{color:var(--ink);font-weight:700}
.bar{background:var(--pine-s);border-radius:99px;height:9px;overflow:hidden}
.bar span{display:block;height:100%;background:var(--pine);border-radius:99px}
.slot.best .bar span{background:var(--mikan)}
.sv{font-size:13.5px;font-weight:700;font-variant-numeric:tabular-nums;min-width:92px;text-align:right}
.sv small{font-weight:400;color:var(--soft);font-size:11px}
.voice{padding:15px 17px;margin-bottom:10px}
.vh{display:flex;align-items:center;gap:9px;margin-bottom:6px}
.role{font-weight:700;font-size:14px}
.tag{font-size:10.5px;letter-spacing:.1em;color:var(--pine);background:var(--pine-s);padding:3px 9px;border-radius:99px;font-weight:700}
.voice p{margin:0;font-size:13.5px;color:var(--soft);line-height:1.8}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sw{display:grid;grid-template-columns:112px 1fr 32px;gap:10px;align-items:center;padding:6px 0}
.swn{font-size:12.5px}.swv{font-size:12.5px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
ol{margin:0;padding-left:19px}ol li{font-size:13.5px;margin-bottom:7px;line-height:1.75}
.tbl{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:11px;letter-spacing:.08em;color:var(--soft);padding:11px 9px;border-bottom:1px solid var(--line);font-weight:700;white-space:nowrap}
th.ta{text-align:right}
td{padding:10px 9px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border:0}
tr.top{background:linear-gradient(90deg,var(--pine-s),transparent 60%)}
.rk{color:var(--soft);font-variant-numeric:tabular-nums;width:24px;font-size:11.5px}
tr.top .rk{color:var(--mikan);font-weight:700}
.hk{min-width:220px;line-height:1.55}
.meta{font-size:11px;color:var(--soft);margin-top:3px}
.nm{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap}
.nm.sm{font-weight:400;color:var(--soft)}
.mini{background:var(--pine-s);height:5px;border-radius:99px;overflow:hidden;margin-bottom:4px;min-width:50px}
.mini span{display:block;height:100%;background:var(--pine)}
.tabs{display:inline-flex;gap:3px;background:var(--pine-s);border-radius:11px;padding:3px;margin-bottom:13px}
.tab{font-family:var(--f);font-size:13px;font-weight:700;color:var(--soft);background:transparent;
border:0;border-radius:9px;padding:7px 17px;cursor:pointer;transition:background .12s,color .12s}
.tab:hover{color:var(--ink)}
.tab.on{background:var(--card);color:var(--pine);box-shadow:var(--sh)}
.tab:focus-visible{outline:2px solid var(--mikan);outline-offset:1px}
h2 .wk{font-family:var(--f);font-size:10.5px;font-weight:700;letter-spacing:.08em;color:var(--soft);
background:var(--pine-s);padding:3px 9px;border-radius:99px;margin-left:-4px}
.empty{margin:0;padding:14px 2px;font-size:13px;color:var(--soft);text-align:center}
@media(prefers-reduced-motion:reduce){.tab{transition:none}}
.directive{border-color:var(--pine);border-width:1.5px}
.dhint{margin:0 0 11px;font-size:12.5px;color:var(--soft);line-height:1.7}
.dhint strong{color:var(--pine)}
#dtext{width:100%;box-sizing:border-box;font-family:var(--f);font-size:14px;line-height:1.65;
color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:11px 12px;resize:vertical}
#dtext:focus{outline:2px solid var(--pine);outline-offset:1px;border-color:transparent}
#dtext::placeholder{color:var(--soft);opacity:.75}
.drow{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-top:9px}
#dsend{font-family:var(--f);font-size:13.5px;font-weight:700;color:#F2F7F4;background:var(--pine);
border:0;border-radius:9px;padding:10px 17px;cursor:pointer}
#dsend:hover{opacity:.9}
#dsend:focus-visible{outline:2px solid var(--mikan);outline-offset:2px}
.dnote{font-size:11.5px;color:var(--soft);flex:1;min-width:0}
.dex{margin-top:11px}
.dex summary{font-size:12px;color:var(--soft);cursor:pointer}
.dex ul{margin:8px 0 0;padding-left:18px}
.dex li{font-size:12.5px;color:var(--soft);margin-bottom:5px;line-height:1.65}
footer{margin-top:38px;padding-top:17px;border-top:1px solid var(--line);font-size:11.5px;color:var(--soft);text-align:center}
@media(max-width:560px){.two{grid-template-columns:1fr}.slot{grid-template-columns:70px 1fr}.sv{grid-column:2;text-align:left;min-width:0}}
'''


def main():
    reports = load_reports()
    body = build(reports)
    posts = collect_posts(reports)
    anchor = posts[-1]["d"] if posts else datetime.now().strftime("%Y-%m-%d")

    # </script> がデータ内に現れてもHTMLが壊れないようエスケープ
    data_json = json.dumps(posts, ensure_ascii=False).replace("</", "<\\/")
    data_script = (f'<script>window.__POSTS__={data_json};'
                   f'window.__ANCHOR__="{anchor}";</script>')

    html = f'''<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#1F4A42">
<title>Threads レポート</title>
<style>{CSS}</style>
</head><body>
<div class="wrap">{body}
<footer>毎週日曜21時に自動更新 — 鈴木貴大 / 小田原</footer>
</div>
{data_script}
<script>{APP_JS}</script>
</body></html>'''
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"✓ {OUT} を生成（レポート {len(reports)}週分 / 投稿 {len(posts)}件 / 基準日 {anchor}）")


if __name__ == "__main__":
    main()
