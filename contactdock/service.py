"""Atomic contact creation/editing, independently of Tkinter."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

FIELDS = ('family_name','given_name','family_name_kana','given_name_kana','company_name',
          'company_name_kana','department','job_title','note','web_page','birthday')
ADDRESS_FIELDS = ('country_region','postal_code','prefecture','city','street','post_office_box')


class ContactValidationError(ValueError):
    pass


class ContactConflictError(ValueError):
    """The edited contact changed, was deleted, or no longer exists."""


@dataclass(frozen=True)
class ContactInput:
    fields: dict[str, str] = field(default_factory=dict)
    phones: tuple[dict, ...] = ()
    emails: tuple[dict, ...] = ()
    addresses: tuple[dict, ...] = ()


def _strings(record, keys):
    values = {key: record.get(key, '') for key in keys}
    if not all(isinstance(value, str) for value in values.values()):
        raise ContactValidationError('入力値は文字列で指定してください。')
    return values


def _position(record):
    value = record.get('position')
    if isinstance(value,bool) or not isinstance(value,int) or value < 1:
        raise ContactValidationError('電話・メールの順序は1以上の整数で指定してください。')
    return value


def validate_contact(draft):
    if set(draft.fields) - set(FIELDS):
        raise ContactValidationError('未対応の連絡先項目があります。')
    fields = _strings(draft.fields,FIELDS)
    phones=[];emails=[];addresses=[]
    phone_keys=set();email_keys=set();address_keys=set()
    for original in draft.phones:
        phone=_strings(original,('kind','value'))
        if not phone['value'].strip():continue
        position=_position(original)
        if not phone['kind'].strip():raise ContactValidationError('電話の種類を指定してください。')
        key=(phone['kind'],position)
        if key in phone_keys:raise ContactValidationError('同じ種類・順序の電話が重複しています。')
        phone_keys.add(key);phones.append(dict(phone,position=position))
    for original in draft.emails:
        email=_strings(original,('address','display_name','source_type'))
        if not any(v.strip() for v in email.values()):continue
        position=_position(original)
        if position in email_keys:raise ContactValidationError('メールの順序が重複しています。')
        email_keys.add(position);emails.append(dict(email,position=position))
    for original in draft.addresses:
        address=_strings(original,('kind',)+ADDRESS_FIELDS)
        if not any(address[k].strip() for k in ADDRESS_FIELDS):continue
        if address['kind'] not in ('work','home','other'):raise ContactValidationError('住所の区分が不正です。')
        if address['kind'] in address_keys:raise ContactValidationError('同じ区分の住所が重複しています。')
        address_keys.add(address['kind']);addresses.append(address)
    if not any(v.strip() for v in fields.values()) and not (phones or emails or addresses):
        raise ContactValidationError('少なくとも一つの項目を入力してください。')
    return fields,phones,emails,addresses


def save_contact(connection, draft, contact_id=None, expected_updated_at=None):
    """Create/update one contact and all related values; preserve import source.

    Update requires the timestamp read when opening the editor, to prevent
    silent overwrites of another edit. Caller must finish any outer transaction.
    """
    if connection.in_transaction:
        raise ContactValidationError('既存のトランザクションを終了してから保存してください。')
    if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise ContactValidationError('外部キー検証を有効にしてください。')
    if contact_id is not None:
        if isinstance(contact_id,bool) or not isinstance(contact_id,int):
            raise ContactValidationError('連絡先IDは整数で指定してください。')
        if not isinstance(expected_updated_at,str) or not expected_updated_at:
            raise ContactValidationError('編集開始時の更新日時が必要です。')
    fields,phones,emails,addresses=validate_contact(draft)
    connection.execute('BEGIN IMMEDIATE')
    try:
        timestamp=datetime.now(timezone.utc).isoformat(timespec='microseconds')
        if contact_id is None:
            names=FIELDS+('created_at','updated_at')
            cursor=connection.execute('INSERT INTO contacts('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',
                                      tuple(fields[k] for k in FIELDS)+(timestamp,timestamp))
            contact_id=cursor.lastrowid
        else:
            cursor=connection.execute('UPDATE contacts SET '+','.join(k+'=?' for k in FIELDS)+
                ',updated_at=? WHERE id=? AND deleted_at IS NULL AND updated_at=?',
                tuple(fields[k] for k in FIELDS)+(timestamp,contact_id,expected_updated_at))
            if cursor.rowcount != 1:
                raise ContactConflictError('連絡先が更新・削除されています。一覧から開き直してください。')
            for table in ('contact_phones','contact_emails','contact_addresses'):
                connection.execute(f'DELETE FROM {table} WHERE contact_id=?',(contact_id,))
        for phone in phones:
            connection.execute('INSERT INTO contact_phones(contact_id,kind,position,value) VALUES(?,?,?,?)',
                (contact_id,phone['kind'],phone['position'],phone['value']))
        for email in emails:
            connection.execute('INSERT INTO contact_emails(contact_id,position,address,display_name,source_type) VALUES(?,?,?,?,?)',
                (contact_id,email['position'],email['address'],email['display_name'],email['source_type']))
        for address in addresses:
            connection.execute('INSERT INTO contact_addresses(contact_id,kind,'+','.join(ADDRESS_FIELDS)+') VALUES(?,?,?,?,?,?,?,?)',
                (contact_id,address['kind'])+tuple(address[k] for k in ADDRESS_FIELDS))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return contact_id
