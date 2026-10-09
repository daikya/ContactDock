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

@pytest.mark.parametrize('cancel_at',['file','password'])
def test_backup_cancel(database,tmp_path,monkeypatch,cancel_at):
    app=app_without_display(database);path=tmp_path/'backup.db'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:'' if cancel_at=='file' else str(path))
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:None)
    app.backup_database()
    assert not path.exists()


def test_backup_gui_saves_and_reports(database,tmp_path,monkeypatch):
    from contactdock.database import open_database
    app=app_without_display(database);path=tmp_path/'backup.db'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(path))
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:'fictional-gui-password')
    info=Mock();monkeypatch.setattr(gui.messagebox,'showinfo',info)
    app.backup_database()
    c=open_database(path,'fictional-gui-password');c.close()
    info.assert_called_once()


def test_backup_gui_wrong_password_keeps_existing_file(database,tmp_path,monkeypatch):
    app=app_without_display(database);path=tmp_path/'backup.db';path.write_bytes(b'keep')
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(path))
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:'wrong-password')
    error=Mock();monkeypatch.setattr(gui.messagebox,'showerror',error)
    app.backup_database()
    assert path.read_bytes()==b'keep'
    error.assert_called_once()


@pytest.mark.parametrize('cancel_at',[0,1,2,3])
def test_password_change_cancelled(database,tmp_path,monkeypatch,cancel_at):
    app=app_without_display(database)
    responses=['fictional-gui-password','fictional-new','fictional-new']
    if cancel_at<3:responses[cancel_at]=None
    answers=iter(responses)
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:next(answers))
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a,**kw:False)
    change=Mock();monkeypatch.setattr(gui,'change_database_password',change)
    app.change_password();change.assert_not_called()


def test_password_change_gui_success(database,tmp_path,monkeypatch):
    from contactdock.database import open_database,DatabaseOpenError
    app=app_without_display(database)
    answers=iter(['fictional-gui-password','fictional-new','fictional-new'])
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:next(answers))
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a,**kw:True)
    info=Mock();monkeypatch.setattr(gui.messagebox,'showinfo',info)
    app.change_password();info.assert_called_once()
    c=open_database(tmp_path/'fictional.db','fictional-new');c.close()
    with pytest.raises(DatabaseOpenError):open_database(tmp_path/'fictional.db','fictional-gui-password')


@pytest.mark.parametrize('answers',[['fictional-gui-password','one','two'],['wrong','new','new']])
def test_password_change_gui_invalid_input(database,tmp_path,monkeypatch,answers):
    from contactdock.database import open_database
    app=app_without_display(database);responses=iter(answers)
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:next(responses))
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a,**kw:True)
    error=Mock();monkeypatch.setattr(gui.messagebox,'showerror',error)
    app.change_password();error.assert_called_once()
    c=open_database(tmp_path/'fictional.db','fictional-gui-password');c.close()


def test_password_change_uncertain_outcome_closes_session(database,monkeypatch):
    app=app_without_display(database)
    for name in ('entry','import_button','search_button','clear_button','new_button','export_button','original_button','backup_button','password_button','file_label','status','tree'):
        setattr(app,name,Mock())
    app.clear_detail=Mock()
    app.tree.get_children.return_value=()
    answers=iter(['fictional-gui-password','new','new'])
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:next(answers))
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a,**kw:True)
    monkeypatch.setattr(gui.messagebox,'showerror',Mock())
    def fail(*args):raise gui.PasswordChangeError('fictional uncertain outcome')
    monkeypatch.setattr(gui,'change_database_password',fail)
    app.change_password()
    assert app.connection is None
    app.password_button.configure.assert_called_once_with(state='disabled')


def settings_app(tmp_path):
    from contactdock.settings import Settings
    app=app_without_display(None);app.root=Mock();app.settings=Settings(tmp_path/'settings.json')
    for name in ('file_label','entry','import_button','search_button','clear_button','new_button','export_button','original_button','backup_button','password_button'):
        setattr(app,name,Mock())
    return app


def test_database_success_remembers_location(tmp_path,monkeypatch):
    app=settings_app(tmp_path);path=tmp_path/'new.db'
    monkeypatch.setattr(gui.filedialog,'asksaveasfilename',lambda **kw:str(path))
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:'fictional-password')
    app.choose_database(True)
    try:
        assert app.settings.data['last_database']==str(path)
        assert app.settings.path.exists()
    finally:app.connection.close()


def test_failed_database_open_does_not_change_remembered_location(tmp_path,monkeypatch):
    app=settings_app(tmp_path);app.settings.remember_database(tmp_path/'previous.db')
    before=app.settings.path.read_bytes()
    monkeypatch.setattr(gui.filedialog,'askopenfilename',lambda **kw:str(tmp_path/'missing.db'))
    monkeypatch.setattr(gui.simpledialog,'askstring',lambda *a,**kw:'fictional-password')
    monkeypatch.setattr(gui.messagebox,'showerror',Mock())
    app.choose_database(False)
    assert app.connection is None and app.settings.path.read_bytes()==before


def test_database_dialog_uses_remembered_location(tmp_path,monkeypatch):
    app=settings_app(tmp_path);path=tmp_path/'previous.db';path.touch()
    app.settings.remember_database(path)
    choose=Mock(return_value='');monkeypatch.setattr(gui.filedialog,'askopenfilename',choose)
    app.choose_database(False)
    assert choose.call_args.kwargs['initialdir']==str(tmp_path)
    assert choose.call_args.kwargs['initialfile']=='previous.db'


def test_gui_imports_contactdock_export(database,tmp_path,monkeypatch):
    from contactdock.service import ContactInput,save_contact
    from contactdock.exporter import export_current_csv
    save_contact(database,ContactInput({'note':'架空の再取込メモ🙂'}))
    path=tmp_path/'current.csv';export_current_csv(database,path)
    app=app_without_display(database)
    monkeypatch.setattr(gui.filedialog,'askopenfilename',lambda **kw:str(path))
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda *a,**kw:True)
    monkeypatch.setattr(gui.messagebox,'showinfo',Mock())
    app.import_csv()
    assert database.execute('SELECT count(*) FROM contacts').fetchone()[0]==2
    assert database.execute('SELECT source_encoding FROM import_batches').fetchone()[0]=='utf-8-sig'
    app.refresh.assert_called_once()
