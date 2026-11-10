"""毎日の公開: queue.csv で承認済み（approved に日付）の事業者を、まだ公開していないものから n 件 release.csv に足す。

  python -m generator.release --n 2      （GitHub Actions が毎朝実行）

承認されていない事業者は出さない。1 日に出す数は n で固定（増やすときは workflow を直す）。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

JST = dt.timezone(dt.timedelta(hours=9))


def pick(queue: list[dict], released: set[str], n: int) -> list[dict]:
    todo = [q for q in queue if q.get("approved", "").strip() and q["slug"] not in released]
    return sorted(todo, key=lambda q: int(q["order"]))[:n]


def release(data: Path = Path("data"), n: int = 2, today: str | None = None) -> list[dict]:
    today = today or dt.datetime.now(JST).date().isoformat()
    with open(data / "queue.csv", encoding="utf-8") as f:
        queue = list(csv.DictReader(f))
    with open(data / "release.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    released = {r["slug"] for r in rows if r.get("released")}
    if any(r.get("released") == today for r in rows):
        return []                                   # 同じ日に 2 回動いても増やさない
    new = pick(queue, released, n)
    with open(data / "release.csv", "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        for q in new:
            w.writerow([q["slug"], q["name"], today])
    return new


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=2)
    p.add_argument("--data", default="data")
    a = p.parse_args(argv)
    new = release(Path(a.data), a.n)
    print("released:", ", ".join(f"{q['name']}（{q['slug']}）" for q in new) or "なし（承認済みの残りが無いか、今日はもう公開済み）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
