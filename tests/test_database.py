import hashlib
import sqlite3
import pytest
from sqlcipher3 import dbapi2 as cipher
from contactdock.database import create_database, open_database, DatabaseOpenError

PASSWORD = "架空の検証用'password"

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / 'contacts.db'
    create_database(path, PASSWORD).close()
    return path


def test_create_reopen_schema(db_path):
    c = open_database(db_path, PASSWORD)
    try:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 1
        assert c.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert c.execute('PRAGMA cipher_integrity_check').fetchall() == []
        assert len(c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()) == 5
    finally:
        c.close()
    assert list(db_path.parent.iterdir()) == [db_path]


def test_existing_file_is_not_overwritten(db_path):
    before = db_path.read_bytes()
    with pytest.raises(FileExistsError):
        create_database(db_path, PASSWORD)
    assert db_path.read_bytes() == before


def test_wrong_password_leaves_file_unchanged(db_path):
    before = hashlib.sha256(db_path.read_bytes()).digest()
    with pytest.raises(DatabaseOpenError):
        open_database(db_path, 'wrong')
    assert hashlib.sha256(db_path.read_bytes()).digest() == before
    open_database(db_path, PASSWORD).close()


def test_missing_file_is_not_created(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        open_database(path, PASSWORD)
    assert not path.exists()


@pytest.mark.parametrize('password', ['', '   '])
def test_empty_password_does_not_create_file(tmp_path, password):
    path = tmp_path / 'empty.db'
    with pytest.raises(ValueError):
        create_database(path, password)
    assert not path.exists()


def test_plain_sqlite_cannot_read(db_path):
    c = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            c.execute('SELECT * FROM contacts').fetchall()
    finally:
        c.close()


def test_foreign_keys_and_multiline_notes(db_path):
    c = open_database(db_path, PASSWORD)
    try:
        with pytest.raises(cipher.IntegrityError):
            c.execute("INSERT INTO contact_phones(contact_id,kind,position,value) VALUES(999,'work_phone',1,'000')")
        c.rollback()
        note = '展示会\n架空のメモ'
        c.execute("INSERT INTO contacts(company_name,note,created_at,updated_at) VALUES(?,?,?,?)", ('架空会社',note,'2026-10-06T00:00:00Z','2026-10-06T00:00:00Z'))
        c.commit()
    finally:
        c.close()
    c = open_database(db_path, PASSWORD)
    try:
        assert c.execute('SELECT company_name,note FROM contacts').fetchone() == ('架空会社',note)
    finally:
        c.close()


def test_incomplete_source_reference_rejected(db_path):
    c = open_database(db_path, PASSWORD)
    try:
        c.execute("INSERT INTO import_batches(imported_at,source_filename,source_encoding,source_sha256,record_count,headers_json,original_csv) VALUES(?,?,?,?,?,?,?)", ('now','fictional.csv','cp932','fictional-hash',1,'[]',b'fictional'))
        with pytest.raises(cipher.IntegrityError):
            c.execute("INSERT INTO contacts(created_at,updated_at,import_batch_id,source_values_json) VALUES('now','now',1,'[]')")
        c.rollback()
    finally:
        c.close()
