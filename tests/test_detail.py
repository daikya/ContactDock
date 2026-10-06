import csv
import json
import pytest
from contactdock.database import create_database
from contactdock.outlook_csv import HEADERS, read_outlook_csv
from contactdock.importer import save_csv_preview
from contactdock.repository import get_contact


@pytest.fixture
def database(tmp_path):
    c = create_database(tmp_path/'fictional.db','fictional-detail-password')
    try:yield c
    finally:c.close()


def import_one(c,tmp_path,record):
    path=tmp_path/'fictional.csv'
    with path.open('w',encoding='cp932',newline='') as f:
        w=csv.writer(f);w.writerow(HEADERS);w.writerow([record.get(h,'') for h in HEADERS])
    p=read_outlook_csv(path);save_csv_preview(c,p)
    return c.execute('SELECT id FROM contacts').fetchone()[0],p


def test_full_detail_and_source(database,tmp_path):
    record={'姓':'架空','名':'太郎','会社名':'架空会社','メモ':'展示会\r\n検索用',
            'Web ページ':'https://example.invalid','誕生日':'2000/2/29',
            '会社電話':'000-1111','会社電話 2':'000-2222','携帯電話':'000-3333',
            '電子メール 3 アドレス':'three@example.invalid','電子メール 3 表示名':'架空メール',
            '電子メール 3 の種類':'SMTP','郵便番号 (会社)':'001-0000','番地 (自宅)':'架空住所',
            'その他住所私書箱':'架空私書箱','優先度':'低'}
    identifier,p=import_one(database,tmp_path,record)
    d=get_contact(database,identifier)
    assert d.id==identifier and d.display_name=='架空 太郎'
    assert d.fields['note']==record['メモ'] and d.fields['birthday']=='2000-02-29'
    assert d.fields['web_page']==record['Web ページ']
    work=[p for p in d.phones if p['kind']=='work_phone']
    assert [(p['position'],p['value']) for p in work]==[(1,'000-1111'),(2,'000-2222')]
    assert d.emails==({'position':3,'address':'three@example.invalid','display_name':'架空メール','source_type':'SMTP'},)
    assert [a['kind'] for a in d.addresses]==['work','home','other']
    assert d.source.filename=='fictional.csv' and d.source.record_number==1
    assert d.source.encoding=='cp932' and d.source.sha256==p.source_sha256
    assert d.source.fields==tuple(zip(p.headers,p.contacts[0].raw_values))
    assert dict(d.source.fields)['誕生日']=='2000/2/29'
    assert dict(d.source.fields)['優先度']=='低'
    assert not database.in_transaction


def test_new_contact_has_no_source_and_empty_children(database):
    identifier=database.execute("INSERT INTO contacts(company_name,created_at,updated_at) VALUES('架空会社','now','now')").lastrowid
    database.commit()
    d=get_contact(database,identifier)
    assert d.source is None
    assert d.phones==d.emails==d.addresses==()
    assert d.display_name=='' and d.fields['company_name']=='架空会社'


def test_missing_and_deleted_are_not_returned(database,tmp_path):
    identifier,_=import_one(database,tmp_path,{'姓':'架空'})
    assert get_contact(database,identifier+100) is None
    database.execute("UPDATE contacts SET deleted_at='deleted' WHERE id=?",(identifier,));database.commit()
    assert get_contact(database,identifier) is None
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==1


def test_source_does_not_change_after_edit(database,tmp_path):
    identifier,_=import_one(database,tmp_path,{'姓':'架空','メモ':'元メモ'})
    database.execute("UPDATE contacts SET note='編集後メモ' WHERE id=?",(identifier,));database.commit()
    d=get_contact(database,identifier)
    assert d.fields['note']=='編集後メモ'
    assert dict(d.source.fields)['メモ']=='元メモ'


def test_existing_transaction_is_preserved(database):
    identifier=database.execute("INSERT INTO contacts(note,created_at,updated_at) VALUES('pending','now','now')").lastrowid
    assert get_contact(database,identifier).fields['note']=='pending'
    assert database.in_transaction
    database.rollback()
    assert get_contact(database,identifier) is None


def test_corrupt_source_error_preserves_callers_transaction(database,tmp_path):
    identifier,_=import_one(database,tmp_path,{'姓':'架空'})
    database.execute('UPDATE contacts SET source_values_json=? WHERE id=?',(json.dumps(['wrong-width']),identifier))
    with pytest.raises(ValueError,match='件数'):get_contact(database,identifier)
    assert database.in_transaction
    database.rollback()
    assert get_contact(database,identifier).source is not None


def test_invalid_id(database):
    with pytest.raises(TypeError):get_contact(database,'1')
    with pytest.raises(TypeError):get_contact(database,True)


def test_related_data_belongs_only_to_selected_contact(database):
    a=database.execute("INSERT INTO contacts(created_at,updated_at) VALUES('now','now')").lastrowid
    b=database.execute("INSERT INTO contacts(created_at,updated_at) VALUES('now','now')").lastrowid
    database.execute("INSERT INTO contact_phones(contact_id,kind,position,value) VALUES(?,'work_phone',1,'000-1111')",(b,))
    database.commit()
    assert get_contact(database,a).phones==()
    assert get_contact(database,b).phones[0]['value']=='000-1111'
