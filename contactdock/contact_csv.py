"""Read ContactDock exports or the existing Outlook migration format."""
import csv
import hashlib
import io
from pathlib import Path
import re

from contactdock.outlook_csv import (FIELDS,PHONES,CsvPreview,ParsedContact,
                                     ImportWarning,CsvValidationError,read_outlook_csv)
from contactdock.service import ContactInput,ContactValidationError,validate_contact,ADDRESS_FIELDS

ADMIN=('連絡先ID','登録日時（UTC）','更新日時（UTC）')
ADDRESS_COLUMNS={kind:dict(zip(ADDRESS_FIELDS,(f'国 ({label})/地域',f'郵便番号 ({label})',
    f'都道府県 ({label})',f'市町村 ({label})',f'番地 ({label})',f'{label}住所私書箱')))
    for kind,label in (('work','会社'),('home','自宅'),('other','その他'))}


def _phone_column(column):
    if column in PHONES:return PHONES[column]
    labels={name:kind for name,(kind,pos) in PHONES.items() if pos==1}
    for label,kind in labels.items():
        match=re.fullmatch(re.escape(label)+r' ([1-9][0-9]*)',column)
        if match:return kind,int(match[1])
    match=re.fullmatch(r'電話（(.+)） ([1-9][0-9]*)',column)
    if match:return match[1],int(match[2])
    return None


def _email_column(column):
    first={'電子メール アドレス':'address','電子メール表示名':'display_name','電子メールの種類':'source_type'}
    if column in first:return 1,first[column]
    match=re.fullmatch(r'電子メール ([1-9][0-9]*) (アドレス|表示名|の種類)',column)
    if match:return int(match[1]),{'アドレス':'address','表示名':'display_name','の種類':'source_type'}[match[2]]
    return None


def read_contact_csv(path):
    path=Path(path);raw=path.read_bytes()
    # ContactDock exports have an explicit UTF-8 BOM; Outlook stays CP932.
    if not raw.startswith(b'\xef\xbb\xbf'):return read_outlook_csv(path)
    try:text=raw.decode('utf-8-sig',errors='strict')
    except UnicodeDecodeError:raise CsvValidationError('UTF-8として読み取れません。') from None
    reader=csv.reader(io.StringIO(text,newline=''),strict=True)
    try:
        headers=next(reader,None)
        if not headers:raise CsvValidationError('CSVが空です。')
        if len(set(headers))!=len(headers):raise CsvValidationError('ヘッダー名が重複しています。')
        required=set(FIELDS)|{'誕生日'}|set(ADMIN)|{c for cols in ADDRESS_COLUMNS.values() for c in cols.values()}
        if not required<=set(headers):raise CsvValidationError('ContactDock CSVの必要な項目が不足しています。')
        phones={};emails={}
        for column in headers:
            if column in required:continue
            phone=_phone_column(column);email=_email_column(column)
            if phone:
                if phone in phones.values():raise CsvValidationError('電話の種類と順序が重複しています。')
                phones[column]=phone
            elif email:
                if email in emails.values():raise CsvValidationError('メールの順序と項目が重複しています。')
                emails[column]=email
            else:raise CsvValidationError('ContactDock CSVに未対応の項目があります。')
        if any(pos>2**63-1 for _,pos in phones.values()) or any(pos>2**63-1 for pos,_ in emails.values()):
            raise CsvValidationError('電話またはメールの順序が範囲外です。')
        contacts=[]
        for number,values in enumerate(reader,1):
            if len(values)!=len(headers):raise CsvValidationError(f'データレコード{number}の列数が一致しません。')
            row=dict(zip(headers,values))
            fields={target:row[source] for source,target in FIELDS.items()};fields['birthday']=row['誕生日']
            phone_values=tuple(dict(kind=kind,position=pos,value=row[col]) for col,(kind,pos) in phones.items())
            email_values={}
            for col,(pos,key) in emails.items():email_values.setdefault(pos,{'position':pos})[key]=row[col]
            addresses=tuple(dict(kind=kind,**{key:row[col] for key,col in cols.items()}) for kind,cols in ADDRESS_COLUMNS.items())
            # Migration can retain contacts whose only values are source-only.
            # Their flat export legitimately has no current editable values.
            empty=not any(value.strip() for col,value in row.items() if col not in ADMIN)
            original_note=fields['note']
            if empty:fields['note']='temporary validation placeholder'
            try:
                fields,p,e,a=validate_contact(ContactInput(fields,phone_values,tuple(email_values.values()),addresses))
                if empty:fields['note']=original_note
            except ContactValidationError:raise CsvValidationError(f'データレコード{number}の連絡先内容を確認してください。') from None
            contacts.append(ParsedContact(number,tuple(values),fields,tuple(p),tuple(e),tuple(a)))
    except csv.Error:raise CsvValidationError('CSVの引用符・レコード構造が不正です。') from None
    if not contacts:raise CsvValidationError('連絡先のデータレコードがありません。')
    warnings=tuple(ImportWarning(None,col,'source_metadata_only') for col in ADMIN)
    return CsvPreview(path.name,'utf-8-sig',hashlib.sha256(raw).hexdigest(),tuple(headers),raw,tuple(contacts),warnings)
