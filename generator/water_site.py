# このファイルは niche_finder から nf water-sync で写したもの。直接直さない。
"""水道料金のしくみ: 事業者ごとの順位・比較・『なぜ』の材料を計算し、静的サイトを生成する。

  nf water-build   →  sites/suido/（GitHub Pages にそのまま置ける）

公開する事業者は themes/water/data/release.csv（slug, name, released）で決める（一度に増やさない）。
"""
from __future__ import annotations

import csv
import html
import re
import statistics
from pathlib import Path

from .water import FIELDS, OUT as UTILITIES

DATA = Path("data")
SITE_OUT = Path("_site")
BASE_URL = "https://naoo047.github.io/suido/"
SITE_NAME = "水道料金のしくみ"
SOURCE = ("総務省「令和6年度 地方公営企業年鑑」水道事業（施設・業務概況及び経営分析に関する調）",
          "https://www.soumu.go.jp/main_sosiki/c-zaisei/kouei_R06/index_su.html")
COST_LABELS = {
    "c_depreciation": "減価償却費（水道管や浄水場などの設備の費用）",
    "c_purchased_water": "受水費（ほかの事業者から買う水の代金）",
    "c_repair": "修繕費",
    "c_salary": "職員給与費",
    "c_outsourcing": "委託料",
    "c_interest": "支払利息（借入金の利息）",
    "c_power": "動力費（ポンプなどの電気代）",
}
RATE_SYSTEM = {"1": "用途別（家庭用・業務用などで料金が違う）", "2": "口径別（水道メーターの大きさで料金が違う）", "3": "その他"}


def _norm_name(s: str) -> str:
    return s.replace("ヶ", "ケ")


def load_codes(path: Path = DATA / "jichitai_code.csv") -> dict[tuple[str, str], str]:
    with open(path, encoding="utf-8") as f:
        return {(r["pref"], _norm_name(r["name"])): r["code"] for r in csv.DictReader(f)}


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_end_utilities(path: Path = UTILITIES) -> list[dict]:
    """家庭に直接給水する上水道（給水形態 1）で、10㎥料金のあるものだけ。数値は float に。"""
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["form"] == "1"]
    for r in rows:
        for k in FIELDS:
            if k not in ("rate_date", "rate_system"):
                r[k] = _f(r[k])
    return [r for r in rows if r["rate10"]]


def slug_for(u: dict, codes: dict) -> str:
    code = codes.get((u["pref"], _norm_name(u["name"])))
    if code:
        return code[:5]                       # 全国地方公共団体コードの検査数字を除いた 5 桁
    return "k" + u["id"].replace("-", "")     # 企業団など（団体コードが無い）


def wareki(s: str) -> str:
    m = re.match(r"([MTSHR])\.\s*(\d+)\.\s*(\d+)\.\s*(\d+)", s or "")
    if not m:
        return ""
    base = {"M": 1867, "T": 1911, "S": 1925, "H": 1988, "R": 2018}[m.group(1)]
    return f"{base + int(m.group(2))}年{int(m.group(3))}月{int(m.group(4))}日"


