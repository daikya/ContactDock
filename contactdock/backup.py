"""Verified encrypted snapshots of the complete ContactDock database."""
import os
from pathlib import Path
import tempfile

from contactdock.database import _connect, open_database
from contactdock.exporter import _protect_database


def backup_database(connection, path, password, *, overwrite=False):
    """Back up committed data using the current database password."""
    if connection.in_transaction:
        raise ValueError('既存のトランザクションを終了してからバックアップしてください。')
    path = Path(path)
    _protect_database(connection, path)
    source = next(filename for _, name, filename in connection.execute('PRAGMA database_list')
                  if name == 'main')
    # Authenticate without retaining the password in the application.
    check = open_database(source, password)
    check.close()
    reserved = False
    temporary = None
    target = None
    try:
        if not overwrite:
            with path.open('xb'):
                pass
            reserved = True
        descriptor, name = tempfile.mkstemp(prefix='.contactdock-backup-', suffix='.db', dir=path.parent)
        os.close(descriptor)
        temporary = Path(name)
        target = _connect(temporary, password)
        connection.backup(target)
        target.close()
        target = None
        check = open_database(temporary, password)
        try:
            if check.execute('PRAGMA cipher_integrity_check').fetchall():
                raise ValueError('暗号化バックアップの整合性を確認できません。')
            if check.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('バックアップの整合性を確認できません。')
            if check.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('バックアップの参照関係を確認できません。')
        finally:
            check.close()
        with temporary.open('r+b') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        reserved = False
    finally:
        if target is not None:
            target.close()
        if temporary is not None:
            for suffix in ('', '-journal', '-wal', '-shm'):
                Path(str(temporary) + suffix).unlink(missing_ok=True)
        if reserved:
            path.unlink(missing_ok=True)
