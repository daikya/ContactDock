# ContactDock

旧Outlookの連絡先資産をローカルで管理するWindowsデスクトップアプリ。
必要な機能・フォルダーだけを、その段階で追加する。

## Version 0.1.0

暗号化DBの作成、既存DBのオープン、最小5テーブルの初期化とpytest。
CSVの読取・構造検証・通常項目への変換まで対応。暗号化DBへの一括取込保存まで対応。一覧取得まで対応。メモを含む検索まで対応。GUI・編集はこれから実装する。SQLCipherは0.6.3のPythonパッケージを使用。
Python 3.12を検証対象とする。

## Windowsでの準備と検証

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

実データ、DB、CSV、PST、パスワードはGit管理しない。
テストは架空データを一時フォルダーへ作成する。
誤パスワードを試すためSQLCipherのhmacエラーが表示される場合がある。

## 開発方針

コミットはdocs/feat/fix/refactor/test/style/choreのprefix、日本語常体、1コミット1テーマ。
旧Outlook項目の対応と設計判断は[対応表](docs/Outlook_Field_Mapping.md)に残す。
接続は呼び出し元でcloseする。パスワードをログやコードへ保存しない。
暗号化は保存ファイルを保護するもので、実行中の端末全体を保護するものではない。
正式配布前にSQLCipherおよび依存ライブラリのライセンス表示を整備する。

## Outlook CSVの読取

`contactdock.outlook_csv.read_outlook_csv(path)`は入力を変更せず、元バイト列・列順・元値・変換済み項目・警告を返す。DBへ保存しない。
今回の95列のヘッダーをすべて要求し、列順の違いは許容する。未知列も元値へ保持し、非空値は警告する。
CP932以外の文字コードは当初の対応対象外。警告や結果には個人情報が含まれうるため、結果全体をログへ出力しない。
単体検証：`python -m pytest -q tests/test_outlook_csv.py`。

## CSVの一括保存

`contactdock.importer.save_csv_preview(connection, preview)`は、読取結果を一つのトランザクションで保存する。
取込実行前に利用側で件数・警告を確認すること。GUIの確認画面は未実装。
同一CSVは`DuplicateImportError`で拒否し、変更CSVは新規追加する。保存失敗時は全体をロールバックする。
呼び出し前に既存のトランザクションを終了し、外部キー検証を有効にする。
単体検証：`python -m pytest -q tests/test_importer.py`。

## 一覧取得

`contactdock.repository.list_contacts(connection)`は削除されていない連絡先を1件1行で返す。
氏名、会社名、部署、役職、会社電話1、携帯電話1、第1メールを含む。第2値で第1値を補わない。
並び順は姓の読み（なければ姓）、名の読み（なければ名）、内部ID。厳密な日本語五十音順ではない。
読み取りだけを行い、呼び出し元のトランザクションを確定しない。
単体検証：`python -m pytest -q tests/test_repository.py`。

## 連絡先検索

`contactdock.repository.search_contacts(connection, query)`は、氏名・読み・会社名・会社名の読み・部署・役職・メモ・すべての電話等・メールアドレスを部分一致で検索する。
検索語の前後空白は除去し、空なら通常一覧を返す。姓と名は空白あり／なしの連結でも検索できる。
保存値を変えず、英字の大文字小文字、全角半角の英数字・カタカナを比較時に揃える。ひらがなとカタカナは区別する。
電話項目だけ、ハイフン類・空白・括弧を無視した数字の追加比較を行う。
メモの改行をまたぐ一致は行わない。%や_はワイルドカードではなく文字として扱う。
住所・Webページ・誕生日・移行元情報は検索対象外。削除済みも除外する。
単体検証：`python -m pytest -q tests/test_search.py`。
