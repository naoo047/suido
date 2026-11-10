# このファイルは niche_finder から nf water-sync で写したもの。直接直さない。
"""水道料金のしくみ: 総務省「地方公営企業年鑑」水道事業（事業別）を取り込み、事業者ごとの表を作る。

  nf water-import data/water/001064895.xls  →  themes/water/data/utilities.csv

表は「列＝事業者、行＝項目」。行の位置は年度で変わりうるので、項目名（左の 5 列をつなげた文字）で探す。
.xls の読み込みには xlrd（2.0.1）が要る。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

OUT = Path("data/utilities.csv")

# 取り出す項目: 列名 → 項目名に含まれる文字（最初に一致した行）
FIELDS = {
    "population": "（３）現在給水人口",
    "rate10": "エ．10m３当たり料金",
    "base_volume": "ア．基本水量",
    "base_fee": "イ．基本料金",
    "over_fee": "ウ．超過料金",
    "rate_date": "（２）現行料金実施年月日",
    "rate_system": "（３）料金体系",
    "pipe_km": "（８）導送配水管延長",
    "pipe_aged_km": "うち法定耐用年数を経過した管路延長",
    "pipe_renewed_km": "うち当該年度に更新した管路延長",
    "revenue_water_pct": "（１）有収率",
    "pipe_efficiency": "（５）配水管使用効率",
    "supply_unit": "（10）供給単価",
    "cost_unit": "（11）給水原価",
    "c_salary": "（１）職員給与費",
    "c_interest": "（２）支払利息",
    "c_depreciation": "（３）減価償却費",
    "c_power": "（４）動力費",
    "c_repair": "（７）修繕費",
    "c_outsourcing": "（11）委託料",
    "c_purchased_water": "（12）受水費",
    "c_total": "（15）費用合計",
}
FIRST_COL = 7
COLUMNS = ["id", "operator", "business", "form", "pref", "name"] + list(FIELDS)


def _label_rows(sheet) -> dict[str, int]:
    """項目名 → 行番号。同じ名前が複数あるとき（「（１）」など）は、より上の大見出しで区別できないので最初の行。"""
    rows = {}
    for r in range(sheet.nrows):
        lab = "".join(str(v).strip() for v in sheet.row_values(r)[:6])
        if lab:
            rows.setdefault(lab, r)
    return rows


def _find(rows: dict[str, int], key: str, after: int = 0) -> int | None:
    hits = sorted(r for lab, r in rows.items() if key in lab and r >= after)
    return hits[0] if hits else None


def _num(v):
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if s in ("", "-", "－", "…"):
        return ""
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return s


def parse(xls: str | Path) -> list[dict]:
    import xlrd
    book = xlrd.open_workbook(str(xls))
    out = []
    for si, sh in enumerate(book.sheets()):
        if sh.nrows < 50:
            continue
        rows = _label_rows(sh)
        # 「（１）」などの小見出しは大見出しの後ろから探す（料金・経営分析・1㎥当たりの金額）
        anchors = {"料金": _find(rows, "８．料金") or 0, "経営": _find(rows, "10．経営分析") or 0,
                   "金額": _find(rows, "11．有収水量１m３当たりの金額") or 0}
        where = {}
        for col, key in FIELDS.items():
            after = (anchors["金額"] if col.startswith("c_") else
                     anchors["経営"] if col in ("revenue_water_pct", "pipe_efficiency", "supply_unit", "cost_unit") else
                     anchors["料金"] if col in ("rate10", "base_volume", "base_fee", "over_fee", "rate_date", "rate_system") else 0)
            where[col] = _find(rows, key, after)
        for c in range(FIRST_COL, sh.ncols):
            operator, business, pref = (str(sh.cell_value(r, c)).strip() for r in (3, 4, 5))
            name = str(sh.cell_value(6, c)).strip() or pref
            form = str(sh.cell_value(8, c)).strip().split(".")[0]
            if not business:
                continue
            rec = {"id": f"{si}-{c}", "operator": operator, "business": business, "form": form,
                   "pref": pref, "name": name}
            for col, r in where.items():
                rec[col] = _num(sh.cell_value(r, c)) if r is not None else ""
            out.append(rec)
    return out


def write(records: list[dict], out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    return out


def parse_members(xls: str | Path) -> dict[tuple[str, str], list[str]]:
    """付表「一部事務組合構成団体一覧表」: (都道府県, 企業団名) → 構成団体（市町村）"""
    import xlrd
    sh = xlrd.open_workbook(str(xls)).sheet_by_index(0)
    out: dict[tuple[str, str], list[str]] = {}
    pref = key = None
    for r in range(sh.nrows):
        p, name, kind, members = (str(v).strip() for v in sh.row_values(r)[1:5])
        if p and p != "都道府県名":
            pref = p
        if name and name != "名称":
            key = (pref, name)
            out[key] = []
        if key and members:
            out[key] += [m for m in re.split(r"[、,，]\s*", members) if m]
    return out
