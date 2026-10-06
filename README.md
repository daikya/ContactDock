# ContactDock

旧Outlookの連絡先資産をローカルで管理するWindowsデスクトップアプリ。
必要な機能・フォルダーだけを、その段階で追加する。

## Version 0.1.0

暗号化DBの作成、既存DBのオープン、最小5テーブルの初期化とpytest。
CSVの読取・構造検証・通常項目への変換まで対応。DBへの取込保存・GUI・検索・編集はこれから実装する。SQLCipherは0.6.3のPythonパッケージを使用。
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
