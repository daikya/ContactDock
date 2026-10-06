"""User-local window geometry and database location settings."""
import json
import os
from pathlib import Path
import tempfile


def default_settings_path():
    directory=Path(os.environ['APPDATA']) if os.environ.get('APPDATA') else Path.home()/'.config'
    return directory/'ContactDock'/'settings.json'


def valid_geometry(value):
    return (isinstance(value,dict) and all(type(value.get(k)) is int for k in ('width','height','x','y'))
            and 100<=value['width']<=10000 and 80<=value['height']<=10000
            and abs(value['x'])<=100000 and abs(value['y'])<=100000)


class Settings:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else default_settings_path()
        self.data={'windows':{}}
        self.last_error=None
        try:
            value=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(value,dict):
                windows=value.get('windows',{})
                if isinstance(windows,dict):
                    self.data['windows']={k:v for k,v in windows.items() if isinstance(k,str) and valid_geometry(v)}
                for key in ('last_database','database_directory'):
                    if isinstance(value.get(key),str) and '\x00' not in value[key]:self.data[key]=value[key]
        except (OSError,ValueError):
            pass

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        descriptor,name=tempfile.mkstemp(prefix='.settings-',suffix='.tmp',dir=self.path.parent)
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8') as f:
                json.dump(self.data,f,ensure_ascii=False,indent=2)
                f.write('\n');f.flush();os.fsync(f.fileno())
            os.replace(name,self.path)
            self.last_error=None
        finally:
            Path(name).unlink(missing_ok=True)

    def try_save(self):
        try:self.save();return True
        except OSError as exc:self.last_error=exc;return False

    def remember_database(self,path):
        path=Path(path).resolve()
        self.data['last_database']=str(path)
        self.data['database_directory']=str(path.parent)
        return self.try_save()

    def database_options(self,create):
        directory=self.data.get('database_directory')
        if not directory or not Path(directory).is_dir():return {}
        options={'initialdir':directory}
        last=self.data.get('last_database')
        if not create and last and Path(last).is_file() and Path(last).parent==Path(directory):
            options['initialfile']=Path(last).name
        return options


def monitor_areas(window):
    if os.name=='nt':
        try:
            import ctypes
            from ctypes import wintypes
            class MonitorInfo(ctypes.Structure):
                _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
            user32=ctypes.WinDLL('user32',use_last_error=True)
            callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
            user32.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
            user32.GetMonitorInfoW.restype=wintypes.BOOL
            user32.EnumDisplayMonitors.argtypes=[wintypes.HDC,ctypes.POINTER(wintypes.RECT),callback_type,wintypes.LPARAM]
            user32.EnumDisplayMonitors.restype=wintypes.BOOL
            areas=[]
            def collect(handle,dc,rectangle,data):
                info=MonitorInfo();info.size=ctypes.sizeof(info)
                if user32.GetMonitorInfoW(handle,ctypes.byref(info)):
                    r=info.work;areas.append((bool(info.flags&1),(r.left,r.top,r.right,r.bottom)))
                return True
            callback=callback_type(collect)
            if user32.EnumDisplayMonitors(None,None,callback,0) and areas:
                return [r for _,r in sorted(areas,key=lambda item:not item[0])]
        except (OSError,AttributeError):
            pass
    return [(0,0,window.winfo_screenwidth(),window.winfo_screenheight())]


def place_geometry(saved,width,height,areas,parent_center=None):
    """Keep a restored window on an available monitor; otherwise center it."""
    center=parent_center
    if valid_geometry(saved):center=(saved['x']+saved['width']//2,saved['y']+saved['height']//2)
    area=next((r for r in areas if center and r[0]<=center[0]<r[2] and r[1]<=center[1]<r[3]),None)
    restore=area is not None and valid_geometry(saved)
    if area is None:area=areas[0]
    left,top,right,bottom=area
    w=min(saved['width'] if restore else width,right-left)
    h=min(saved['height'] if restore else height,bottom-top-40)
    x=min(max(saved['x'],left),right-w) if restore else left+(right-left-w)//2
    y=min(max(saved['y'],top+30),bottom-h) if restore else top+(bottom-top-h)//2
    return {'width':w,'height':h,'x':x,'y':y}


def remember_window(window,key,settings,parent=None,default_size=None):
    window.update_idletasks()
    center=None
    if parent is not None:
        center=(parent.winfo_x()+parent.winfo_width()//2,parent.winfo_y()+parent.winfo_height()//2)
    width,height=default_size or (window.winfo_reqwidth(),window.winfo_reqheight())
    geometry=place_geometry(settings.data['windows'].get(key),width,height,monitor_areas(window),center)
    minimum=window.minsize()
    window.minsize(min(minimum[0],geometry['width']),min(minimum[1],geometry['height']))
    window.geometry(f"{geometry['width']}x{geometry['height']}+{geometry['x']}+{geometry['y']}")
    settings.data['windows'][key]=geometry
    def capture(event):
        if event.widget is window and window.state()=='normal':
            value={'width':window.winfo_width(),'height':window.winfo_height(),'x':window.winfo_x(),'y':window.winfo_y()}
            if valid_geometry(value):settings.data['windows'][key]=value
    def closed(event):
        if event.widget is window:settings.try_save()
    window.bind('<Configure>',capture,add='+')
    window.bind('<Destroy>',closed,add='+')
