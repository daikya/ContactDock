import pytest
from contactdock.database import create_database
from contactdock.repository import search_contacts, list_contacts
from contactdock.search import normalize_text


@pytest.fixture
def database(tmp_path):
    c = create_database(tmp_path/'fictional.db','fictional-search-password')
    try:yield c
    finally:c.close()


def add(c, **fields):
    fields = dict(created_at='now',updated_at='now',**fields)
    return c.execute('INSERT INTO contacts('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(fields.values())).lastrowid


@pytest.mark.parametrize('field,query',[
    ('family_name','架空'),('given_name','架空'),('family_name_kana','架空'),
    ('given_name_kana','架空'),('company_name','架空'),('company_name_kana','架空'),
    ('department','架空'),('job_title','架空'),('note','架空'),
])
def test_each_search_field(database,field,query):
    identifier = add(database,**{field:'前架空後'})
    assert [r.id for r in search_contacts(database,query)] == [identifier]


def test_note_only_and_original_preserved(database):
    note = '展示会で名刺交換\r\nＡＢＣ ｶﾞｲﾄﾞ\nA-B  二語'
    identifier = add(database,note=note)
    for query in ('展示会','abc','ガイド',' A-B '):
        assert [r.id for r in search_contacts(database,query)] == [identifier]
    assert search_contacts(database,'AB  二語') == []
    assert search_contacts(database,'二 語') == []
    assert database.execute('SELECT note FROM contacts').fetchone()[0] == note


def test_kana_dakuten_and_hiragana_distinct(database):
    add(database,note='ガイド')
    assert len(search_contacts(database,'ｶﾞｲﾄﾞ')) == 1
    assert search_contacts(database,'カイド') == []
    assert search_contacts(database,'がいど') == []


def test_phone_separators_all_phone_values(database):
    identifier = add(database)
    database.execute("INSERT INTO contact_phones(contact_id,kind,position,value) VALUES(?,'work_phone',2,'０１２（３４５）－６７８９')",(identifier,))
    for query in ('0123456789','012-345-6789','０１２ ３４５ ６７８９'):
        assert [r.id for r in search_contacts(database,query)] == [identifier]
    assert search_contacts(database,'999999') == []
    assert search_contacts(database,'---') == []
    assert search_contacts(database,'()') == []


def test_secondary_email_and_single_row(database):
    identifier = add(database,note='example.invalid')
    for pos in (2,3):
        database.execute('INSERT INTO contact_emails(contact_id,position,address) VALUES(?,?,?)',(identifier,pos,f'contact{pos}@example.invalid'))
    assert [r.id for r in search_contacts(database,'EXAMPLE.INVALID')] == [identifier]
    assert search_contacts(database,'contact3@')[0].primary_email == ''


def test_empty_whitespace_deleted_and_no_match(database):
    active = add(database,note='unique')
    add(database,note='unique',deleted_at='deleted')
    for query in ('',' \t\u3000'):
        assert search_contacts(database,query) == list_contacts(database)
    assert [r.id for r in search_contacts(database,'unique')] == [active]
    assert search_contacts(database,'absent') == []


def test_literal_wildcards_and_quotes(database):
    identifier = add(database,note="50%_ 'special'")
    add(database,note='ordinary')
    for query in ('%','_',"'special'","50%_"):
        assert [r.id for r in search_contacts(database,query)] == [identifier]
    assert search_contacts(database,"' OR 1=1 --") == []


def test_no_cross_line_matching_and_full_names(database):
    add(database,family_name='架空',given_name='太郎',note='展示\n会')
    assert search_contacts(database,'展示会') == []
    assert search_contacts(database,'展示\n会') == []
    assert len(search_contacts(database,'架空 太郎')) == 1
    assert len(search_contacts(database,'架空太郎')) == 1


def test_address_web_birthday_and_source_not_searched(database):
    identifier = add(database,web_page='unique-web',birthday='2000-01-01')
    database.execute("INSERT INTO contact_addresses(contact_id,kind,city) VALUES(?,'work','unique-city')",(identifier,))
    for query in ('unique-web','2000-01-01','unique-city'):
        assert search_contacts(database,query) == []


def test_read_does_not_commit(database):
    add(database,note='pending')
    assert len(search_contacts(database,'pending')) == 1
    assert database.in_transaction
    database.rollback()
    assert search_contacts(database,'pending') == []


def test_width_normalization_is_limited():
    assert normalize_text('ＡＢＣ１２３ ｶﾞｲﾄﾞ') == 'abc123 ガイド'
    assert normalize_text('①') == '①'
