# 日本株 高配当トラッカー

高配当の日本株をカード形式で一覧・分析できるWebアプリ。GitHub Pagesでホストし、GitHub Actionsで平日3回（JST 11:35 / 15:35 / 18:00）自動更新される。

## 構成

| ファイル | 役割 |
|---|---|
| `index.html` | 画面本体（Vanilla JS） |
| `data/stocks_list.csv` | 対象銘柄リスト（`コード,日本語名`、ヘッダーなし） |
| `data/stocks.json` | 取得済みデータ（スクリプトが出力、Git管理） |
| `scripts/fetch_stocks.py` | yfinanceでデータ取得 |
| `scripts/translate_names.py` | 銘柄名・セクターの日本語化 |
| `.github/workflows/update.yml` | 自動更新（平日3回） |

## 公開手順（GitHubのWeb画面だけで完了・コマンド不要）

1. GitHubにログイン → 右上「＋」→「New repository」
2. リポジトリ名（例 `kabu-tracker`）を入力し、**Public** を選んで作成
   - ※Publicにする必要があるのは GitHub Pages 無料枠の仕様。**このリポジトリに個人情報は含まれない**（保有銘柄・投資額・メモはブラウザ内にのみ保存される）
3. 「uploading an existing file」リンクから、このフォルダの中身を**全部ドラッグ＆ドロップ**してCommit
   - `.github` フォルダが見えない場合はFinderで `Cmd+Shift+.`（隠しファイル表示）
4. リポジトリの Settings → Pages → Branch を `main` / `(root)` にして Save
5. 数分後に `https://ユーザー名.github.io/kabu-tracker/` で公開される
6. Actionsタブ → ワークフローを有効化（初回に「I understand…」ボタンが出たら押す）

## 銘柄の追加・削除

`data/stocks_list.csv` に1行1銘柄で追記（例：`8306,三菱UFJフィナンシャル・グループ`）。
GitHubのWeb画面で直接編集してCommitすれば、次回の自動更新から反映される。

## ローカルでのデータ更新（任意）

```bash
pip3 install --user yfinance
python3 scripts/fetch_stocks.py
python3 scripts/translate_names.py
```

※ `index.html` は `file://` 直開きではデータを読めない（ブラウザの制約）。ローカルで見るときは `python3 -m http.server` を実行して http://localhost:8000 を開く。

## データの注意

- 配当利回り20%以上は取得異常とみなし「-」表示・集計/ランキングから除外
- 保有タグ・投資額・購入時利回り・メモ・手動上書きはすべてlocalStorage（このブラウザ内）に保存。ブラウザを変えると引き継がれない
- 投資判断は自己責任で。データはyfinance（Yahoo Finance）由来で遅延・欠損があり得る
