"""Read and validate Outlook CSV without writing to a database."""
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

HEADERS = ('肩書き', '名', 'ミドル ネーム', '姓', '敬称', '会社名', '部署', '役職', '番地 (会社)', '住所 2 (会社)', '住所 3 (会社)', '市町村 (会社)', '都道府県 (会社)', '郵便番号 (会社)', '国 (会社)/地域', '番地 (自宅)', '住所 2 (自宅)', '住所 3 (自宅)', '市町村 (自宅)', '都道府県 (自宅)', '郵便番号 (自宅)', '国 (自宅)/地域', '番地 (その他)', '住所 2 (その他)', '住所 3 (その他)', '市町村 (その他)', '都道府県 (その他)', '郵便番号 (その他)', '国 (その他)/地域', '秘書の電話', '会社 FAX', '会社電話', '会社電話 2', 'コールバック', '自動車電話', '会社代表電話', '自宅 FAX', '自宅電話', '自宅電話 2', 'ISDN', '携帯電話', 'その他の FAX', 'その他の電話', 'ポケットベル', '通常の電話', '無線電話', 'TTY/TDD', 'テレックス', 'ID 番号', 'Web ページ', 'アカウント', 'イニシャル', 'インターネット空き時間情報', 'キーワード', 'その他住所私書箱', 'ディレクトリ サーバー', 'プライベート', 'マネージャー', 'メモ', 'ユーザー 1', 'ユーザー 2', 'ユーザー 3', 'ユーザー 4', '会社 ID', '会社住所私書箱', '会社名フリガナ', '記念日', '経費情報', '言語', '参照事項', '子供', '支払い条件', '事業所', '自宅住所私書箱', '趣味', '場所', '職業', '姓フリガナ', '性別', '誕生日', '電子メール アドレス', '電子メールの種類', '電子メール表示名', '電子メール 2 アドレス', '電子メール 2 の種類', '電子メール 2 表示名', '電子メール 3 アドレス', '電子メール 3 の種類', '電子メール 3 表示名', '配偶者', '秘書の氏名', '秘密度', '分類', '名前フリガナ', '優先度')
FIELDS = {
    '姓': 'family_name', '名': 'given_name', '姓フリガナ': 'family_name_kana',
    '名前フリガナ': 'given_name_kana', '会社名': 'company_name',
    '会社名フリガナ': 'company_name_kana', '部署': 'department',
    '役職': 'job_title', 'メモ': 'note', 'Web ページ': 'web_page',
}
PHONES = {
    '会社電話': ('work_phone', 1), '会社電話 2': ('work_phone', 2),
    '会社代表電話': ('company_main_phone', 1), '会社 FAX': ('work_fax', 1),
    '自宅電話': ('home_phone', 1), '自宅電話 2': ('home_phone', 2),
    '携帯電話': ('mobile_phone', 1), 'その他の電話': ('other_phone', 1),
    'その他の FAX': ('other_fax', 1), '無線電話': ('radio_phone', 1),
    'テレックス': ('telex', 1),
}


class CsvValidationError(ValueError):
    """Malformed or unsupported input; message does not contain contact values."""


@dataclass(frozen=True)
class ImportWarning:
    record_number: int | None
    column: str
    code: str


@dataclass(frozen=True)
class ParsedContact:
    record_number: int
    raw_values: tuple[str, ...]
    fields: dict[str, str]
    phones: tuple[dict, ...]
    emails: tuple[dict, ...]
    addresses: tuple[dict, ...]

    @property
    def source_values_json(self):
        return json.dumps(self.raw_values, ensure_ascii=False)


@dataclass(frozen=True)
class CsvPreview:
    source_filename: str
    source_encoding: str
    source_sha256: str
    headers: tuple[str, ...]
    original_csv: bytes
    contacts: tuple[ParsedContact, ...]
    warnings: tuple[ImportWarning, ...]


