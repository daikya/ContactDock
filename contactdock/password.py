"""Change an encrypted database password without changing contact data."""
from contactdock.database import open_database


class PasswordChangeError(Exception):
    """The outcome needs checking by reopening the database."""


def change_database_password(connection, current_password, new_password):
    if not isinstance(new_password,str) or not new_password.strip():
        raise ValueError('新しいパスワードを空にできません。')
    if '\x00' in new_password:
        raise ValueError('パスワードに使用できない文字が含まれています。')
    if current_password == new_password:
        raise ValueError('現在と異なるパスワードを指定してください。')
    if connection.in_transaction:
        raise ValueError('既存のトランザクションを終了してから変更してください。')
    if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
        raise ValueError('パスワード変更はDELETEジャーナルモードのDBに対応しています。')
    source=next(filename for _,name,filename in connection.execute('PRAGMA database_list') if name=='main')
    check=open_database(source,current_password)
    check.close()
    quoted=new_password.replace("'","''")
    try:
        connection.execute("PRAGMA rekey='"+quoted+"'")
        check=open_database(source,new_password)
        try:
            if check.execute('PRAGMA cipher_integrity_check').fetchall():
                raise ValueError('暗号化DBの整合性を確認できません。')
            if check.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                raise ValueError('DBの整合性を確認できません。')
            if check.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('DBの参照関係を確認できません。')
        finally:
            check.close()
    except Exception as exc:
        raise PasswordChangeError('変更処理を確認できません。アプリを終了し、新しいパスワードでDBを開き直してください。開けない場合は元のパスワードを確認してください。') from exc
