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


def list_contacts(connection):
    """Return one summary per active contact. No writes and no implicit commit.

    Order by surname reading (or surname), given-name reading (or given name),
    then id. SQLite's binary order is used, not Japanese linguistic collation.
    Secondary phone/email values never replace an empty first value.
    """
    rows = connection.execute('''
        SELECT c.id,c.family_name,c.given_name,c.company_name,c.department,c.job_title,
            COALESCE((SELECT p.value FROM contact_phones p
                WHERE p.contact_id=c.id AND p.kind='work_phone' AND p.position=1),'') AS work_phone,
            COALESCE((SELECT p.value FROM contact_phones p
                WHERE p.contact_id=c.id AND p.kind='mobile_phone' AND p.position=1),'') AS mobile_phone,
            COALESCE((SELECT e.address FROM contact_emails e
                WHERE e.contact_id=c.id AND e.position=1),'') AS primary_email
        FROM contacts c
        WHERE c.deleted_at IS NULL
        ORDER BY CASE WHEN trim(c.family_name_kana)<>'' THEN c.family_name_kana ELSE c.family_name END,
                 CASE WHEN trim(c.given_name_kana)<>'' THEN c.given_name_kana ELSE c.given_name END,
                 c.id
    ''').fetchall()
    return [ContactSummary(*row) for row in rows]
