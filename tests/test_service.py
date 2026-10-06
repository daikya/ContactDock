import csv
from dataclasses import replace
import pytest
from sqlcipher3 import dbapi2 as cipher
from contactdock.database import create_database, open_database
from contactdock.outlook_csv import HEADERS,read_outlook_csv
from contactdock.importer import save_csv_preview
from contactdock.repository import get_contact,search_contacts
from contactdock.service import ContactInput,save_contact,ContactValidationError,ContactConflictError


@pytest.fixture
def database(tmp_path):
    c=create_database(tmp_path/'fictional.db','fictional-edit-password')
    try:yield c
    finally:c.close()


def draft_from_detail(d):
    return ContactInput(d.fields,d.phones,d.emails,d.addresses)


def test_create_company_only_reopen(database,tmp_path):
    identifier=save_contact(database,ContactInput({'company_name':'架空会社'}))
    c=open_database(tmp_path/'fictional.db','fictional-edit-password')
    try:
        d=get_contact(c,identifier)
        assert d.fields['company_name']=='架空会社' and d.display_name==''
        assert d.source is None and d.created_at==d.updated_at
    finally:c.close()


@pytest.mark.parametrize('fields',[{}, {'family_name':' \t','note':'\n'}])
def test_empty_rejected_without_save(database,fields):
    with pytest.raises(ContactValidationError,match='少なくとも'):save_contact(database,ContactInput(fields))
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==0
    assert not database.in_transaction


def test_multiple_related_values_and_note_preserved(database):
    draft=ContactInput({'note':'  展示会\r\n検索メモ  '},
        ({'kind':'work_phone','position':2,'value':'000-0123'},),
        ({'position':3,'address':'fictional@example.invalid','display_name':'架空','source_type':'SMTP'},),
        ({'kind':'other','post_office_box':'架空私書箱'},))
    identifier=save_contact(database,draft);d=get_contact(database,identifier)
    assert d.fields['note']==draft.fields['note'] and d.phones[0]['position']==2
    assert d.emails[0]['position']==3 and d.addresses[0]['post_office_box']=='架空私書箱'
    assert search_contacts(database,'検索メモ')[0].id==identifier


def test_edit_preserves_import_source_and_created_at(database,tmp_path):
    path=tmp_path/'fictional.csv'
    original={'姓':'架空','メモ':'元メモ\r\n原本','優先度':'低'}
    with path.open('w',encoding='cp932',newline='') as f:
        w=csv.writer(f);w.writerow(HEADERS);w.writerow([original.get(h,'') for h in HEADERS])
    p=read_outlook_csv(path);save_csv_preview(database,p)
    identifier=database.execute('SELECT id FROM contacts').fetchone()[0]
    old=get_contact(database,identifier)
    fields=dict(old.fields,note='変更したメモ')
    save_contact(database,ContactInput(fields),identifier,old.updated_at)
    new=get_contact(database,identifier)
    assert new.source==old.source and new.created_at==old.created_at
    assert new.updated_at!=old.updated_at and new.fields['note']=='変更したメモ'
    assert database.execute('SELECT original_csv FROM import_batches').fetchone()[0]==p.original_csv


def test_edit_replaces_related_values(database):
    identifier=save_contact(database,ContactInput({'family_name':'架空'},
        ({'kind':'work_phone','position':1,'value':'old'},),
        ({'position':1,'address':'old@example.invalid'},),({'kind':'work','city':'旧住所'},)))
    old=get_contact(database,identifier)
    save_contact(database,ContactInput(dict(old.fields),
        ({'kind':'mobile_phone','position':1,'value':'000-new'},)),identifier,old.updated_at)
    new=get_contact(database,identifier)
    assert len(new.phones)==1 and new.phones[0]['kind']=='mobile_phone'
    assert new.emails==() and new.addresses==()


@pytest.mark.parametrize('draft',[
    ContactInput({'family_name':'架空'},({'kind':'work_phone','position':0,'value':'000'},)),
    ContactInput({'family_name':'架空'},({'kind':'work_phone','position':1,'value':'000'},{'kind':'work_phone','position':1,'value':'001'})),
    ContactInput({'family_name':'架空'},emails=({'position':1,'address':'one'},{'position':1,'address':'two'})),
    ContactInput({'family_name':'架空'},addresses=({'kind':'work','city':'一'},{'kind':'work','city':'二'})),
])
def test_invalid_related_rows_do_not_save(database,draft):
    with pytest.raises(ContactValidationError):save_contact(database,draft)
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==0


def test_failure_restores_contact_and_deleted_children(database):
    identifier=save_contact(database,ContactInput({'note':'元メモ'},({'kind':'work_phone','position':1,'value':'old'},)))
    old=get_contact(database,identifier)
    database.execute("""CREATE TEMP TRIGGER simulated_failure BEFORE INSERT ON contact_phones
        BEGIN SELECT RAISE(ABORT,'simulated failure'); END""")
    with pytest.raises(cipher.IntegrityError):
        save_contact(database,ContactInput({'note':'変更メモ'},({'kind':'work_phone','position':1,'value':'new'},)),identifier,old.updated_at)
    assert get_contact(database,identifier)==old
    assert not database.in_transaction


def test_stale_edit_and_deleted_contact_rejected(database):
    identifier=save_contact(database,ContactInput({'note':'元メモ'}));old=get_contact(database,identifier)
    save_contact(database,ContactInput({'note':'先行編集'}),identifier,old.updated_at)
    with pytest.raises(ContactConflictError):save_contact(database,ContactInput({'note':'後続編集'}),identifier,old.updated_at)
    assert get_contact(database,identifier).fields['note']=='先行編集'
    new=get_contact(database,identifier)
    database.execute("UPDATE contacts SET deleted_at='deleted' WHERE id=?",(identifier,));database.commit()
    with pytest.raises(ContactConflictError):save_contact(database,draft_from_detail(new),identifier,new.updated_at)


def test_callers_transaction_not_committed_or_rolled_back(database):
    database.execute("INSERT INTO contacts(created_at,updated_at,note) VALUES('now','now','pending')")
    with pytest.raises(ContactValidationError,match='トランザクション'):save_contact(database,ContactInput({'note':'new'}))
    assert database.in_transaction
    database.rollback()
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==0


def test_related_only_and_blank_rows(database):
    identifier=save_contact(database,ContactInput({},phones=({'kind':'','position':0,'value':''},),
        emails=({'position':2,'display_name':'架空表示名'},),addresses=({'kind':'home','postal_code':'001-0000'},)))
    d=get_contact(database,identifier)
    assert d.phones==() and d.emails[0]['address']=='' and d.addresses[0]['postal_code']=='001-0000'
