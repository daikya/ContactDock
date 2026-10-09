# ContactDock

旧Outlookの連絡先資産をローカルで管理するWindowsデスクトップアプリ。
必要な機能・フォルダーだけを、その段階で追加する。

## Version 0.1.0

暗号化DBの作成、既存DBのオープン、最小5テーブルの初期化とpytest。
CSVの読取・構造検証・通常項目への変換まで対応。暗号化DBへの一括取込保存まで対応。一覧取得まで対応。メモを含む検索まで対応。詳細取得まで対応。最小Tkinter GUIまで対応。新規登録・編集まで対応。確認後の削除（内部データ保持）まで対応。SQLCipherは0.6.3のPythonパッケージを使用。
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
第三者ライセンスの一覧と原文を配布ZIPへ同梱する（下記の配布手順参照）。

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

## 詳細取得

`contactdock.repository.get_contact(connection, contact_id)`は通常項目と全電話・メール・住所、移行元の項目名・元値を返す。
存在しないIDや削除済みの連絡先は`None`を返す。新規登録した連絡先の移行元は`None`。
電話は種類・順序、メールは元の順序、住所は会社・自宅・その他の順に返す。
元CSV全体のBLOBは詳細取得では読み込まない。移行後の編集値と元値を分けて確認できる。
単体検証：`python -m pytest -q tests/test_detail.py`。

## 最小GUIの起動

```powershell
.\.venv\Scripts\python.exe -m contactdock
```

1. ［DB新規作成］で新しい.dbファイルを指定し、パスワードを2回入力する。既存ファイルは上書きしない。
2. ［CSV取込］でOutlookのCP932 CSVを選ぶ。件数と確認事項を読み、実行する。
3. 一覧で選ぶと［詳細］に全電話・メール・住所・メモ、［移行元］に元項目名・元値が表示される。
4. 検索欄に入力しEnterまたは［検索］で検索する。［クリア］で全件表示へ戻る。
5. ウィンドウを閉じ、再起動して［DBを開く］から同じDBをパスワードで開く。

GUIは閲覧・取込・新規登録・編集に対応。パスワード変更の画面は未実装。
パスワードはアプリに保存しない。復旧機能は未実装のため、設定したパスワードを忘れないよう管理する。
GUI表示の配置・スクロールはWindowsで手動確認する。GUI処理のpytestは実画面を生成せず、取込確認とキャンセル等を検証する。

## 新規登録・編集

DBを開いた後、［新規登録］で入力画面を開く。一覧で連絡先を選ぶと［編集］が使える。
入力画面は共通で、氏名・所属、メモ、電話・FAX等、メール、住所のタブを持つ。
姓・名は必須ではなく会社名だけでも保存できる。全項目が空白なら保存できない。
電話・メールは［追加］で増やし、種類・順序と値を入力する。行の［削除］はその入力画面内の項目を外す操作で、［保存］まではDBへ反映しない。
同じ種類・順序の電話、同じ順序のメール、同じ区分の住所の重複は拒否する。番号自体の共有は許容する。
住所は会社・自宅・その他を分ける。郵便番号・電話番号は文字列のまま保存する。
誕生日は手入力の文字列として保持する（例：2000-02-29）。フリガナの自動生成は行わない。
［保存］後は全件一覧に戻り、保存した連絡先を選択する。［キャンセル］・閉じる・Escでは保存しない。
編集してもOutlookの元値とCSV原本は変更しない。メモを触らなかった場合は元の改行形式も保持する。
保存失敗時は入力画面を閉じず内容を残す。別の編集による更新を検出した場合も無断で上書きしない。
既存DBのテーブル変更はないため、以前作成したDBをそのまま開ける。

保存処理：`contactdock.service.save_contact(connection, draft, contact_id=None, expected_updated_at=None)`。
更新時には詳細取得時のupdated_atを指定する。氏名・電話・メールの一致による自動統合はしない。
単体検証：`python -m pytest -q tests/test_service.py tests/test_editor.py tests/test_gui_flow.py`。

## 連絡先の削除

