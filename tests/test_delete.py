import csv
import pytest
from sqlcipher3 import dbapi2 as cipher
from contactdock.database import create_database,open_database
from contactdock.service import ContactInput,save_contact,delete_contact,ContactConflictError,ContactValidationError
from contactdock.repository import get_contact,list_contacts,search_contacts
from contactdock.outlook_csv import HEADERS,read_outlook_csv
from contactdock.importer import save_csv_preview,DuplicateImportError


@pytest.fixture
def database(tmp_path):
    c=create_database(tmp_path/'fictional.db','fictional-delete-password')
    try:yield c
    finally:c.close()


def test_delete_hides_contact_but_keeps_related_values(database,tmp_path):
    identifier=save_contact(database,ContactInput({'family_name':'架空','note':'検索語'},
        ({'kind':'work_phone','position':1,'value':'000'},),
        ({'position':1,'address':'fictional@example.invalid'},),({'kind':'work','city':'架空市'},)))
    d=get_contact(database,identifier)
    before={t:database.execute('SELECT * FROM '+t).fetchall() for t in
            ('contact_phones','contact_emails','contact_addresses')}
    delete_contact(database,identifier,d.updated_at)
    assert list_contacts(database)==[] and search_contacts(database,'検索語')==[]
    assert get_contact(database,identifier) is None
    row=database.execute('SELECT note,created_at,deleted_at,updated_at FROM contacts').fetchone()
    assert row[:2]==('検索語',d.created_at) and row[2] and row[2]==row[3]
    for table,rows in before.items():assert database.execute('SELECT * FROM '+table).fetchall()==rows
    c=open_database(tmp_path/'fictional.db','fictional-delete-password')
    try:assert list_contacts(c)==[] and c.execute('SELECT count(*) FROM contacts').fetchone()[0]==1
    finally:c.close()


def test_import_source_unchanged_and_reimport_still_refused(database,tmp_path):
    path=tmp_path/'fictional.csv'
    with path.open('w',encoding='cp932',newline='') as f:
        w=csv.writer(f);w.writerow(HEADERS);w.writerow(['架空' if h=='姓' else '' for h in HEADERS])
    p=read_outlook_csv(path);save_csv_preview(database,p)
    identifier=database.execute('SELECT id FROM contacts').fetchone()[0]
    d=get_contact(database,identifier)
    batch=database.execute('SELECT * FROM import_batches').fetchall()
    original=database.execute('SELECT import_batch_id,source_record_number,source_values_json FROM contacts').fetchone()
    delete_contact(database,identifier,d.updated_at)
    assert database.execute('SELECT * FROM import_batches').fetchall()==batch
    assert database.execute('SELECT import_batch_id,source_record_number,source_values_json FROM contacts').fetchone()==original
    with pytest.raises(DuplicateImportError):save_csv_preview(database,p)


def test_changed_since_confirmation_is_not_deleted(database):
    identifier=save_contact(database,ContactInput({'note':'元値'}));old=get_contact(database,identifier)
    save_contact(database,ContactInput({'note':'先行編集'}),identifier,old.updated_at)
    with pytest.raises(ContactConflictError):delete_contact(database,identifier,old.updated_at)
    assert get_contact(database,identifier).fields['note']=='先行編集'


@pytest.mark.parametrize('already_deleted',[False,True])
def test_missing_or_already_deleted_rejected(database,already_deleted):
    identifier=save_contact(database,ContactInput({'note':'架空'}));d=get_contact(database,identifier)
    if already_deleted:delete_contact(database,identifier,d.updated_at)
    else:identifier+=100
    with pytest.raises(ContactConflictError):delete_contact(database,identifier,d.updated_at)
    assert not database.in_transaction


def test_failure_rolls_back_deletion(database):
    identifier=save_contact(database,ContactInput({'note':'架空'}));d=get_contact(database,identifier)
    database.execute("""CREATE TEMP TRIGGER simulated_failure BEFORE UPDATE ON contacts
        BEGIN SELECT RAISE(ABORT,'simulated failure'); END""")
    with pytest.raises(cipher.IntegrityError):delete_contact(database,identifier,d.updated_at)
    assert get_contact(database,identifier)==d and not database.in_transaction


def test_callers_transaction_untouched(database):
    identifier=save_contact(database,ContactInput({'note':'架空'}));d=get_contact(database,identifier)
    database.execute("UPDATE contacts SET note='pending' WHERE id=?",(identifier,))
    with pytest.raises(ContactValidationError,match='トランザクション'):delete_contact(database,identifier,d.updated_at)
    assert database.in_transaction
    database.rollback()
    assert get_contact(database,identifier)==d