def _birthday(value, record_number, warnings):
    if not value.strip() or value.strip() == '00/0/0':
        return ''
    match = re.fullmatch(r'(\d{4})([/\-])(\d{1,2})\2(\d{1,2})', value)
    if match:
        try:
            return date(int(match[1]), int(match[3]), int(match[4])).isoformat()
        except ValueError:
            pass
    warnings.append(ImportWarning(record_number, '誕生日', 'unrecognized_date'))
    return value


def _contact(values, headers, number, warnings):
    row = dict(zip(headers, values))
    fields = {target: row[source] for source, target in FIELDS.items()}
    fields['birthday'] = _birthday(row['誕生日'], number, warnings)
    phones = tuple({'kind': kind, 'position': position, 'value': row[source]}
                   for source, (kind, position) in PHONES.items() if row[source].strip())
    emails = []
    for position in (1, 2, 3):
        cols = ('電子メール アドレス', '電子メール表示名', '電子メールの種類') if position == 1 else (
            f'電子メール {position} アドレス', f'電子メール {position} 表示名', f'電子メール {position} の種類')
        address, display_name, source_type = (row[c] for c in cols)
        if any(value.strip() for value in (address, display_name, source_type)):
            emails.append(dict(position=position, address=address, display_name=display_name, source_type=source_type))
            if address.strip() and not re.fullmatch(r'[^\s@]+@[^\s@]+', address):
                warnings.append(ImportWarning(number, cols[0], 'unrecognized_email'))
    addresses = []
    for label, kind in (('会社', 'work'), ('自宅', 'home'), ('その他', 'other')):
        columns = {'country_region': f'国 ({label})/地域', 'postal_code': f'郵便番号 ({label})',
                   'prefecture': f'都道府県 ({label})', 'city': f'市町村 ({label})',
                   'street': f'番地 ({label})', 'post_office_box': f'{label}住所私書箱'}
        parts = {key: row[col] for key, col in columns.items()}
        if any(value.strip() for value in parts.values()):
            addresses.append(dict(kind=kind, **parts))
    represented = set(FIELDS) | set(PHONES) | {'誕生日'}
    represented.update(c for c in headers if c.startswith('電子メール'))
    for label in ('会社', '自宅', 'その他'):
        represented.update((f'国 ({label})/地域', f'郵便番号 ({label})', f'都道府県 ({label})',
                            f'市町村 ({label})', f'番地 ({label})', f'{label}住所私書箱'))
    defaults = {'記念日': '00/0/0', '性別': '指定なし', 'プライベート': 'False', '秘密度': '標準', '優先度': '標準'}
    for col, value in row.items():
        if col not in represented and value.strip() and value.strip() != defaults.get(col):
            warnings.append(ImportWarning(number, col, 'raw_only_field'))
    return ParsedContact(number, tuple(values), fields, phones, tuple(emails), tuple(addresses))


def read_outlook_csv(path):
    """Return a validated in-memory preview; never save or change input files."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode('cp932', errors='strict')
    except UnicodeDecodeError:
        raise CsvValidationError('CP932として読み取れません。') from None
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    warnings = []
    contacts = []
    try:
        headers = next(reader, None)
        if headers is None:
            raise CsvValidationError('CSVが空です。')
        if len(set(headers)) != len(headers):
            raise CsvValidationError('ヘッダー名が重複しています。')
        missing = set(HEADERS) - set(headers)
        if missing:
            raise CsvValidationError(f'必要なOutlook項目が{len(missing)}列不足しています。')
        for number, values in enumerate(reader, 1):
            if len(values) != len(headers):
                raise CsvValidationError(f'データレコード{number}の列数がヘッダーと一致しません。')
            if not any(value.strip() for value in values):
                raise CsvValidationError(f'データレコード{number}が全項目空欄です。')
            contacts.append(_contact(values, headers, number, warnings))
    except csv.Error:
        raise CsvValidationError('CSVの引用符・レコード構造が不正です。') from None
    if not contacts:
        raise CsvValidationError('連絡先のデータレコードがありません。')
    return CsvPreview(path.name, 'cp932', hashlib.sha256(raw).hexdigest(), tuple(headers), raw,
                      tuple(contacts), tuple(warnings))
