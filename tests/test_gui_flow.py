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


def test_new_editor_cancel_does_not_save(database,monkeypatch):
    from contactdock import editor
    app=app_without_display(database)
    fake=Mock();fake.show.return_value=None
    monkeypatch.setattr(editor,'ContactEditor',lambda *args,**kw:fake)
    app.edit_contact(False)
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==0
    app.refresh.assert_not_called()


def test_new_editor_save_persists_and_selects_contact(database,monkeypatch):
    from contactdock import editor
    from contactdock.service import ContactInput
    app=app_without_display(database);app.tree=Mock();app.tree.exists.return_value=True
    app.select_contact=Mock()
    class FakeEditor:
        def __init__(self,parent,detail,save_callback):
            self.window=Mock();self.save_callback=save_callback
        def show(self):
            assert self.save_callback(ContactInput({'company_name':'架空会社'}))
    monkeypatch.setattr(editor,'ContactEditor',FakeEditor)
    app.edit_contact(False)
    row=database.execute('SELECT id,company_name FROM contacts').fetchone()
    assert row[1]=='架空会社'
    app.refresh.assert_called_once();app.tree.selection_set.assert_called_once_with(str(row[0]))
    app.select_contact.assert_called_once()


def selected_delete_app(c):
    from contactdock.service import ContactInput,save_contact
    identifier=save_contact(c,ContactInput({'family_name':'架空','company_name':'架空会社'}))
    app=app_without_display(c);app.tree=Mock();app.tree.selection.return_value=(str(identifier),)
    return app,identifier


def test_delete_confirmation_cancel_keeps_contact(database,monkeypatch):
    app,identifier=selected_delete_app(database)
    confirm=Mock(return_value=False);monkeypatch.setattr(gui.messagebox,'askyesno',confirm)
    app.delete_selected_contact()
    assert get_contact(database,identifier) is not None
    app.refresh.assert_not_called()
    message=confirm.call_args.args[1]
    assert '架空会社' in message and 'データは内部に保持' in message


def test_delete_confirmation_accepts_then_refreshes(database,monkeypatch):
    app,identifier=selected_delete_app(database)
    monkeypatch.setattr(gui.messagebox,'askyesno',Mock(return_value=True))
    app.delete_selected_contact()
    assert get_contact(database,identifier) is None
    app.refresh.assert_called_once()


def test_delete_without_selection_does_not_prompt(database,monkeypatch):
    app=app_without_display(database);app.tree=Mock();app.tree.selection.return_value=()
    confirm=Mock();monkeypatch.setattr(gui.messagebox,'askyesno',confirm)
    app.delete_selected_contact()
    confirm.assert_not_called()


def test_export_cancel_does_not_create_file(database,tmp_path,monkeypatch):
    app=app_without_display(database);path=tmp_path/'cancel.csv'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(path))
    confirm=Mock(return_value=False);monkeypatch.setattr(gui.messagebox,'askyesno',confirm)
    app.export_contacts()
    assert not path.exists() and '暗号化されず' in confirm.call_args.args[1]


def test_confirmed_export_writes_file(database,tmp_path,monkeypatch):
    from contactdock.service import ContactInput,save_contact
    save_contact(database,ContactInput({'note':'架空メモ'}))
    app=app_without_display(database);path=tmp_path/'current.csv'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(path))
    monkeypatch.setattr(gui.messagebox,'askyesno',Mock(return_value=True))
    monkeypatch.setattr(gui.messagebox,'showinfo',Mock())
    app.export_contacts()
    assert path.exists() and '架空メモ' in path.read_text(encoding='utf-8-sig')


def test_original_export_cancel_does_not_create_file(database,tmp_path,monkeypatch):
    p=read_outlook_csv(csv_file(tmp_path));save_csv_preview(database,p)
    app=app_without_display(database);path=tmp_path/'original.csv'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(path))
    monkeypatch.setattr(gui.messagebox,'askyesno',Mock(return_value=False))
    app.export_source()
    assert not path.exists()


def test_original_export_byte_exact(database,tmp_path,monkeypatch):
    p=read_outlook_csv(csv_file(tmp_path));save_csv_preview(database,p)
    app=app_without_display(database);path=tmp_path/'original.csv'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(path))
    monkeypatch.setattr(gui.messagebox,'askyesno',Mock(return_value=True))
    monkeypatch.setattr(gui.messagebox,'showinfo',Mock())
    app.export_source()
    assert path.read_bytes()==p.original_csv