一覧で連絡先を選び［削除］を押す。確認画面の氏名・会社名・IDを確認して実行する。
削除日時を記録して一覧・検索・通常の詳細取得から除外し、関連項目と移行元情報はDB内に保持する。
キャンセルでは変更しない。復元画面・完全削除は未実装。同一CSVの再取込では復元しない。
確認中に他の操作で連絡先が更新・削除された場合は、無断で削除せず再確認を求める。
単体検証：`python -m pytest -q tests/test_delete.py tests/test_gui_flow.py`。

## 更新ZIPの配置

アプリを終了し、ZIP内のContactDockフォルダーを開発環境の親フォルダーへコピーする。
Windowsエクスプローラーのフォルダー統合で同名ファイルは［置き換える］を選ぶ。
ZIPに含まれない既存ファイル・フォルダーは削除されない。ContactDockの中へフォルダーごと入れると二重になるため避ける。

## CSVエクスポート

［現在の連絡先をCSV出力］は、削除済みを除く全連絡先を出力する（現在の検索結果に限定しない）。
形式はContactDock CSV／UTF-8 BOM付き、1件1行。氏名・所属・メモ・Webページ・誕生日・登録／更新日時・内部IDと全電話・メール・住所を出す。
電話・メールは実データに応じて列を増やすため、会社電話3やメール4以降も省略しない。メモの改行・引用符・空白、先頭ゼロもファイル中の文字列として保持する。
このCSVは旧Outlookの95列CP932形式ではなく、CSV取込から新しい連絡先として再取込できる。移行元だけの項目は現在値へ混ぜない。

［移行元CSV原本を出力］は保存済みの元バイト列をそのまま再出力する。複数の取込単位がある場合は選択する。
取込後の編集は反映されず、取込後に削除した連絡先も原本には含まれる。元の文字コード・引用符・改行も保持する。
どちらも出力ファイルは暗号化されないため、確認画面を表示する。暗号化DB全体のバックアップとは用途が異なる。
使用中のDBと補助ファイルへの出力は拒否する。書込みは同じ保存先の一時ファイルから置換し、書込み失敗時に既存出力を壊さない。
APIでは既存ファイルの上書きはデフォルトで拒否し、GUIでは保存先選択と出力確認後に許可する。
単体検証：`python -m pytest -q tests/test_exporter.py tests/test_gui_flow.py`。

### 暗号化DB全体のバックアップ

DBを開いた状態で「暗号化DBをバックアップ」を押し、保存先と現在のDBのパスワードを指定します。現在の連絡先、削除済みデータ、電話・メール・住所、取込履歴、移行元CSV原本をまとめて保存します。検索条件による絞り込みはありません。

バックアップも暗号化され、作成時点の同じパスワードで「DBを開く」から利用できます。元DBのパスワードを後から変更しても、既に作成したバックアップのパスワードは変わりません。保存後の編集はバックアップへ反映されません。バックアップを開くと、そのファイルを直接編集します。復旧時は必要に応じてコピーしてから開いてください。

SQLCipherのオンラインバックアップで確定済みデータを保存し、暗号化・DB・参照関係の整合性を検証してから保存先を置き換えます。使用中のDBと補助ファイルへの上書きは禁止します。未確定のトランザクションがある場合は処理しません。パスワードはアプリの属性や設定ファイルへ保存しません。

### DBパスワードの変更

DBを開き、「DBパスワード変更」を押します。現在のパスワード、新しいパスワード、新しいパスワードの再入力を行い、確認画面で変更します。空または空白だけのパスワード、現在と同じパスワードは使用できません。入力の前後の空白は自動で削除しません。

SQLCipherの `PRAGMA rekey` で暗号化を変更し、新しいパスワードで別接続を開いて整合性を確認します。連絡先、削除済みデータ、移行元情報は保持され、変更後もそのまま編集できます。次回は新しいパスワードで開いてください。既に作成したバックアップは、作成時のパスワードのままです。変更前に必要に応じてバックアップを保存してください。

変更処理や変更後の検証でエラーが起きた場合、変更できていないとは断定せず、DBを閉じて開き直すよう案内します。まず新しいパスワード、開けない場合は元のパスワードで確認してください。通常のContactDock DB（DELETEジャーナルモード）が対象で、WALモードや未確定のトランザクションがある場合は変更しません。

