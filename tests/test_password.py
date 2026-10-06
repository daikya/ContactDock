import pytest
from contactdock import password
from contactdock.database import create_database,open_database,DatabaseOpenError
from contactdock.backup import backup_database
from contactdock.service import ContactInput,save_contact,delete_contact
from contactdock.repository import get_contact
from test_exporter import original

OLD='fictional-old-password'
NEW="架空の新しい'パスワード🙂"

@pytest.fixture
def database(tmp_path):
    c=create_database(tmp_path/'source.db',OLD)
    try:yield c
    finally:c.close()


def test_rekey_preserves_all_data_and_existing_backup(database,tmp_path):
    _,identifier,_=original(database,tmp_path)
    delete_contact(database,identifier,get_contact(database,identifier).updated_at)
    save_contact(database,ContactInput({'note':'架空\nメモ'},
        ({'kind':'mobile_phone','position':1,'value':'000'},),
        ({'position':1,'address':'fictional@example.invalid'},),
        ({'kind':'work','city':'架空市'},)))
    tables=('contacts','contact_phones','contact_emails','contact_addresses','import_batches')
    before={t:database.execute(f'SELECT * FROM {t} ORDER BY id').fetchall() for t in tables}
    backup_database(database,tmp_path/'old-backup.db',OLD)
    password.change_database_password(database,OLD,NEW)
    c=open_database(tmp_path/'source.db',NEW)
    try:
        for t in tables:assert c.execute(f'SELECT * FROM {t} ORDER BY id').fetchall()==before[t]
    finally:c.close()
    with pytest.raises(DatabaseOpenError):open_database(tmp_path/'source.db',OLD)
    c=open_database(tmp_path/'old-backup.db',OLD);c.close()
    with pytest.raises(DatabaseOpenError):open_database(tmp_path/'old-backup.db',NEW)
    save_contact(database,ContactInput({'note':'変更後も保存'}))
    backup_database(database,tmp_path/'new-backup.db',NEW)
    c=open_database(tmp_path/'new-backup.db',NEW);c.close()


def test_wrong_current_password_leaves_file_unchanged(database,tmp_path):
    path=tmp_path/'source.db';before=path.read_bytes()
    with pytest.raises(DatabaseOpenError):password.change_database_password(database,'wrong',NEW)
    assert path.read_bytes()==before
    c=open_database(path,OLD);c.close()


@pytest.mark.parametrize('new',['','  ',None,OLD,'nul\x00character'])
def test_invalid_new_password_leaves_file_unchanged(database,tmp_path,new):
    path=tmp_path/'source.db';before=path.read_bytes()
    with pytest.raises(ValueError):password.change_database_password(database,OLD,new)
    assert path.read_bytes()==before


def test_pending_transaction_not_committed(database):
    database.execute("INSERT INTO contacts(note,created_at,updated_at) VALUES('pending','x','x')")
    with pytest.raises(ValueError):password.change_database_password(database,OLD,NEW)
    assert database.in_transaction
    database.rollback()


def test_wal_rejected_before_change(database,tmp_path):
    database.execute('PRAGMA journal_mode=WAL')
    with pytest.raises(ValueError):password.change_database_password(database,OLD,NEW)
    c=open_database(tmp_path/'source.db',OLD);c.close()


def test_post_change_verification_failure_reports_uncertain_outcome(database,tmp_path,monkeypatch):
    real_open=password.open_database
    def fail_new(path,key):
        if key==NEW:raise OSError('fictional verification failure')
        return real_open(path,key)
    monkeypatch.setattr(password,'open_database',fail_new)
    with pytest.raises(password.PasswordChangeError):password.change_database_password(database,OLD,NEW)
    c=real_open(tmp_path/'source.db',NEW);c.close()
