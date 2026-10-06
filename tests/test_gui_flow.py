"""Non-display GUI flow tests; actual rendering is checked on Windows."""
import csv
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from contactdock import gui
from contactdock.database import create_database
from contactdock.outlook_csv import HEADERS, read_outlook_csv
from contactdock.importer import save_csv_preview
from contactdock.repository import get_contact


@pytest.fixture
def database(tmp_path):
    c=create_database(tmp_path/'fictional.db','fictional-gui-password')
    try:yield c
    finally:c.close()


def csv_file(tmp_path):
    path=tmp_path/'fictional.csv'
    values={'姓':'架空','メモ':'秘密の本文\r\n検索語','優先度':'低'}
    with path.open('w',encoding='cp932',newline='') as f:
        w=csv.writer(f);w.writerow(HEADERS);w.writerow([values.get(h,'') for h in HEADERS])
    return path


def test_detail_preserves_note_and_source(database,tmp_path):
    p=read_outlook_csv(csv_file(tmp_path));save_csv_preview(database,p)
    identifier=database.execute('SELECT id FROM contacts').fetchone()[0]
    detail=get_contact(database,identifier)
    assert detail.fields['note'] in gui.format_detail(detail)
    assert '優先度：低' in gui.format_source(detail)
    assert 'メモ：秘密の本文\r\n検索語' in gui.format_source(detail)


def test_confirmation_does_not_list_private_values(tmp_path):
    p=read_outlook_csv(csv_file(tmp_path))
    text=gui.import_confirmation(p)
    assert '1件' in text and '優先度' in text
    assert '秘密の本文' not in text and '架空' not in text


def app_without_display(c):
    app=gui.ContactDockApplication.__new__(gui.ContactDockApplication)
    app.connection=c;app.root=None;app.query=SimpleNamespace(set=Mock());app.refresh=Mock()
    return app


def test_cancelled_import_does_not_save(database,tmp_path,monkeypatch):
    app=app_without_display(database)
    monkeypatch.setattr(gui.filedialog,'askopenfilename',lambda **kw:str(csv_file(tmp_path)))
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *args,**kw:False)
    app.import_csv()
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==0
    assert database.execute('SELECT count(*) FROM import_batches').fetchone()[0]==0
    app.refresh.assert_not_called()


def test_duplicate_import_does_not_prompt_or_save(database,tmp_path,monkeypatch):
    path=csv_file(tmp_path);save_csv_preview(database,read_outlook_csv(path))
    app=app_without_display(database)
    monkeypatch.setattr(gui.filedialog,'askopenfilename',lambda **kw:str(path))
    confirm=Mock();monkeypatch.setattr(gui.messagebox,'askyesno',confirm)
    monkeypatch.setattr(gui.messagebox,'showinfo',Mock())
    app.import_csv()
    confirm.assert_not_called()
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==1


def test_confirmed_import_refreshes_list(database,tmp_path,monkeypatch):
    app=app_without_display(database)
    monkeypatch.setattr(gui.filedialog,'askopenfilename',lambda **kw:str(csv_file(tmp_path)))
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *args,**kw:True)
    monkeypatch.setattr(gui.messagebox,'showinfo',Mock())
    app.import_csv()
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==1
    app.query.set.assert_called_once_with('');app.refresh.assert_called_once()