def _median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def analyze(utilities: list[dict], codes: dict) -> dict[str, dict]:
    """事業者ごとの順位・比較・『なぜ』の材料。キーは slug。"""
    keys = ["rate10", "cost_unit", "supply_unit", "revenue_water_pct", "pipe_efficiency"] + list(COST_LABELS)
    med = {k: _median(u[k] for u in utilities) for k in keys}
    med["aged_pct"] = _median(u["pipe_aged_km"] / u["pipe_km"] * 100 for u in utilities
                              if u["pipe_aged_km"] is not None and u["pipe_km"])
    med["renew_pct"] = _median(u["pipe_renewed_km"] / u["pipe_km"] * 100 for u in utilities
                               if u["pipe_renewed_km"] is not None and u["pipe_km"])
    by_rate = sorted(utilities, key=lambda u: -u["rate10"])
    rank = {u["id"]: i + 1 for i, u in enumerate(by_rate)}
    by_pref: dict[str, list[dict]] = {}
    for u in by_rate:
        by_pref.setdefault(u["pref"], []).append(u)
    out = {}
    for u in utilities:
        same = by_pref[u["pref"]]
        a = {
            "slug": slug_for(u, codes), "name": u["name"], "pref": u["pref"], "operator": u["operator"],
            "population": u["population"], "rate10": u["rate10"], "base_volume": u["base_volume"],
            "base_fee": u["base_fee"], "over_fee": u["over_fee"], "rate_date": wareki(u["rate_date"]),
            "rate_system": RATE_SYSTEM.get(str(u["rate_system"] or "").split(".")[0], ""),
            "rank": rank[u["id"]], "n": len(utilities), "pref_rank": same.index(u) + 1, "pref_n": len(same),
            "cost_unit": u["cost_unit"], "supply_unit": u["supply_unit"],
            "recovery_pct": round(u["supply_unit"] / u["cost_unit"] * 100, 1) if u["cost_unit"] and u["supply_unit"] else None,
            "revenue_water_pct": u["revenue_water_pct"], "pipe_efficiency": u["pipe_efficiency"],
            "aged_pct": round(u["pipe_aged_km"] / u["pipe_km"] * 100, 1) if u["pipe_aged_km"] is not None and u["pipe_km"] else None,
            "renew_pct": round(u["pipe_renewed_km"] / u["pipe_km"] * 100, 2) if u["pipe_renewed_km"] is not None and u["pipe_km"] else None,
            "costs": [{"key": k, "label": COST_LABELS[k], "value": u[k], "median": med[k]} for k in COST_LABELS if u[k] is not None],
            "median": med,
        }
        a["renew_years"] = round(100 / a["renew_pct"]) if a["renew_pct"] else None
        out[a["slug"]] = a
    return out


def reasons(a: dict) -> list[str]:
    """数字の比較だけで言えることを文にする（評価や予測はしない）。"""
    m, out = a["median"], []
    if a["cost_unit"] and m["cost_unit"]:
        r = a["cost_unit"] / m["cost_unit"]
        if r >= 1.15:
            out.append(f"水1㎥を届けるのにかかる費用（給水原価）が{a['cost_unit']:.0f}円で、全国の中央値（{m['cost_unit']:.0f}円）の{r:.1f}倍です。")
        elif r <= 0.87:
            out.append(f"水1㎥を届けるのにかかる費用（給水原価）が{a['cost_unit']:.0f}円で、全国の中央値（{m['cost_unit']:.0f}円）より低めです。")
    big = sorted([c for c in a["costs"] if c["median"] is not None and c["value"] >= 1.5 * max(c["median"], 1)
                  and c["value"] - c["median"] >= 10], key=lambda c: -(c["value"] - c["median"]))
    for c in big[:2]:
        out.append(f"費用のうち{c['label'].split('（')[0]}が1㎥あたり{c['value']:.0f}円で、全国の中央値（{c['median']:.0f}円）より多くかかっています。")
    if a["pipe_efficiency"] and m["pipe_efficiency"] and a["pipe_efficiency"] <= 0.6 * m["pipe_efficiency"]:
        out.append("水道管の長さのわりに使われる水の量が少なく（配水管使用効率が全国の中央値の6割以下）、"
                   "家がまばらな地域に水を届けている事業者に多い形です。")
    if a["recovery_pct"] is not None and a["recovery_pct"] < 100:
        out.append(f"料金回収率が{a['recovery_pct']:.0f}%で、料金収入だけでは給水の費用をまかなえていません（100%を下回っているため）。")
    return out


def level(a: dict) -> str:
    return "高い" if a["rank"] <= a["n"] * 0.25 else "安い" if a["rank"] > a["n"] * 0.75 else "中くらいの"


def _yen(v) -> str:
    return f"{v:,.0f}円" if v is not None else "—"


def _num(v, fmt) -> str:
    return format(v, fmt) if v is not None else "—"


def _row(label: str, val: str, med: str | None = None) -> str:
    m = f'<td class="med">{med}</td>' if med is not None else ""
    return f"<tr><th>{html.escape(label)}</th><td>{val}</td>{m}</tr>"


def _page(title: str, body: str, description: str, canonical: str, depth: int) -> str:
    root = "../" * depth
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><meta name=\"description\" content=\"{html.escape(description)}\">"
            f'<link rel="canonical" href="{canonical}"><link rel="stylesheet" href="{root}style.css"></head><body>'
            f'<header class="site"><a href="{root}">{SITE_NAME}</a></header>{body}'
            f'<footer class="site"><a href="{root}about/">運営者情報</a> ・ <a href="{root}privacy/">プライバシーポリシー</a>'
            f"<p>出典：{html.escape(SOURCE[0])}を加工して作成</p></footer></body></html>\n")


