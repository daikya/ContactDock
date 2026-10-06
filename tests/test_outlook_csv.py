import csv
import hashlib
import json
import pytest
from contactdock.outlook_csv import HEADERS, read_outlook_csv, CsvValidationError


def write_csv(tmp_path, records, headers=HEADERS):
    path = tmp_path / 'fictional.csv'
    with path.open('w',encoding='cp932',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for record in records:
            writer.writerow([record.get(h,'') for h in headers])
    return path


def test_multiline_and_raw_retention(tmp_path):
    path = write_csv(tmp_path,[{'姓':'架空','名':'太郎','メモ':'  展示会,"確認"\r\n検索用メモ  '}])
    before = path.read_bytes()
    result = read_outlook_csv(path)
    assert result.original_csv == before == path.read_bytes()
    assert result.source_sha256 == hashlib.sha256(before).hexdigest()
    assert result.source_filename == 'fictional.csv'
    contact = result.contacts[0]
    assert contact.fields['note'] == '  展示会,"確認"\r\n検索用メモ  '
    assert contact.record_number == 1
    assert json.loads(contact.source_values_json)[HEADERS.index('メモ')] == contact.fields['note']


def test_second_phone_and_third_email_keep_position(tmp_path):
    result = read_outlook_csv(write_csv(tmp_path,[{'会社電話 2':'000-0123','電子メール 3 アドレス':'fictional@example.invalid'}]))
    contact = result.contacts[0]
    assert contact.phones == ({'kind':'work_phone','position':2,'value':'000-0123'},)
    assert contact.emails[0]['position'] == 3


def test_display_name_only_and_partial_address(tmp_path):
    result = read_outlook_csv(write_csv(tmp_path,[{'電子メール 2 表示名':'架空表示名','郵便番号 (会社)':'001-0000','その他住所私書箱':'架空私書箱'}]))
    contact = result.contacts[0]
    assert contact.emails[0]['address'] == ''
    assert contact.emails[0]['display_name'] == '架空表示名'
    assert contact.addresses[0]['postal_code'] == '001-0000'
    assert contact.addresses[1]['post_office_box'] == '架空私書箱'


@pytest.mark.parametrize('source,expected,warn', [('00/0/0','',False),('2000/2/29','2000-02-29',False),('2001/2/29','2001/2/29',True),('02/03/2000','02/03/2000',True)])
def test_birthday(tmp_path,source,expected,warn):
    result = read_outlook_csv(write_csv(tmp_path,[{'姓':'架空','誕生日':source}]))
    assert result.contacts[0].fields['birthday'] == expected
    assert any(w.code == 'unrecognized_date' for w in result.warnings) == warn


def test_reordered_headers(tmp_path):
    result = read_outlook_csv(write_csv(tmp_path,[{'姓':'架空'}],tuple(reversed(HEADERS))))
    assert result.contacts[0].fields['family_name'] == '架空'
    assert result.headers == tuple(reversed(HEADERS))


def test_unknown_and_raw_only_columns(tmp_path):
    result = read_outlook_csv(write_csv(tmp_path,[{'追加項目':'架空値','優先度':'低'}],HEADERS+('追加項目',)))
    assert {w.column for w in result.warnings} == {'追加項目','優先度'}
    assert '架空値' in result.contacts[0].raw_values


@pytest.mark.parametrize('headers',[HEADERS[:-1],HEADERS+('姓',)])
def test_invalid_headers(tmp_path,headers):
    with pytest.raises(CsvValidationError):
        read_outlook_csv(write_csv(tmp_path,[{'姓':'架空'}],headers))


def test_empty_record_rejected(tmp_path):
    with pytest.raises(CsvValidationError,match='全項目空欄'):
        read_outlook_csv(write_csv(tmp_path,[{}]))


def test_width_mismatch(tmp_path):
    path = write_csv(tmp_path,[{'姓':'架空'}])
    with path.open('a',encoding='cp932') as f:f.write('too,few\n')
    with pytest.raises(CsvValidationError,match='レコード2'):
        read_outlook_csv(path)


def test_unclosed_quote(tmp_path):
    path = write_csv(tmp_path,[])
    with path.open('a',encoding='cp932') as f:f.write('"unfinished')
    with pytest.raises(CsvValidationError,match='引用符'):
        read_outlook_csv(path)


def test_decode_failure(tmp_path):
    path = tmp_path/'invalid.csv';path.write_bytes(b'\x81')
    with pytest.raises(CsvValidationError,match='CP932'):
        read_outlook_csv(path)


def test_no_records(tmp_path):
    with pytest.raises(CsvValidationError,match='データレコード'):
        read_outlook_csv(write_csv(tmp_path,[]))
