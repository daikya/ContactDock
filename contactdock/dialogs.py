"""Position-aware masked input dialogs."""
import tkinter as tk
from tkinter import ttk
from contactdock.settings import remember_window


def askstring(title,prompt,*,parent,show=None):
    window=tk.Toplevel(parent);window.withdraw();window.title(title)
    window.transient(parent);window.resizable(False,False)
    ttk.Label(window,text=prompt,wraplength=420).pack(padx=18,pady=(16,8))
    entry=ttk.Entry(window,width=42,show=show or '')
    entry.pack(padx=18,pady=8)
    result=None
    def accept(event=None):
        nonlocal result
        result=entry.get();window.destroy()
    def cancel(event=None):window.destroy()
    buttons=ttk.Frame(window);buttons.pack(padx=18,pady=(8,16),fill='x')
    ttk.Button(buttons,text='キャンセル',command=cancel).pack(side='right')
    ttk.Button(buttons,text='OK',command=accept).pack(side='right',padx=8)
    window.protocol('WM_DELETE_WINDOW',cancel)
    window.bind('<Return>',accept);window.bind('<Escape>',cancel)
    settings=getattr(parent,'contactdock_settings',None)
    if settings is not None:remember_window(window,'input:'+title,settings,parent)
    window.deiconify();window.wait_visibility();window.grab_set();entry.focus_set()
    window.wait_window()
    return result