### 画面位置とDB保存先の設定

メイン画面、新規登録・編集画面、移行元CSV選択画面、パスワード入力画面は、初回は中央に表示します。メイン画面は主画面、サブ画面は親画面のあるモニターの中央に表示します。画面ごとの通常表示時の位置とサイズを保存し、次回の表示に反映します。新規登録と編集は同じ位置設定を使います。最大化・最小化中の位置やサイズは記録しません。モニターを外した場合など、記録した位置が画面外なら中央へ戻します。

設定ファイルは Windows では `%APPDATA%\ContactDock\settings.json` です。アプリやDBのフォルダへ設定ファイルを置く必要はありません。画面を閉じたとき、またはDBを正常に開いたときに設定を保存します。設定がない場合やJSONが壊れている場合は初期設定で起動します。

正常に作成・開いたDBのフルパスとフォルダを記録し、次回の「DBを開く」はそのフォルダとファイル名、「DB新規作成」はそのフォルダを初期選択します。設定したフォルダが存在しない場合は通常のファイル選択へ戻ります。DBは自動で開かず、パスワード入力は毎回必要です。パスワードと連絡先の内容はJSONへ保存しません。

Windows標準のファイル選択・確認ダイアログはWindows側の位置制御を使用し、その位置はこのJSONへ保存しません。

## Windows本体exeのビルドと検証

Windows上のPython 3.12仮想環境でビルドします。`run_contactdock.py` は本体GUIを起動する専用入口です。SQLCipher検証用exeで確認したPyInstaller 6.22.3をビルド用追加依存に固定します。

```powershell
cd C:\Users\takesuzu\MyPythonCode\ContactDock
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m PyInstaller --clean --onedir --console --noupx --collect-all sqlcipher3 --icon contactdock/assets/contactdock.ico --add-data "contactdock/assets:contactdock/assets" --name ContactDockConsole run_contactdock.py
.\dist\ContactDockConsole\ContactDockConsole.exe
```

まずコンソール付きで確認します。アプリを終了するまでPowerShellへ戻らない場合があります。誤パスワードや変更前のパスワードを試したときのSQLCipherのHMACエラーは想定されるログです。起動失敗のトレースバックとは区別します。

exeで確認する項目：

1. 起動し、メイン・サブ画面の位置とサイズが復元される。
2. 確認用DBの新規作成、既存DBの正しい／誤ったパスワードでのオープンができる。
3. 確認用CSVの取込、メモ検索、詳細・移行元表示ができる。
4. 新規登録・編集・削除と、現在のCSV／原本CSVの出力ができる。
5. 暗号化バックアップを作成し、同じパスワードで開ける。
6. パスワード変更後に終了・再起動し、新しいパスワードで開ける。
7. 終了・再起動後に画面位置とDB選択先が復元される。

開発用とexeは同じ `%APPDATA%\ContactDock\settings.json` を利用します。DBのパスは設定に記録した元の場所を参照します。exeのフォルダを移動してもDB自体は移動しません。

コンソール付きexeを閉じた後、フォルダを丸ごと別の場所へコピーします。

```powershell
$contactDockMoveFolder = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ContactDock移動確認'
New-Item -ItemType Directory -Path $contactDockMoveFolder
Copy-Item .\dist\ContactDockConsole -Destination $contactDockMoveFolder -Recurse
& (Join-Path $contactDockMoveFolder 'ContactDockConsole\ContactDockConsole.exe')
```

移動先ではエクスプローラーからexeをダブルクリックしても起動すること、DB・設定が引き続き利用できることを確認します。`_internal` などの付属ファイルも必要なので、exe単体ではなく `ContactDockConsole` フォルダ全体をコピーします。フォルダ移動の確認だけでは、Python未導入PCでの動作確認を済ませたことにはなりません。