def render_utility(a: dict, pref_list: list[dict], released: set[str]) -> str:
    m, e = a["median"], html.escape
    pref_run = [x for x in pref_list if x["operator"] == "都道府県営" and x["slug"] != a["slug"]]
    pref_note = (f"<p class=\"note\">{e(a['pref'])}では、{e(pref_run[0]['name'])}が運営する水道が家庭に直接給水している市町村もあります。"
                 f"同じ市町村の中でも地域によって水道が違うことがあるので、お住まいの地域の水道がどちらかは、水道局の案内で確かめてください。</p>"
                 if pref_run else "")
    if a["operator"] == "都道府県営":
        pref_note = (f"<p class=\"note\">{e(a['name'])}が運営する水道は、{e(a['pref'])}内の一部の市町村に給水しています。"
                     "お住まいの地域の水道がどこかは、水道局の案内で確かめてください。</p>")
    title = f"{a['name']}の水道料金は高い？全国・県内の順位と理由"
    rs = reasons(a)
    reason_html = ("<ul class=\"list\">" + "".join(f"<li>{e(r)}</li>" for r in rs) + "</ul>") if rs else \
        "<p>費用の項目に、全国と比べて目立って大きいものはありませんでした。</p>"
    costs = "".join(_row(c["label"], f"{c['value']:.1f}円", f"{c['median']:.1f}円") for c in a["costs"])
    pref_rows = "".join(
        f"<tr class=\"{'sel' if x['slug'] == a['slug'] else ''}\"><td>{i + 1}</td><th>"
        + (f"<a href=\"../{x['slug']}/\">{e(x['name'])}</a>" if x["slug"] in released and x["slug"] != a["slug"] else e(x["name"]))
        + f"</th><td>{_yen(x['rate10'])}</td></tr>" for i, x in enumerate(pref_list))
    renew = f"今のペースで全部の水道管を取り替えると、およそ{a['renew_years']}年かかる計算です。" if a["renew_years"] else ""
    body = f"""<main class="wrap">
<p class="eyebrow">{e(a['pref'])}の水道料金</p>
<h1>{e(title)}</h1>
<p class="lead">{e(a['name'])}の水道（{e(a['operator'])}）の家庭用の料金を、全国{a['n']:,}の水道事業と比べました。料金の背景になる費用や水道管の古さも、国の統計の数字で示します。</p>
<section class="answer">
  <p class="big">1か月10㎥あたり <b>{_yen(a['rate10'])}</b><small>（税込み・口径13mm）</small></p>
  <p>全国<b>{a['rank']:,}位</b>／{a['n']:,}（高い順）・{e(a['pref'])}内<b>{a['pref_rank']}位</b>／{a['pref_n']}。全国の中で<b>{level(a)}</b>ほうです（全国の中央値は{_yen(m['rate10'])}）。</p>
{pref_note}</section>
<section><h2>料金のしくみ</h2><table class="cmp">
{_row("基本料金", _yen(a['base_fee']))}
{_row("基本料金に含まれる水量", f"{a['base_volume']:.0f}㎥" if a['base_volume'] else "なし")}
{_row("それを超えた分（最初の段階）", f"1㎥あたり{_yen(a['over_fee'])}" if a['over_fee'] else "—")}
{_row("料金の決め方", e(a['rate_system']) or "—")}
{_row("今の料金になった日", a['rate_date'] or "—")}
{_row("給水人口", f"{a['population']:,.0f}人" if a['population'] else "—")}
</table><p class="note">使う量が多いほど1㎥あたりの単価が上がる料金表の事業者もあるので、実際の請求額は水道局の料金表で確かめてください。下水道の使用料は別にかかります。</p></section>
<section><h2>なぜこの料金なのか（数字で見る）</h2>{reason_html}
<div class="scroll"><table class="cmp"><thead><tr><th>水1㎥あたり</th><td>{e(a['name'])}</td><td class="med">全国の中央値</td></tr></thead>
{_row("給水原価（届けるのにかかる費用）", f"{_num(a['cost_unit'], '.1f')}円", f"{m['cost_unit']:.1f}円")}
{_row("供給単価（1㎥あたりの料金収入）", f"{_num(a['supply_unit'], '.1f')}円", f"{m['supply_unit']:.1f}円")}
{costs}</table></div></section>
<section><h2>これからに関わる数字</h2><div class="scroll"><table class="cmp"><thead><tr><th></th><td>{e(a['name'])}</td><td class="med">全国の中央値</td></tr></thead>
{_row("料金回収率（供給単価 ÷ 給水原価）", f"{_num(a['recovery_pct'], '.1f')}%", "")}
{_row("法定耐用年数を過ぎた水道管の割合", f"{_num(a['aged_pct'], '.1f')}%", f"{m['aged_pct']:.1f}%")}
{_row("1年で取り替えた水道管の割合", f"{_num(a['renew_pct'], '.2f')}%", f"{m['renew_pct']:.2f}%")}
{_row("有収率（配った水のうち料金になった割合）", f"{_num(a['revenue_water_pct'], '.1f')}%", f"{m['revenue_water_pct']:.1f}%")}
</table></div>
<p class="note">{renew}料金回収率が100%を下回ると、料金収入だけでは給水の費用をまかなえていないことを表します。ただし総務省は、限られた指標だけで経営のよしあしをすぐに判断するものではないとしています。</p></section>
<details class="all"><summary><span class="sum-title">{e(a['pref'])}の水道料金（10㎥・高い順）</span><span class="sum-hint">{a['pref_n']}事業者をまとめて見る</span></summary>
<div class="all-body"><div class="table-wrap"><table><thead><tr><th>順位</th><th>事業者</th><th>10㎥あたり</th></tr></thead><tbody>{pref_rows}</tbody></table></div></div></details>
<section><h2>数字の根拠</h2><div class="note">
<p>数字はすべて、{e(SOURCE[0])}の令和6年度決算の事業者ごとの値です。順位と中央値は、家庭に直接給水する上水道事業（全国{a['n']:,}）で計算しました。簡易水道事業は含みません。</p>
<p>料金回収率は「供給単価 ÷ 給水原価 × 100」、水道管の割合は「法定耐用年数を経過した管路延長（または当年度に更新した管路延長）÷ 導送配水管延長 × 100」で計算しました。</p>
<p>料金はその後に改定されている場合があります。最新の料金は、お住まいの水道局のページで確かめてください。</p></div>
<ul class="sources"><li>出典：{e(SOURCE[0])}を加工して作成 <a href="{SOURCE[1]}" target="_blank" rel="noopener">{SOURCE[1]}</a></li></ul></section>
</main>"""
    desc = f"{a['name']}の水道料金は10㎥あたり{_yen(a['rate10'])}で全国{a['rank']}位。費用や水道管の古さなど、料金の背景を国の統計で。"
    return _page(f"{title} | {SITE_NAME}", body, desc, BASE_URL + a["slug"] + "/", 1)


