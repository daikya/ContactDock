"""Read contacts for the list view, independently of the GUI."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ContactSummary:
    id: int
    family_name: str
    given_name: str
    company_name: str
    department: str
    job_title: str
    work_phone: str
    mobile_phone: str
    primary_email: str

    @property
    def display_name(self):
        return ' '.join(value for value in (self.family_name, self.given_name) if value)


# Shared selection: multiple phone/email records never multiply list rows.
_SELECT = """
SELECT c.id,c.family_name,c.given_name,c.company_name,c.department,c.job_title,
    COALESCE((SELECT p.value FROM contact_phones p
        WHERE p.contact_id=c.id AND p.kind='work_phone' AND p.position=1),'') AS work_phone,
    COALESCE((SELECT p.value FROM contact_phones p
        WHERE p.contact_id=c.id AND p.kind='mobile_phone' AND p.position=1),'') AS mobile_phone,
    COALESCE((SELECT e.address FROM contact_emails e
        WHERE e.contact_id=c.id AND e.position=1),'') AS primary_email
FROM contacts c
WHERE c.deleted_at IS NULL
"""
_ORDER = """
ORDER BY CASE WHEN trim(c.family_name_kana)<>'' THEN c.family_name_kana ELSE c.family_name END,
         CASE WHEN trim(c.given_name_kana)<>'' THEN c.given_name_kana ELSE c.given_name END,
         c.id
"""


def list_contacts(connection):
    """Return one summary per active contact without writes or implicit commit.

    Order by surname reading (or surname), given-name reading (or given name),
    then id. Binary order is used, not Japanese linguistic collation.
    Secondary phone/email values never replace an empty first value.
    """
    return [ContactSummary(*row) for row in connection.execute(_SELECT + _ORDER).fetchall()]


def search_contacts(connection, query):
    """Literal partial search; empty input returns all active contacts.

    Search current fields and all phones/email addresses, never import raw data.
    No writes, implicit commit, or wildcard interpretation. Full names also match.
    """
    from contactdock.search import contains_text, contains_phone
    if not isinstance(query, str):
        raise TypeError('検索語は文字列で指定してください。')
    query = query.strip()
    if not query:
        return list_contacts(connection)
    connection.create_function('contactdock_contains', 2, contains_text, deterministic=True)
    connection.create_function('contactdock_phone_contains', 2, contains_phone, deterministic=True)
    fields = ('family_name','given_name','family_name_kana','given_name_kana',
              'company_name','company_name_kana','department','job_title','note')
    conditions = [f'contactdock_contains(c.{field}, ?) = 1' for field in fields]
    # Full name and reading can be typed with or without the display separator.
    for family, given in (('family_name', 'given_name'), ('family_name_kana', 'given_name_kana')):
        conditions.append(f"contactdock_contains(c.{family} || ' ' || c.{given}, ?) = 1")
        conditions.append(f"contactdock_contains(c.{family} || c.{given}, ?) = 1")
    conditions.extend([
        'EXISTS(SELECT 1 FROM contact_phones p WHERE p.contact_id=c.id AND contactdock_phone_contains(p.value, ?) = 1)',
        'EXISTS(SELECT 1 FROM contact_emails e WHERE e.contact_id=c.id AND contactdock_contains(e.address, ?) = 1)',
    ])
    sql = _SELECT + ' AND (' + ' OR '.join(conditions) + ') ' + _ORDER
    return [ContactSummary(*row) for row in connection.execute(sql, (query,) * len(conditions)).fetchall()]


@dataclass(frozen=True)
class ImportSource:
    batch_id: int
    record_number: int
    filename: str
    encoding: str
    sha256: str
    imported_at: str
    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ContactDetail:
    id: int
    fields: dict[str, str]
    created_at: str
    updated_at: str
    phones: tuple[dict, ...]
    emails: tuple[dict, ...]
    addresses: tuple[dict, ...]
    source: ImportSource | None

    @property
    def display_name(self):
        return ' '.join(self.fields[key] for key in ('family_name', 'given_name') if self.fields[key])


def _dict_rows(connection, sql, parameters):
    cursor = connection.execute(sql, parameters)
    names = [column[0] for column in cursor.description]
    return tuple(dict(zip(names, row)) for row in cursor.fetchall())


def get_contact(connection, contact_id):
    """Read a consistent active-contact detail, or return None.

    A savepoint keeps all component reads in the same snapshot and preserves
    the caller's existing transaction. No original CSV BLOB is loaded here.
    """
    import json
    import uuid
    if isinstance(contact_id, bool) or not isinstance(contact_id, int):
        raise TypeError('連絡先IDは整数で指定してください。')
    savepoint = 'contactdock_detail_' + uuid.uuid4().hex
    connection.execute(f'SAVEPOINT {savepoint}')
    try:
        contacts = _dict_rows(connection,
            'SELECT * FROM contacts WHERE id=? AND deleted_at IS NULL', (contact_id,))
        if not contacts:
            detail = None
        else:
            contact = contacts[0]
            field_names = ('family_name','given_name','family_name_kana','given_name_kana',
                           'company_name','company_name_kana','department','job_title',
                           'note','web_page','birthday')
            phones = _dict_rows(connection, '''SELECT kind,position,value FROM contact_phones
                WHERE contact_id=? ORDER BY kind,position,id''', (contact_id,))
            emails = _dict_rows(connection, '''SELECT position,address,display_name,source_type
                FROM contact_emails WHERE contact_id=? ORDER BY position,id''', (contact_id,))
            addresses = _dict_rows(connection, '''SELECT kind,country_region,postal_code,prefecture,
                city,street,post_office_box FROM contact_addresses WHERE contact_id=?
                ORDER BY CASE kind WHEN 'work' THEN 1 WHEN 'home' THEN 2 ELSE 3 END,id''', (contact_id,))
            source = None
            if contact['import_batch_id'] is not None:
                batches = _dict_rows(connection, '''SELECT id,source_filename,source_encoding,
                    source_sha256,imported_at,headers_json FROM import_batches WHERE id=?''',
                    (contact['import_batch_id'],))
                if not batches:
                    raise ValueError('移行元の取込情報が見つかりません。')
                batch = batches[0]
                headers = json.loads(batch['headers_json'])
                values = json.loads(contact['source_values_json'])
                if not isinstance(headers,list) or not isinstance(values,list) or not all(
                        isinstance(value,str) for value in headers + values):
                    raise ValueError('移行元情報の形式が不正です。')
                if len(headers) != len(values):
                    raise ValueError('移行元の項目名と元値の件数が一致しません。')
                source = ImportSource(batch['id'],contact['source_record_number'],
                    batch['source_filename'],batch['source_encoding'],batch['source_sha256'],
                    batch['imported_at'],tuple(zip(headers,values)))
            detail = ContactDetail(contact['id'],{name:contact[name] for name in field_names},
                contact['created_at'],contact['updated_at'],phones,emails,addresses,source)
        connection.execute(f'RELEASE SAVEPOINT {savepoint}')
        return detail
    except BaseException:
        connection.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
        connection.execute(f'RELEASE SAVEPOINT {savepoint}')
        raise
