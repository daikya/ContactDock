"""Input collection and save/cancel behavior without a Tk display."""
from types import SimpleNamespace
from unittest.mock import Mock
from contactdock.editor import ContactEditor
from contactdock.service import ContactInput


def variable(value):
    return SimpleNamespace(get=lambda:value)


def bare_editor():
    editor=ContactEditor.__new__(ContactEditor)
    editor.window=Mock();editor.result=None;editor.save_callback=None
    editor.fields={'company_name':variable('架空会社')}
    editor.note=Mock();editor.note.get.return_value='編集メモ\n末尾行'
    editor.original_note='元メモ\r\n次行\r\n';editor.note_changed=False
    editor.phone_rows=[];editor.email_rows=[];editor.address_rows=[]
    return editor


def test_untouched_note_retains_original_line_endings():
    editor=bare_editor()
    draft=editor.collect()
    assert draft.fields['note']==editor.original_note
    editor.note.get.assert_not_called()


def test_changed_note_uses_input_text():
    editor=bare_editor();editor.note_changed=True
    assert editor.collect().fields['note']=='編集メモ\n末尾行'


def test_cancel_does_not_invoke_save_callback():
    editor=bare_editor();editor.save_callback=Mock()
    editor.cancel()
    editor.save_callback.assert_not_called()
    assert editor.result is None
    editor.window.destroy.assert_called_once()


def test_save_failure_keeps_editor_open():
    editor=bare_editor();editor.save_callback=Mock(return_value=False)
    editor.save()
    editor.save_callback.assert_called_once()
    editor.window.destroy.assert_not_called()
    assert editor.result is None


def test_success_closes_editor_after_callback():
    editor=bare_editor();editor.save_callback=Mock(return_value=True)
    editor.save()
    editor.window.destroy.assert_called_once()
    assert editor.result.fields['company_name']=='架空会社'
