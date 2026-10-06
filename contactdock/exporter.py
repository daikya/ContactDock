"""Current-contact CSV export and exact original-CSV restoration."""
import csv
import hashlib
import io
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from contactdock.outlook_csv import FIELDS, PHONES
from contactdock.service import ADDRESS_FIELDS


@dataclass(frozen=True)
class ImportBatchSummary:
    id: int
    filename: str
    imported_at: str
    record_count: int
    encoding: str


def list_import_batches(connection):
    return [ImportBatchSummary(*row) for row in connection.execute('''
        SELECT id,source_filename,imported_at,record_count,source_encoding
        FROM import_batches ORDER BY id''').fetchall()]


def _protect_database(connection, path):
    target=Path(path).resolve()
    for _,_,filename in connection.execute('PRAGMA database_list').fetchall():
        if not filename:continue
        database=Path(filename).resolve()
        protected=[database]+[Path(str(database)+suffix) for suffix in ('-journal','-wal','-shm')]
        for item in protected:
            if target==item or (target.exists() and item.exists() and os.path.samefile(target,item)):
                raise ValueError('使用中のDBや補助ファイルへ出力できません。')


def _write_file(connection,path,data,overwrite):
    _protect_database(connection,path)
    path=Path(path)
    reserved=False;temporary=None
    try:
        if not overwrite:
            with path.open('xb'):pass
            reserved=True
        descriptor,name=tempfile.mkstemp(prefix='.contactdock-export-',suffix='.tmp',dir=path.parent)
        temporary=Path(name)
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
        temporary=None;reserved=False
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
        if reserved:path.unlink(missing_ok=True)


def _rows(connection,sql):
    cursor=connection.execute(sql)
    names=[column[0] for column in cursor.description]
    return [dict(zip(names,row)) for row in cursor.fetchall()]


def _current_csv(connection):
    if connection.in_transaction:
        raise ValueError('既存のトランザクションを終了してから出力してください。')
    savepoint='contactdock_export_'+uuid.uuid4().hex
    connection.execute(f'SAVEPOINT {savepoint}')
    try:
        contacts=_rows(connection,'SELECT id,'+','.join(tuple(FIELDS.values())+('birthday','created_at','updated_at'))+
            ' FROM contacts WHERE deleted_at IS NULL ORDER BY id')
        phones=_rows(connection,'''SELECT p.contact_id,p.kind,p.position,p.value FROM contact_phones p
            JOIN contacts c ON c.id=p.contact_id WHERE c.deleted_at IS NULL''')
        emails=_rows(connection,'''SELECT e.contact_id,e.position,e.address,e.display_name,e.source_type
            FROM contact_emails e JOIN contacts c ON c.id=e.contact_id WHERE c.deleted_at IS NULL''')
        addresses=_rows(connection,'''SELECT a.* FROM contact_addresses a
            JOIN contacts c ON c.id=a.contact_id WHERE c.deleted_at IS NULL''')
        connection.execute(f'RELEASE SAVEPOINT {savepoint}')
    except BaseException:
        connection.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
        connection.execute(f'RELEASE SAVEPOINT {savepoint}')
        raise
    # Human-readable flat columns; add extra numbered columns without truncation.
    phone_names={pair:name for name,pair in PHONES.items()}
    labels={kind:name for name,(kind,pos) in PHONES.items() if pos==1}
    kind_order={kind:index for index,kind in enumerate(labels)}
    phone_keys=sorted({(p['kind'],p['position']) for p in phones},
        key=lambda key:(kind_order.get(key[0],len(kind_order)),key[0],key[1]))
    phone_columns={key:phone_names.get(key,labels.get(key[0],f'電話（{key[0]}）')+f' {key[1]}') for key in phone_keys}
    email_positions=sorted({e['position'] for e in emails})
    email_columns={pos:('電子メール アドレス','電子メール表示名','電子メールの種類') if pos==1 else
        (f'電子メール {pos} アドレス',f'電子メール {pos} 表示名',f'電子メール {pos} の種類') for pos in email_positions}
    address_columns={}
    for kind,label in (('work','会社'),('home','自宅'),('other','その他')):
        address_columns[kind]=dict(zip(ADDRESS_FIELDS,(f'国 ({label})/地域',f'郵便番号 ({label})',
            f'都道府県 ({label})',f'市町村 ({label})',f'番地 ({label})',f'{label}住所私書箱')))
    headers=['連絡先ID']+list(FIELDS)+['誕生日','登録日時（UTC）','更新日時（UTC）']
    headers+=list(phone_columns.values())
    for columns in email_columns.values():headers+=list(columns)
    for columns in address_columns.values():headers+=list(columns.values())
    if len(headers)!=len(set(headers)):
        raise ValueError('CSV列名が重複するため出力できません。')
    rows={c['id']:dict({'連絡先ID':str(c['id'])},**{source:c[target] for source,target in FIELDS.items()},
        誕生日=c['birthday'],**{'登録日時（UTC）':c['created_at'],'更新日時（UTC）':c['updated_at']}) for c in contacts}
    for p in phones:rows[p['contact_id']][phone_columns[(p['kind'],p['position'])]]=p['value']
    for e in emails:
        for column,key in zip(email_columns[e['position']],('address','display_name','source_type')):
            rows[e['contact_id']][column]=e[key]
    for a in addresses:
        for key,column in address_columns[a['kind']].items():rows[a['contact_id']][column]=a[key]
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=headers,lineterminator='\r\n')
    writer.writeheader();writer.writerows(rows.values())
    return stream.getvalue().encode('utf-8-sig'),len(contacts)


def export_current_csv(connection,path,overwrite=False):
    """Export all active contacts in ContactDock CSV (UTF-8 BOM); return count.

    Not the legacy 95-column CP932 import format. Source-only fields are not
    mixed into current contact values; originals are exported separately.
    """
    _protect_database(connection,path)
    data,count=_current_csv(connection)
    _write_file(connection,path,data,overwrite)
    return count


def export_original_csv(connection,batch_id,path,overwrite=False):
    """Write exact original bytes, including contacts deleted after import."""
    if connection.in_transaction:
        raise ValueError('既存のトランザクションを終了してから出力してください。')
    if isinstance(batch_id,bool) or not isinstance(batch_id,int):
        raise ValueError('取込単位IDは整数で指定してください。')
    row=connection.execute('SELECT original_csv,source_sha256 FROM import_batches WHERE id=?',(batch_id,)).fetchone()
    if row is None:raise ValueError('移行元のCSVが見つかりません。')
    data=bytes(row[0])
    if hashlib.sha256(data).hexdigest()!=row[1]:
        raise ValueError('保存されているCSV原本の整合性を確認できません。')
    _write_file(connection,path,data,overwrite)
