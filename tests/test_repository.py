import pytest
from contactdock.database import create_database
from contactdock.repository import list_contacts


@pytest.fixture
def database(tmp_path):
    c = create_database(tmp_path/'fictional.db','fictional-list-password')
    try:yield c
    finally:c.close()


def add(c, family='', given='', company='', family_kana='', given_kana='', deleted=None):
    return c.execute('''INSERT INTO contacts
        (family_name,given_name,company_name,family_name_kana,given_name_kana,department,job_title,created_at,updated_at,deleted_at)
        VALUES(?,?,?,?,?,'架空部署','架空役職','now','now',?)''',
        (family,given,company,family_kana,given_kana,deleted)).lastrowid


def test_empty_database(database):
    assert list_contacts(database) == []


def test_summary_fields_and_single_row_with_multiple_values(database):
    identifier = add(database,'架空','太郎','架空会社')
    for kind,position,value in [('work_phone',1,'000-1111'),('work_phone',2,'000-2222'),('mobile_phone',1,'000-3333')]:
        database.execute('INSERT INTO contact_phones(contact_id,kind,position,value) VALUES(?,?,?,?)',(identifier,kind,position,value))
    for position,address in [(1,'one@example.invalid'),(2,'two@example.invalid'),(3,'three@example.invalid')]:
        database.execute('INSERT INTO contact_emails(contact_id,position,address) VALUES(?,?,?)',(identifier,position,address))
    database.commit()
    rows = list_contacts(database)
    assert len(rows) == 1
    row = rows[0]
    assert (row.id,row.display_name,row.company_name,row.department,row.job_title) == (identifier,'架空 太郎','架空会社','架空部署','架空役職')
    assert (row.work_phone,row.mobile_phone,row.primary_email) == ('000-1111','000-3333','one@example.invalid')
    assert not database.in_transaction


def test_secondary_values_do_not_replace_first(database):
    identifier = add(database,company='架空会社')
    database.execute("INSERT INTO contact_phones(contact_id,kind,position,value) VALUES(?,'work_phone',2,'000-2222')",(identifier,))
    database.execute("INSERT INTO contact_emails(contact_id,position,address) VALUES(?,2,'two@example.invalid')",(identifier,))
    row = list_contacts(database)[0]
    assert row.display_name == ''
    assert (row.work_phone,row.mobile_phone,row.primary_email) == ('','','')


def test_deleted_excluded(database):
    active = add(database,'表示架空')
    add(database,'削除架空',deleted='2026-10-06T00:00:00Z')
    assert [row.id for row in list_contacts(database)] == [active]
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0] == 2


def test_order_by_reading_name_and_id(database):
    later = add(database,'甲',family_kana='イ')
    first = add(database,'乙',family_kana='ア')
    same = add(database,'丙',family_kana='ア')
    assert [row.id for row in list_contacts(database)] == [first,same,later]


def test_read_does_not_commit_callers_transaction(database):
    identifier = add(database,'架空')
    assert database.in_transaction
    assert list_contacts(database)[0].id == identifier
    assert database.in_transaction
    database.rollback()
    assert list_contacts(database) == []
