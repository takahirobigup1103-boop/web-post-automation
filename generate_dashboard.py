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


def esc(s):
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_reports():
    files = sorted(glob.glob(str(BASE_DIR / "reports" / "*.json")))
    return [json.loads(Path(f).read_text()) for f in files]


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

    return f'''<span class="eyebrow"><i></i>THREADS 週次レポート</span>
<h1>{latest["date"]} の週</h1>
<p class="sub">4つの役割が実測データを検討し、次週の方針を決定しました。</p>
<div class="verdict"><b>今週の総括</b>{esc(r["verdict"])}</div>

<h2>数字</h2>
<div class="grid">{card_html}</div>
{trend_html}
<h2>時間帯別の伸び</h2>
<div class="pane">{slot_html}</div>

<h2>専門家の所見</h2>
{voice_html}

<h2>次週の方針</h2>
<div class="two">
<div class="pane"><div class="k">重点すること</div><p>{esc(r["focus_note"])}</p></div>
<div class="pane avoid"><div class="k">避けること</div><p>{esc(r["avoid_note"])}</p></div>
</div>
<div class="pane" style="margin-top:12px"><div class="k">スタイル配分（次週の投稿に自動反映済み）</div>{sw_html}</div>

<h2>鈴木さんへの提案</h2>
<div class="pane"><ol>{acts}</ol></div>

<h2>今週の全投稿（{len(posts)}件）</h2>
<div class="tbl"><table>
<thead><tr><th></th><th>投稿の書き出し</th><th class="ta">views</th><th class="ta">♥</th><th class="ta">返信</th></tr></thead>
<tbody>{rows}</tbody></table></div>'''


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
footer{margin-top:38px;padding-top:17px;border-top:1px solid var(--line);font-size:11.5px;color:var(--soft);text-align:center}
@media(max-width:560px){.two{grid-template-columns:1fr}.slot{grid-template-columns:70px 1fr}.sv{grid-column:2;text-align:left;min-width:0}}
'''


def main():
    reports = load_reports()
    body = build(reports)
    html = f'''<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#1F4A42">
<title>Threads 週次レポート</title>
<style>{CSS}</style>
</head><body>
<div class="wrap">{body}
<footer>毎週日曜21時に自動更新 — 鈴木貴大 / 小田原</footer>
</div></body></html>'''
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"✓ {OUT} を生成（レポート {len(reports)}週分）")


if __name__ == "__main__":
    main()
