import sqlite3
import pytest
from contactdock import backup
from contactdock.database import create_database, open_database, DatabaseOpenError
from contactdock.service import ContactInput, save_contact, delete_contact
from contactdock.repository import get_contact
from test_exporter import original

PASSWORD='fictional-backup-password'

@pytest.fixture
def database(tmp_path):
    c=create_database(tmp_path/'source.db',PASSWORD)
    try:yield c
    finally:c.close()


def test_complete_encrypted_snapshot(database,tmp_path):
    batch,identifier,preview=original(database,tmp_path)
    delete_contact(database,identifier,get_contact(database,identifier).updated_at)
    save_contact(database,ContactInput({'note':'日本語\n架空メモ'},
        ({'kind':'mobile_phone','position':1,'value':'000'},),
        ({'position':1,'address':'fictional@example.invalid'},),
        ({'kind':'home','city':'架空市'},)))
    path=tmp_path/'backup.db'
    backup.backup_database(database,path,PASSWORD)
    c=open_database(path,PASSWORD)
    try:
        for table in ('contacts','contact_phones','contact_emails','contact_addresses','import_batches'):
            assert c.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()==database.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
        assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
    finally:c.close()
    with pytest.raises(DatabaseOpenError):open_database(path,'wrong-password')
    with sqlite3.connect(path) as plain:
        with pytest.raises(sqlite3.DatabaseError):plain.execute('SELECT * FROM contacts').fetchall()
    save_contact(database,ContactInput({'note':'バックアップ後'}))
    assert not list(tmp_path.glob('.contactdock-backup-*'))


def test_committed_wal_is_included(database,tmp_path):
    database.execute('PRAGMA journal_mode=WAL')
    save_contact(database,ContactInput({'note':'WAL内の架空データ'}))
    path=tmp_path/'wal-backup.db';backup.backup_database(database,path,PASSWORD)
    c=open_database(path,PASSWORD)
    try:assert c.execute('SELECT note FROM contacts').fetchone()[0]=='WAL内の架空データ'
    finally:c.close()


@pytest.mark.parametrize('suffix',['','-wal','-shm','-journal'])
def test_source_files_protected(database,tmp_path,suffix):
    with pytest.raises(ValueError):backup.backup_database(database,tmp_path/('source.db'+suffix),PASSWORD,overwrite=True)


def test_wrong_password_preserves_existing_output(database,tmp_path):
    path=tmp_path/'existing.db';path.write_bytes(b'keep')
    with pytest.raises(DatabaseOpenError):backup.backup_database(database,path,'wrong',overwrite=True)
    assert path.read_bytes()==b'keep'


def test_existing_output_requires_explicit_overwrite(database,tmp_path):
    path=tmp_path/'existing.db';path.write_bytes(b'keep')
    with pytest.raises(FileExistsError):backup.backup_database(database,path,PASSWORD)
    assert path.read_bytes()==b'keep'
    backup.backup_database(database,path,PASSWORD,overwrite=True)
    c=open_database(path,PASSWORD);c.close()


@pytest.mark.parametrize('existing',[False,True])
def test_publish_failure_cleanup(database,tmp_path,monkeypatch,existing):
    path=tmp_path/'backup.db'
    if existing:path.write_bytes(b'keep')
    def fail(*args):raise OSError('fictional publish failure')
    monkeypatch.setattr(backup.os,'replace',fail)
    with pytest.raises(OSError):backup.backup_database(database,path,PASSWORD,overwrite=existing)
    if existing:assert path.read_bytes()==b'keep'
    else:assert not path.exists()
    assert not list(tmp_path.glob('.contactdock-backup-*'))


def test_pending_transaction_not_committed(database,tmp_path):
    database.execute("INSERT INTO contacts(note,created_at,updated_at) VALUES('pending','x','x')")
    with pytest.raises(ValueError):backup.backup_database(database,tmp_path/'backup.db',PASSWORD)
    assert database.in_transaction
    database.rollback()


def test_backup_sync_uses_writable_descriptor(database,tmp_path,monkeypatch):
    real_sync=backup.os.fsync
    synced=[]
    def require_writable(descriptor):
        # A zero-byte write checks write access without changing DB contents.
        backup.os.write(descriptor,b'')
        synced.append(descriptor)
        real_sync(descriptor)
    monkeypatch.setattr(backup.os,'fsync',require_writable)
    backup.backup_database(database,tmp_path/'backup.db',PASSWORD)
    assert len(synced)==1
