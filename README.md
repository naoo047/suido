# 水道料金のしくみ

https://naoo047.github.io/suido/ — 市町村の水道料金は高い？全国の比較と理由（総務省「地方公営企業年鑑」より）

## 毎日の公開のしくみ
- 毎朝 9 時（日本時間）に GitHub Actions（`.github/workflows/publish.yml`）が動き、`data/queue.csv` で **approved に日付が入っている事業者**のうち、まだ公開していないものを **2 件** `data/release.csv` に足して、サイトを作り直します
- 承認していない事業者は出ません。承認済みが尽きたら、その日は何も増えません
- `main` に push したとき・Actions の画面から手で実行したときは、作り直すだけ（公開は進めない。手で進めるときは release を true に）

## 承認のしかた
`data/queue.csv` を開き、出してよい行の `approved` 列に日付（例 `2026-11-10`）を入れて保存（GitHub の画面やスマホのアプリからでも編集できます）。上から順番に（order の小さい順に）公開されます。

## 直してはいけないもの
- `generator/` は、手元の niche_finder から `nf water-sync` で写したもの。直すときは niche_finder 側を直して写し直す
- 数字は `data/utilities.csv`（年鑑から `nf water-import` で作る）。翌年度の年鑑が出たら取り込み直す
