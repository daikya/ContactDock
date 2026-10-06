import csv
import json
from dataclasses import replace
import pytest
from sqlcipher3 import dbapi2 as cipher
from contactdock.database import create_database, open_database
from contactdock.outlook_csv import HEADERS, read_outlook_csv
from contactdock.importer import save_csv_preview, DuplicateImportError

PASSWORD = 'fictional-import-password'


def preview(tmp_path, records, name='fictional.csv'):
    path = tmp_path / name
    with path.open('w', encoding='cp932', newline='') as f:
        w = csv.writer(f);w.writerow(HEADERS)
        for record in records:w.writerow([record.get(h,'') for h in HEADERS])
    return read_outlook_csv(path)


@pytest.fixture
def database(tmp_path):
    c = create_database(tmp_path/'fictional.db', PASSWORD)
    try:yield c
    finally:c.close()


def counts(c):
    return tuple(c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in
                 ('import_batches','contacts','contact_phones','contact_emails','contact_addresses'))


def test_save_all_values_and_original(tmp_path,database):
    p = preview(tmp_path,[{'姓':'架空','メモ':'展示会\r\n検索用','会社電話 2':'000-0123',
                         '電子メール 3 アドレス':'fictional@example.invalid','その他住所私書箱':'架空私書箱'}])
    result = save_csv_preview(database,p)
    assert result.contact_count == 1
    assert counts(database) == (1,1,1,1,1)
    row = database.execute('SELECT note,source_record_number,source_values_json,deleted_at FROM contacts').fetchone()
    assert row[:2] == ('展示会\r\n検索用',1)
    assert json.loads(row[2]) == list(p.contacts[0].raw_values)
    assert row[3] is None
    assert database.execute('SELECT kind,position,value FROM contact_phones').fetchone() == ('work_phone',2,'000-0123')
    assert database.execute('SELECT position FROM contact_emails').fetchone() == (3,)
    assert database.execute('SELECT kind,post_office_box FROM contact_addresses').fetchone() == ('other','架空私書箱')
    batch = database.execute('SELECT original_csv,headers_json,source_filename FROM import_batches').fetchone()
    assert batch[0] == p.original_csv
    assert json.loads(batch[1]) == list(p.headers)
    assert batch[2] == 'fictional.csv'


def test_duplicate_renamed_and_deleted_contacts(tmp_path,database):
    p = preview(tmp_path,[{'姓':'架空'}]);save_csv_preview(database,p)
    database.execute("UPDATE contacts SET deleted_at='fictional-date'");database.commit()
    before = counts(database)
    with pytest.raises(DuplicateImportError):
        save_csv_preview(database,replace(p,source_filename='renamed.csv'))
    assert counts(database) == before
    assert not database.in_transaction
    assert database.execute('SELECT deleted_at FROM contacts').fetchone()[0] == 'fictional-date'


def test_changed_csv_adds_without_updating(tmp_path,database):
    save_csv_preview(database,preview(tmp_path,[{'姓':'架空','メモ':'元のメモ'}]))
    save_csv_preview(database,preview(tmp_path,[{'姓':'架空','メモ':'変更メモ'}]))
    assert database.execute('SELECT note FROM contacts ORDER BY id').fetchall() == [('元のメモ',),('変更メモ',)]
    assert counts(database)[:2] == (2,2)


def test_failure_rolls_back_all_and_retry_works(tmp_path,database):
    save_csv_preview(database,preview(tmp_path,[{'姓':'既存架空'}],'existing.csv'))
    p = preview(tmp_path,[{'姓':'架空一','携帯電話':'000'},{'姓':'架空二','携帯電話':'001'}])
    before = counts(database)
    # Inject an actual database failure on the second contact, after child inserts of the first.
    database.execute("""CREATE TEMP TRIGGER simulated_failure BEFORE INSERT ON contacts
        WHEN NEW.source_record_number=2 BEGIN SELECT RAISE(ABORT,'simulated failure'); END""")
    with pytest.raises(cipher.IntegrityError):save_csv_preview(database,p)
    assert counts(database) == before
    assert not database.in_transaction
    assert database.execute('SELECT family_name FROM contacts').fetchall() == [('既存架空',)]
    database.execute('DROP TRIGGER simulated_failure')
    save_csv_preview(database,p)
    assert counts(database) == (2,3,2,0,0)


def test_existing_transaction_is_untouched(tmp_path,database):
    p = preview(tmp_path,[{'姓':'架空'}])
    database.execute("INSERT INTO contacts(created_at,updated_at,note) VALUES('now','now','pending')")
    with pytest.raises(ValueError,match='トランザクション'):save_csv_preview(database,p)
    assert database.in_transaction
    assert counts(database)[:2] == (0,1)
    database.rollback()
    assert counts(database)[:2] == (0,0)


def test_reopen_persists_import(tmp_path,database):
    p = preview(tmp_path,[{'会社名':'架空会社'}]);save_csv_preview(database,p)
    c = open_database(tmp_path/'fictional.db',PASSWORD)
    try:
        assert c.execute('SELECT company_name FROM contacts').fetchone() == ('架空会社',)
        with pytest.raises(DuplicateImportError):save_csv_preview(c,p)
    finally:c.close()


def test_warnings_keep_source_values(tmp_path,database):
    p = preview(tmp_path,[{'姓':'架空','優先度':'低','誕生日':'invalid'}])
    result = save_csv_preview(database,p)
    assert result.warning_count == 2
    assert database.execute('SELECT birthday FROM contacts').fetchone() == ('invalid',)
    assert json.loads(database.execute('SELECT source_values_json FROM contacts').fetchone()[0]) == list(p.contacts[0].raw_values)


def test_mismatched_hash_rejected_before_save(tmp_path,database):
    p = preview(tmp_path,[{'姓':'架空'}])
    with pytest.raises(ValueError,match='ハッシュ'):save_csv_preview(database,replace(p,source_sha256='wrong'))
    assert counts(database) == (0,0,0,0,0)


def test_disabled_foreign_keys_rejected(tmp_path,database):
    database.execute('PRAGMA foreign_keys=OFF')
    with pytest.raises(ValueError,match='外部キー'):save_csv_preview(database,preview(tmp_path,[{'姓':'架空'}]))
    assert counts(database) == (0,0,0,0,0)
