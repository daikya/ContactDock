import csv
import hashlib
import os
import pytest
from contactdock.database import create_database
from contactdock.service import ContactInput,save_contact,delete_contact
from contactdock.repository import get_contact
from contactdock.outlook_csv import HEADERS,read_outlook_csv
from contactdock.importer import save_csv_preview
from contactdock.exporter import export_current_csv,export_original_csv,list_import_batches


@pytest.fixture
def database(tmp_path):
    c=create_database(tmp_path/'fictional.db','fictional-export-password')
    try:yield c
    finally:c.close()


def original(database,tmp_path):
    path=tmp_path/'fictional.csv'
    with path.open('w',encoding='cp932',newline='') as f:
        w=csv.writer(f);w.writerow(HEADERS);w.writerow(['架空' if h=='姓' else '元メモ\r\n原本' if h=='メモ' else '' for h in HEADERS])
    p=read_outlook_csv(path);result=save_csv_preview(database,p)
    identifier=database.execute('SELECT id FROM contacts').fetchone()[0]
    return result.batch_id,identifier,p


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def test_current_csv_preserves_full_values_and_extra_positions(database,tmp_path):
    note='  メモ,"引用"\r\n絵文字🙂  '
    identifier=save_contact(database,ContactInput({'company_name':'架空会社','note':note},
        ({'kind':'work_phone','position':3,'value':'000-0123'},),
        ({'position':4,'address':'four@example.invalid','display_name':'架空メール','source_type':'SMTP'},),
        ({'kind':'other','post_office_box':'架空私書箱'},)))
    path=tmp_path/'current.csv'
    assert export_current_csv(database,path)==1
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    row=read_csv(path)[0]
    assert row['連絡先ID']==str(identifier) and row['メモ']==note
    assert row['会社電話 3']=='000-0123' and row['電子メール 4 アドレス']=='four@example.invalid'
    assert row['電子メール 4 表示名']=='架空メール' and row['その他住所私書箱']=='架空私書箱'


def test_deleted_excluded_and_current_values_used(database,tmp_path):
    _,identifier,_=original(database,tmp_path)
    old=get_contact(database,identifier)
    save_contact(database,ContactInput({'family_name':'編集架空','note':'変更メモ'}),identifier,old.updated_at)
    another=save_contact(database,ContactInput({'note':'削除メモ'}))
    delete_contact(database,another,get_contact(database,another).updated_at)
    path=tmp_path/'current.csv';assert export_current_csv(database,path)==1
    row=read_csv(path)[0]
    assert row['姓']=='編集架空' and row['メモ']=='変更メモ'
    assert 'source_values_json' not in row


def test_original_byte_exact_after_edit_and_delete(database,tmp_path):
    batch,identifier,p=original(database,tmp_path)
    old=get_contact(database,identifier)
    save_contact(database,ContactInput({'note':'変更メモ'}),identifier,old.updated_at)
    delete_contact(database,identifier,get_contact(database,identifier).updated_at)
    path=tmp_path/'original-restored.csv';export_original_csv(database,batch,path)
    assert path.read_bytes()==p.original_csv
    assert hashlib.sha256(path.read_bytes()).hexdigest()==p.source_sha256
    assert list_import_batches(database)[0].record_count==1


def test_existing_output_not_overwritten_without_request(database,tmp_path):
    path=tmp_path/'output.csv';path.write_bytes(b'keep')
    with pytest.raises(FileExistsError):export_current_csv(database,path)
    assert path.read_bytes()==b'keep'
    export_current_csv(database,path,overwrite=True)
    assert read_csv(path)==[]


def test_database_file_is_protected(database,tmp_path):
    path=tmp_path/'fictional.db';before=path.read_bytes()
    with pytest.raises(ValueError,match='使用中のDB'):export_current_csv(database,path,overwrite=True)
    assert path.read_bytes()==before


def test_write_failure_preserves_existing_file_and_cleans_temp(database,tmp_path,monkeypatch):
    path=tmp_path/'output.csv';path.write_bytes(b'keep')
    def fail(*args):raise OSError('simulated failure')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):export_current_csv(database,path,overwrite=True)
    assert path.read_bytes()==b'keep' and list(tmp_path.glob('.contactdock-export-*'))==[]
    new=tmp_path/'new.csv'
    with pytest.raises(OSError):export_current_csv(database,new)
    assert not new.exists() and list(tmp_path.glob('.contactdock-export-*'))==[]


def test_missing_or_corrupt_original_does_not_overwrite(database,tmp_path):
    path=tmp_path/'output.csv';path.write_bytes(b'keep')
    with pytest.raises(ValueError,match='見つかりません'):export_original_csv(database,999,path,overwrite=True)
    batch,_,_=original(database,tmp_path)
    database.execute("UPDATE import_batches SET source_sha256='corrupt' WHERE id=?",(batch,));database.commit()
    with pytest.raises(ValueError,match='整合性'):export_original_csv(database,batch,path,overwrite=True)
    assert path.read_bytes()==b'keep'


def test_export_does_not_change_database(database,tmp_path):
    original(database,tmp_path)
    before=database.execute('SELECT * FROM contacts').fetchall()
    batches=database.execute('SELECT * FROM import_batches').fetchall()
    export_current_csv(database,tmp_path/'current.csv')
    assert database.execute('SELECT * FROM contacts').fetchall()==before
    assert database.execute('SELECT * FROM import_batches').fetchall()==batches
    assert not database.in_transaction


def test_pending_transaction_not_exported_or_committed(database,tmp_path):
    database.execute("INSERT INTO contacts(created_at,updated_at,note) VALUES('now','now','pending')")
    with pytest.raises(ValueError,match='トランザクション'):export_current_csv(database,tmp_path/'current.csv')
    assert database.in_transaction and not (tmp_path/'current.csv').exists()
    database.rollback()


def test_multiple_import_batch_listing(database,tmp_path):
    original(database,tmp_path)
    path=tmp_path/'second.csv'
    with path.open('w',encoding='cp932',newline='') as f:
        w=csv.writer(f);w.writerow(HEADERS);w.writerow(['別の架空' if h=='姓' else '' for h in HEADERS])
    save_csv_preview(database,read_outlook_csv(path))
    assert [b.filename for b in list_import_batches(database)]==['fictional.csv','second.csv']
