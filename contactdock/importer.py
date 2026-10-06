"""Persist a validated Outlook CSV preview in one transaction."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from contactdock.outlook_csv import CsvPreview, FIELDS


class DuplicateImportError(ValueError):
    """The same original CSV bytes have already been imported."""


@dataclass(frozen=True)
class ImportResult:
    batch_id: int
    contact_count: int
    warning_count: int


def save_csv_preview(connection, preview: CsvPreview):
    """Explicit save operation. Caller reviews preview/warnings before calling.

    A changed CSV adds contacts; existing contacts are never merged or updated.
    Reject an existing transaction rather than committing or rolling it back.
    """
    if connection.in_transaction:
        raise ValueError('既存のトランザクションを終了してから取り込んでください。')
    if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise ValueError('外部キー検証を有効にしてください。')
    if not preview.contacts:
        raise ValueError('保存する連絡先がありません。')
    if hashlib.sha256(preview.original_csv).hexdigest() != preview.source_sha256:
        raise ValueError('CSV原本とハッシュが一致しません。')
    expected_numbers = list(range(1, len(preview.contacts) + 1))
    if [c.record_number for c in preview.contacts] != expected_numbers:
        raise ValueError('元レコード番号が連続していません。')
    if any(len(c.raw_values) != len(preview.headers) for c in preview.contacts):
        raise ValueError('元データの列数が一致しません。')

    # Take a writer lock before checking duplicates, to avoid a check/insert race.
    connection.execute('BEGIN IMMEDIATE')
    try:
        if connection.execute('SELECT id FROM import_batches WHERE source_sha256=?',
                              (preview.source_sha256,)).fetchone():
            raise DuplicateImportError('同じCSVは取込済みです。')
        timestamp = datetime.now(timezone.utc).isoformat(timespec='microseconds')
        cursor = connection.execute('''INSERT INTO import_batches
            (imported_at,source_filename,source_encoding,source_sha256,record_count,headers_json,original_csv)
            VALUES(?,?,?,?,?,?,?)''',
            (timestamp, preview.source_filename, preview.source_encoding, preview.source_sha256,
             len(preview.contacts), json.dumps(preview.headers, ensure_ascii=False), preview.original_csv))
        batch_id = cursor.lastrowid
        field_names = tuple(FIELDS.values()) + ('birthday',)
        columns = ','.join(field_names)
        placeholders = ','.join('?' for _ in range(len(field_names) + 5))
        for contact in preview.contacts:
            cursor = connection.execute(
                f'INSERT INTO contacts({columns},created_at,updated_at,import_batch_id,source_record_number,source_values_json) VALUES({placeholders})',
                tuple(contact.fields[name] for name in field_names) +
                (timestamp, timestamp, batch_id, contact.record_number, contact.source_values_json))
            contact_id = cursor.lastrowid
            for phone in contact.phones:
                connection.execute('INSERT INTO contact_phones(contact_id,kind,position,value) VALUES(?,?,?,?)',
                                   (contact_id, phone['kind'], phone['position'], phone['value']))
            for email in contact.emails:
                connection.execute('''INSERT INTO contact_emails
                    (contact_id,position,address,display_name,source_type) VALUES(?,?,?,?,?)''',
                    (contact_id, email['position'], email['address'], email['display_name'], email['source_type']))
            for address in contact.addresses:
                parts = ('country_region','postal_code','prefecture','city','street','post_office_box')
                connection.execute('''INSERT INTO contact_addresses
                    (contact_id,kind,country_region,postal_code,prefecture,city,street,post_office_box)
                    VALUES(?,?,?,?,?,?,?,?)''', (contact_id, address['kind']) + tuple(address[p] for p in parts))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return ImportResult(batch_id, len(preview.contacts), len(preview.warnings))