上記の確認後、通常版を作成します。

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --onedir --windowed --noupx --collect-all sqlcipher3 --icon contactdock/assets/contactdock.ico --add-data "contactdock/assets:contactdock/assets" --name ContactDock run_contactdock.py
.\dist\ContactDock\ContactDock.exe
```

通常版でも上記の各項目とフォルダ移動を確認します。`dist\ContactDock` 全体が配布対象です。ビルド生成物、DB、CSV、個人の設定JSONはGitへ追加しません。再ビルド時に出力フォルダの置き換え確認が出たら、exeを閉じ、出力内に保存したDB等がないことを確認してから続けます。配布時は下記の配布ZIP作成スクリプトでライセンス原文と利用者向け文書を同梱します。

参考：[PyInstaller公式の使い方](https://pyinstaller.org/en/stable/usage.html)


### ContactDock出力CSVの再取込

UTF-8（BOM付き）のContactDock出力CSVと、従来のCP932 Outlook CSVをCSV取込で判別します。氏名、メモ、電話、メール、住所、誕生日は現在値として取り込みます。電話・メールの追加順序列も保持します。元の連絡先ID・登録日時・更新日時は移行元情報に残し、新しいIDと取込時の日時を付けて追加します。既存連絡先は更新しません。元DBへ再取込すると重複するため、確認画面で追加先を確認してください。同一ファイルの二度目の取込は拒否します。

CSVでは削除済みデータや元のOutlook取込履歴を復元できません。DB全体の復元は暗号化バックアップを使用してください。取込後に「移行元CSV原本を出力」すると、今回取り込んだContactDock CSVをそのまま出力できます。


### アプリアイコン

`contactdock/assets/contactdock.ico` は人物と鍵を組み合わせたContactDockのアイコンです。16～256ピクセルの7サイズを収録します。Windowsの画面アイコンとexeアイコンに使用し、ビルド時は `--icon` と `--add-data` で本体へ組み込みます。

## ライセンス同梱と配布ZIPの作成

同梱する第三者ソフトウェアの一覧は `THIRD_PARTY_NOTICES.md`、ライセンス原文は `licenses/` にあります。Python本体のライセンスは、配布ZIP作成時にビルド環境の `LICENSE.txt` をコピーします。Tcl/Tkは実際のビルドに `license.terms` があれば優先してコピーします。依存関係やビルド環境を変更した場合は、実際の配布物に含まれるライブラリとライセンスを再確認します。ContactDock本体の公開ライセンスは、これら第三者ライセンスとは別に決めます。

検証済みの通常版 `dist\ContactDock` を元に配布ZIPを作成します。exeは閉じておき、DBやCSVはビルド済みフォルダの外へ保存してください。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe package_release.py
```

標準の出力は `dist\ContactDock-0.1.0-windows-x64.zip` と、そのSHA-256を記録した `.zip.sha256` です。ZIP内は `ContactDock/` 直下にexe、`_internal`、利用者向けREADME、第三者ライセンス一覧、`licenses/`、ビルド情報をまとめます。Python・SQLCipher等の版は `BUILD_INFO.json` に記録します。

DB、CSV、PST、個人の設定JSON、開発用フォルダ、外部参照、ビルド直下の追加ファイルを検出すると作成を中止します。元のビルドは変更せず、一時フォルダで配布物を組み立てます。同名のZIPやSHA-256ファイルは上書きしません。再作成時は別名を指定できます。

```powershell
.\.venv\Scripts\python.exe package_release.py --output .\dist\ContactDock-0.1.0-windows-x64-check2.zip
```

ZIPは別のフォルダへ展開し、exeの起動、アイコン、DBのオープン・検索・保存、設定の復元を確認します。ライセンス一覧と原文が展開先で読めることも確認してください。ZIPにはソース、仮想環境、DB、CSV、個人の設定ファイルを同梱しません。ZIPとSHA-256ファイルを配布時の組にします。

```powershell
Get-FileHash .\dist\ContactDock-0.1.0-windows-x64.zip -Algorithm SHA256
Get-Content .\dist\ContactDock-0.1.0-windows-x64.zip.sha256
```

注意：配布ZIPの作成・展開確認と、Python未導入の別PCでの動作確認は別です。これまでに確認した同一PC上のフォルダ移動だけで、別PCでの動作を保証したことにはしません。
