"""Encrypted database lifecycle. No real contact data is bundled."""
from pathlib import Path
from sqlcipher3 import dbapi2 as sqlite

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE import_batches (
 id INTEGER PRIMARY KEY, imported_at TEXT NOT NULL,
 source_filename TEXT NOT NULL, source_encoding TEXT NOT NULL,
 source_sha256 TEXT NOT NULL UNIQUE, record_count INTEGER NOT NULL CHECK(record_count >= 0),
 headers_json TEXT NOT NULL, original_csv BLOB NOT NULL
);
CREATE TABLE contacts (
 id INTEGER PRIMARY KEY,
 family_name TEXT NOT NULL DEFAULT '', given_name TEXT NOT NULL DEFAULT '',
 family_name_kana TEXT NOT NULL DEFAULT '', given_name_kana TEXT NOT NULL DEFAULT '',
 company_name TEXT NOT NULL DEFAULT '', company_name_kana TEXT NOT NULL DEFAULT '',
 department TEXT NOT NULL DEFAULT '', job_title TEXT NOT NULL DEFAULT '',
 note TEXT NOT NULL DEFAULT '', web_page TEXT NOT NULL DEFAULT '', birthday TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,
 import_batch_id INTEGER REFERENCES import_batches(id), source_record_number INTEGER,
 source_values_json TEXT,
 UNIQUE(import_batch_id, source_record_number),
 CHECK ((import_batch_id IS NULL AND source_record_number IS NULL AND source_values_json IS NULL)
 OR (import_batch_id IS NOT NULL AND source_record_number IS NOT NULL AND source_record_number > 0 AND source_values_json IS NOT NULL))
);
CREATE TABLE contact_phones (
 id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL REFERENCES contacts(id),
 kind TEXT NOT NULL, position INTEGER NOT NULL CHECK(position > 0), value TEXT NOT NULL,
 UNIQUE(contact_id, kind, position)
);
CREATE TABLE contact_emails (
 id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL REFERENCES contacts(id),
 position INTEGER NOT NULL CHECK(position > 0), address TEXT NOT NULL DEFAULT '',
 display_name TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL DEFAULT '',
 UNIQUE(contact_id, position)
);
CREATE TABLE contact_addresses (
 id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL REFERENCES contacts(id),
 kind TEXT NOT NULL CHECK(kind IN ('work','home','other')),
 country_region TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '',
 prefecture TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
 street TEXT NOT NULL DEFAULT '', post_office_box TEXT NOT NULL DEFAULT '',
 UNIQUE(contact_id, kind)
);
PRAGMA user_version=1;
"""


class DatabaseOpenError(Exception):
    """Incorrect password, damaged file, or incompatible database."""


def _connect(path, password):
    if not isinstance(password, str) or not password.strip():
        raise ValueError("パスワードを空にできません。")
    connection = sqlite.connect(str(path))
    try:
        version = connection.execute('PRAGMA cipher_version').fetchone()
        if not version or not version[0]:
            raise RuntimeError("SQLCipherが有効ではありません。")
        quoted = password.replace("'", "''")
        connection.execute("PRAGMA key='" + quoted + "'")
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA temp_store=MEMORY')
        return connection
    except Exception:
        connection.close()
        raise


def create_database(path, password):
    """Create a new database; never overwrite an existing path. Caller closes connection."""
    path = Path(path)
    # Validate before reserving the filename. Exclusive creation prevents accidental overwrite.
    if not isinstance(password, str) or not password.strip():
        raise ValueError("パスワードを空にできません。")
    with path.open('xb'):
        pass
    connection = None
    try:
        connection = _connect(path, password)
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.executescript('BEGIN;\n' + SCHEMA + '\nCOMMIT;')
        return connection
    except Exception:
        if connection is not None:
            connection.close()
        path.unlink(missing_ok=True)
        raise


def open_database(path, password):
    """Open an existing ContactDock database without creating a missing file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = _connect(path, password)
    try:
        connection.execute('SELECT count(*) FROM sqlite_master').fetchone()
        if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
            raise DatabaseOpenError("未対応のDBバージョンです。")
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'contacts','contact_phones','contact_emails','contact_addresses','import_batches'} <= tables:
            raise DatabaseOpenError("ContactDockのDB構造を確認できません。")
        return connection
    except sqlite.DatabaseError as exc:
        connection.close()
        raise DatabaseOpenError("パスワード、ファイルの破損、互換性を確認してください。") from exc
    except Exception:
        connection.close()
        raise
