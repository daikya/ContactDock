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
