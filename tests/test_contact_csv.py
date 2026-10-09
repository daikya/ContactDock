import csv
import pytest
from contactdock.database import create_database
from contactdock.service import ContactInput,save_contact
from contactdock.repository import get_contact,list_contacts
from contactdock.exporter import export_current_csv,export_original_csv
from contactdock.contact_csv import read_contact_csv,CsvValidationError
from contactdock.importer import save_csv_preview,DuplicateImportError
from test_exporter import original

@pytest.fixture
def database(tmp_path):
    c=create_database(tmp_path/'source.db','fictional-password')
    try:yield c
    finally:c.close()


def test_export_import_roundtrip_preserves_contact_values(database,tmp_path):
    identifier=save_contact(database,ContactInput({'family_name':'架空','note':'引用,"本文"\r\n絵文字🙂','birthday':'文字列のまま'},
        ({'kind':'work_phone','position':3,'value':'000-03'},{'kind':'custom','position':2,'value':'000-02'}),
        ({'position':4,'address':'fictional@example.invalid','display_name':'架空','source_type':'SMTP'},),
        ({'kind':'other','city':'架空市','post_office_box':'架空私書箱'},)))
    path=tmp_path/'current.csv';export_current_csv(database,path)
    preview=read_contact_csv(path);assert preview.source_encoding=='utf-8-sig'
    destination=create_database(tmp_path/'target.db','fictional-password')
    try:
        result=save_csv_preview(destination,preview)
        before=get_contact(database,identifier);after=get_contact(destination,list_contacts(destination)[0].id)
        assert before.fields==after.fields and before.phones==after.phones and before.emails==after.emails and before.addresses==after.addresses
        restored=tmp_path/'restored.csv';export_original_csv(destination,result.batch_id,restored)
        assert restored.read_bytes()==path.read_bytes()
        with pytest.raises(DuplicateImportError):save_csv_preview(destination,preview)
    finally:destination.close()


def test_import_into_source_adds_instead_of_updating(database,tmp_path):
    identifier=save_contact(database,ContactInput({'note':'架空メモ'}))
    before=get_contact(database,identifier)
    path=tmp_path/'current.csv';export_current_csv(database,path)
    save_csv_preview(database,read_contact_csv(path))
    assert len(list_contacts(database))==2 and get_contact(database,identifier)==before


def test_outlook_format_still_supported(database,tmp_path):
    _,_,preview=original(database,tmp_path)
    assert read_contact_csv(tmp_path/'fictional.csv')==preview


@pytest.mark.parametrize('bad',['duplicate','missing','width','unknown'])
def test_malformed_contactdock_csv_rejected(database,tmp_path,bad):
    save_contact(database,ContactInput({'note':'架空メモ'}));path=tmp_path/'current.csv';export_current_csv(database,path)
    with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
    if bad=='duplicate':rows[0][1]=rows[0][0]
    elif bad=='missing':rows[0][1]='不足項目'
    elif bad=='width':rows[1].pop()
    else:
        rows[0].append('未対応項目');rows[1].append('架空')
    with path.open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerows(rows)
    with pytest.raises(CsvValidationError):read_contact_csv(path)


def test_empty_current_fields_from_migration_can_be_reimported(database,tmp_path):
    database.execute("INSERT INTO contacts(created_at,updated_at) VALUES('fictional','fictional')")
    database.commit()
    path=tmp_path/'empty-values.csv';export_current_csv(database,path)
    preview=read_contact_csv(path)
    assert len(preview.contacts)==1 and not any(preview.contacts[0].fields.values())
    save_csv_preview(database,preview)
    assert len(list_contacts(database))==2