def render_index(all_a: dict, released: set[str]) -> str:
    e = html.escape
    items = sorted(all_a.values(), key=lambda a: a["rank"])

    def tr(a):
        name = f"<a href=\"{a['slug']}/\">{e(a['name'])}</a>" if a["slug"] in released else e(a["name"])
        return f"<tr><td>{a['rank']}</td><th>{name}</th><td>{e(a['pref'])}</td><td>{_yen(a['rate10'])}</td></tr>"

    head = "<thead><tr><th>順位</th><th>事業者</th><th>都道府県</th><th>10㎥あたり</th></tr></thead>"
    top, low = "".join(tr(a) for a in items[:30]), "".join(tr(a) for a in items[-30:][::-1])
    rel = sorted((all_a[s] for s in released if s in all_a), key=lambda a: a["rank"])
    links = "".join(f"<li><a href=\"{a['slug']}/\"><b>{e(a['name'])}</b><span>{_yen(a['rate10'])}・全国{a['rank']}位</span></a></li>" for a in rel)
    med = items[0]["median"]["rate10"]
    body = f"""<main class="wrap"><h1>{SITE_NAME}</h1>
<p class="lead">市町村の水道料金を、全国{len(items):,}の水道事業と比べて「高いのか」「なぜなのか」を国の統計の数字で示します。家庭用の1か月10㎥あたりの全国の中央値は{_yen(med)}です。</p>
<section><h2>事業者ごとのページ</h2><ul class="index">{links}</ul></section>
<section><h2>水道料金が高い事業者（10㎥・上位30）</h2><div class="table-wrap"><table>{head}<tbody>{top}</tbody></table></div></section>
<section><h2>水道料金が安い事業者（10㎥・下位30）</h2><div class="table-wrap"><table>{head}<tbody>{low}</tbody></table></div></section>
<section><h2>数字の根拠</h2><p class="note">{e(SOURCE[0])}の令和6年度決算の事業者ごとの値です。家庭に直接給水する上水道事業（簡易水道事業を除く）で比べています。料金はその後に改定されている場合があります。</p></section></main>"""
    return _page(f"{SITE_NAME} — 市町村の水道料金は高い？全国の比較と理由", body,
                 "市町村の水道料金を全国の水道事業と比べ、高い理由を費用や水道管の古さなど国の統計で示します。", BASE_URL, 0)


