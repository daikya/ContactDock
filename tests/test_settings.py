import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from contactdock import settings


def test_first_run_and_settings_roundtrip(tmp_path):
    path=tmp_path/'settings.json';s=settings.Settings(path)
    assert s.data=={'windows':{}}
    s.data['windows']['main']={'width':1000,'height':700,'x':120,'y':80}
    db=tmp_path/'架空.db';db.touch()
    assert s.remember_database(db)
    loaded=settings.Settings(path)
    assert loaded.data==s.data
    assert loaded.database_options(False)=={'initialdir':str(tmp_path),'initialfile':'架空.db'}
    assert loaded.database_options(True)=={'initialdir':str(tmp_path)}
    assert set(json.loads(path.read_text(encoding='utf-8')))=={'windows','last_database','database_directory'}


@pytest.mark.parametrize('contents',['not json','[]','{"windows":42}','{"windows":{"main":{"width":true}}}'])
def test_invalid_settings_use_defaults(tmp_path,contents):
    path=tmp_path/'settings.json';path.write_text(contents)
    s=settings.Settings(path);assert s.data=={'windows':{}}


def test_missing_database_directory_falls_back(tmp_path):
    s=settings.Settings(tmp_path/'settings.json');s.data['database_directory']=str(tmp_path/'missing')
    assert s.database_options(False)=={}


def test_missing_last_database_keeps_directory(tmp_path):
    s=settings.Settings(tmp_path/'settings.json');s.data.update(database_directory=str(tmp_path),last_database=str(tmp_path/'missing.db'))
    assert s.database_options(False)=={'initialdir':str(tmp_path)}


def test_save_failure_keeps_existing_json(tmp_path,monkeypatch):
    s=settings.Settings(tmp_path/'settings.json');s.save();before=s.path.read_bytes()
    def fail(*a):raise OSError('fictional failure')
    monkeypatch.setattr(settings.os,'replace',fail)
    assert not s.remember_database(tmp_path/'db.db')
    assert s.path.read_bytes()==before and s.last_error is not None
    assert not list(tmp_path.glob('.settings-*'))


def test_settings_path_is_user_local(tmp_path,monkeypatch):
    monkeypatch.setenv('APPDATA',str(tmp_path))
    assert settings.default_settings_path()==tmp_path/'ContactDock'/'settings.json'


AREAS=[(0,0,1920,1040),(-1920,0,0,1040)]


def test_initial_window_centered():
    g=settings.place_geometry(None,1000,700,AREAS)
    assert g=={'width':1000,'height':700,'x':460,'y':170}


def test_subwindow_centers_on_parents_monitor():
    g=settings.place_geometry(None,800,600,AREAS,(-1000,500))
    assert g['x']==-1360 and g['y']==220


def test_geometry_restored_on_negative_monitor():
    saved={'width':800,'height':600,'x':-1800,'y':100}
    assert settings.place_geometry(saved,1000,700,AREAS)==saved


def test_removed_monitor_returns_to_center():
    saved={'width':800,'height':600,'x':5000,'y':100}
    assert settings.place_geometry(saved,1000,700,AREAS)['x']==460


def test_oversized_window_clamped():
    saved={'width':2500,'height':1500,'x':-100,'y':-20}
    g=settings.place_geometry(saved,1000,700,AREAS)
    assert g['width']==1920 and g['height']==1000
    assert g['x']==0 and g['y']==30


def test_window_capture_ignores_child_and_maximized_events(tmp_path,monkeypatch):
    s=settings.Settings(tmp_path/'settings.json')
    window=Mock();window.winfo_reqwidth.return_value=1000;window.winfo_reqheight.return_value=700
    window.minsize.return_value=(900,560)
    window.state.return_value='normal'
    window.winfo_width.return_value=1100;window.winfo_height.return_value=750
    window.winfo_x.return_value=200;window.winfo_y.return_value=90
    monkeypatch.setattr(settings,'monitor_areas',lambda w:AREAS)
    settings.remember_window(window,'main',s)
    callbacks={args[0]:args[1] for args,kw in window.bind.call_args_list}
    original=s.data['windows']['main'].copy()
    callbacks['<Configure>'](SimpleNamespace(widget=object()))
    assert s.data['windows']['main']==original
    window.state.return_value='zoomed';callbacks['<Configure>'](SimpleNamespace(widget=window))
    assert s.data['windows']['main']==original
    window.state.return_value='normal';callbacks['<Configure>'](SimpleNamespace(widget=window))
    assert s.data['windows']['main']=={'width':1100,'height':750,'x':200,'y':90}
    callbacks['<Destroy>'](SimpleNamespace(widget=window))
    assert settings.Settings(s.path).data==s.data