ABOUT = ("<main class=\"wrap\"><h1>運営者情報</h1><p>水道料金のしくみは、市町村の水道料金が高いのか、なぜなのかを、"
         "国の統計（総務省「地方公営企業年鑑」）の数字で調べられるよう、個人で運営しているサイトです。</p>"
         "<p>数字は統計の値をそのまま使い、順位や中央値などを計算しています。評価や将来の予測はしていません。</p></main>")
PRIVACY = ("<main class=\"wrap\"><h1>プライバシーポリシー</h1><p>当サイトは、利用者の個人情報を集めるフォームを置いていません。</p>"
           "<p>今後、アクセス解析や広告（アフィリエイトを含む）を使う場合は、このページで内容をお知らせします。</p></main>")
EXTRA_CSS = """
.big{font-size:20px}.big b{font-size:30px;color:var(--peak)}.big small{color:var(--muted);font-size:13px;margin-left:6px}
.answer p{margin:0}
.scroll{overflow-x:auto}
table.cmp{border-collapse:collapse;width:100%;min-width:420px;font-size:15px}
table.cmp th{font-weight:500;color:var(--muted);text-align:left}
table.cmp td{font-weight:700;white-space:nowrap}
table.cmp td.med,table.cmp thead td{color:var(--muted);font-size:13px;font-weight:500}
"""


def load_released(path: Path = DATA / "release.csv") -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {r["slug"] for r in csv.DictReader(f) if r.get("released")}


def build_site(out: Path = SITE_OUT, data: Path = DATA, utilities: Path = UTILITIES) -> list[Path]:
    codes = load_codes(data / "jichitai_code.csv")
    all_a = analyze(load_end_utilities(utilities), codes)
    released = load_released(data / "release.csv")
    unknown = released - set(all_a)
    if unknown:
        raise ValueError(f"release.csv にデータの無い slug: {sorted(unknown)}")
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for slug in sorted(released):
        a = all_a[slug]
        pref_list = sorted([x for x in all_a.values() if x["pref"] == a["pref"]], key=lambda x: -x["rate10"])
        p = out / slug / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_utility(a, pref_list, released), encoding="utf-8")
        written.append(p)
    pages = {"index.html": render_index(all_a, released),
             "about/index.html": _page(f"運営者情報 | {SITE_NAME}", ABOUT, "運営者情報", BASE_URL + "about/", 1),
             "privacy/index.html": _page(f"プライバシーポリシー | {SITE_NAME}", PRIVACY, "プライバシーポリシー", BASE_URL + "privacy/", 1),
             "404.html": _page(f"ページが見つかりません | {SITE_NAME}",
                               '<main class="wrap"><h1>ページが見つかりません</h1><p><a href="/suido/">トップへ</a></p></main>',
                               "ページが見つかりません", BASE_URL, 0)}
    for name, text in pages.items():
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        written.append(p)
    urls = [BASE_URL] + [BASE_URL + s + "/" for s in sorted(released)] + [BASE_URL + "about/", BASE_URL + "privacy/"]
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                     + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}sitemap.xml\n", encoding="utf-8")
    css = Path(__file__).with_name("style.css").read_text(encoding="utf-8")
    (out / "style.css").write_text(css + EXTRA_CSS, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    static = data.parent / "static"
    if static.exists():
        for f in static.iterdir():
            if f.is_file():
                (out / f.name).write_bytes(f.read_bytes())
    return written
