"""Shared modal editor. Collect input here; persistence belongs to service.py."""
import tkinter as tk
from tkinter import ttk, messagebox
from contactdock.gui import FIELD_LABELS, PHONE_LABELS, ADDRESS_LABELS
from contactdock.service import ContactInput, ContactValidationError, validate_contact

ADDRESS_LABELS_FIELDS = (
    ('country_region','国／地域'),('postal_code','郵便番号'),('prefecture','都道府県'),
    ('city','市町村'),('street','番地'),('post_office_box','私書箱'),
)


class ContactEditor:
    def __init__(self,parent,detail=None,save_callback=None):
        self.result=None
        self.save_callback=save_callback
        self.window=tk.Toplevel(parent)
        self.window.withdraw()
        self.window.title('連絡先の編集' if detail else '連絡先の新規登録')
        self.window.geometry('850x650');self.window.minsize(650,480)
        self.window.transient(parent)
        self.window.protocol('WM_DELETE_WINDOW',self.cancel)
        self.fields={};self.phone_rows=[];self.email_rows=[];self.address_rows=[]
        self.original_note=detail.fields['note'] if detail else ''
        self.note_changed=False
        notebook=ttk.Notebook(self.window);notebook.pack(fill='both',expand=True,padx=8,pady=8)
        basic=self.scroll_tab(notebook,'氏名・所属')
        for row,(key,label) in enumerate(FIELD_LABELS.items()):
            ttk.Label(basic,text=label).grid(row=row,column=0,sticky='w',padx=8,pady=5)
            variable=tk.StringVar(value=detail.fields[key] if detail else '')
            self.fields[key]=variable
            ttk.Entry(basic,textvariable=variable,width=55).grid(row=row,column=1,sticky='ew',padx=8,pady=5)
        basic.columnconfigure(1,weight=1)
        note_frame=ttk.Frame(notebook);notebook.add(note_frame,text='メモ')
        self.note=tk.Text(note_frame,wrap='word',undo=True)
        scrollbar=ttk.Scrollbar(note_frame,command=self.note.yview);self.note.configure(yscrollcommand=scrollbar.set)
        self.note.pack(side='left',fill='both',expand=True);scrollbar.pack(side='right',fill='y')
        self.note.insert('1.0',self.original_note)
        self.note.edit_reset()
        self.note.edit_modified(False)
        self.note.bind('<<Modified>>',self.note_modified)
        self.phone_frame=self.scroll_tab(notebook,'電話・FAX等')
        ttk.Button(self.phone_frame,text='電話を追加',command=self.add_phone).pack(anchor='w',padx=8,pady=6)
        for phone in detail.phones if detail else ():self.add_phone(phone)
        self.email_frame=self.scroll_tab(notebook,'メール')
        ttk.Button(self.email_frame,text='メールを追加',command=self.add_email).pack(anchor='w',padx=8,pady=6)
        for email in detail.emails if detail else ():self.add_email(email)
        address_frame=self.scroll_tab(notebook,'住所')
        existing={a['kind']:a for a in detail.addresses} if detail else {}
        for kind,label in ADDRESS_LABELS.items():
            frame=ttk.LabelFrame(address_frame,text=label,padding=8);frame.pack(fill='x',padx=8,pady=6)
            fields={}
            for row,(key,title) in enumerate(ADDRESS_LABELS_FIELDS):
                ttk.Label(frame,text=title).grid(row=row,column=0,sticky='w',pady=3)
                variable=tk.StringVar(value=existing.get(kind,{}).get(key,''));fields[key]=variable
                ttk.Entry(frame,textvariable=variable,width=55).grid(row=row,column=1,sticky='ew',padx=8,pady=3)
            frame.columnconfigure(1,weight=1);self.address_rows.append((kind,fields))
        controls=ttk.Frame(self.window,padding=8);controls.pack(fill='x')
        ttk.Label(controls,text='移行元の情報は変更しません。' if detail and detail.source else '').pack(side='left')
        ttk.Button(controls,text='キャンセル',command=self.cancel).pack(side='right')
        ttk.Button(controls,text='保存',command=self.save).pack(side='right',padx=8)
        self.window.bind('<Escape>',lambda event:self.cancel())
        self.window.deiconify();self.window.grab_set()

    def scroll_tab(self,notebook,title):
        outer=ttk.Frame(notebook);notebook.add(outer,text=title)
        canvas=tk.Canvas(outer,highlightthickness=0)
        scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        inner=ttk.Frame(canvas);item=canvas.create_window((0,0),window=inner,anchor='nw')
        inner.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width))
        return inner

    def note_modified(self,event=None):
        if self.note.edit_modified():
            self.note_changed=True
            self.note.edit_modified(False)

    def add_phone(self,values=None):
        if values is None:
            positions=[]
            for row in self.phone_rows:
                if row['kind'].get() == PHONE_LABELS['work_phone']:
                    try:positions.append(int(row['position'].get()))
                    except ValueError:pass
            values=dict(kind='work_phone',position=max(positions,default=0)+1,value='')
        frame=ttk.Frame(self.phone_frame,padding=8);frame.pack(fill='x')
        row={key:tk.StringVar(value=str(value)) for key,value in values.items()}
        row['kind']=tk.StringVar(value=PHONE_LABELS.get(values['kind'],values['kind']))
        ttk.Label(frame,text='種類').grid(row=0,column=0,sticky='w')
        ttk.Combobox(frame,textvariable=row['kind'],values=list(PHONE_LABELS.values()),state='readonly',width=18).grid(row=0,column=1,padx=4)
        ttk.Label(frame,text='順序').grid(row=0,column=2)
        ttk.Spinbox(frame,from_=1,to=999,textvariable=row['position'],width=5).grid(row=0,column=3,padx=4)
        ttk.Label(frame,text='番号').grid(row=1,column=0,sticky='w',pady=5)
        ttk.Entry(frame,textvariable=row['value'],width=45).grid(row=1,column=1,columnspan=3,sticky='ew',pady=5)
        ttk.Button(frame,text='削除',command=lambda:self.remove_row(frame,row,self.phone_rows)).grid(row=0,column=4,padx=8)
        self.phone_rows.append(row)

    def add_email(self,values=None):
        if values is None:
            positions=[]
            for row in self.email_rows:
                try:positions.append(int(row['position'].get()))
                except ValueError:pass
            values=dict(position=max(positions,default=0)+1,address='',display_name='',source_type='')
        frame=ttk.LabelFrame(self.email_frame,text='メール',padding=8);frame.pack(fill='x',padx=8,pady=6)
        row={key:tk.StringVar(value=str(value)) for key,value in values.items()}
        ttk.Label(frame,text='順序').grid(row=0,column=0,sticky='w')
        ttk.Spinbox(frame,from_=1,to=999,textvariable=row['position'],width=5).grid(row=0,column=1,sticky='w',padx=8)
        for index,(key,label) in enumerate((('address','アドレス'),('display_name','表示名'),('source_type','種類（例：SMTP）')),1):
            ttk.Label(frame,text=label).grid(row=index,column=0,sticky='w',pady=3)
            ttk.Entry(frame,textvariable=row[key],width=50).grid(row=index,column=1,sticky='ew',padx=8,pady=3)
        ttk.Button(frame,text='削除',command=lambda:self.remove_row(frame,row,self.email_rows)).grid(row=0,column=2)
        frame.columnconfigure(1,weight=1);self.email_rows.append(row)

    @staticmethod
    def remove_row(frame,row,rows):
        rows.remove(row);frame.destroy()

    def collect(self):
        fields={key:variable.get() for key,variable in self.fields.items()}
        # Tk Text can normalize line endings; keep untouched imported notes byte-for-byte as strings.
        fields['note']=self.note.get('1.0','end-1c') if self.note_changed else self.original_note
        phones=[];emails=[]
        kinds={label:kind for kind,label in PHONE_LABELS.items()}
        try:
            for row in self.phone_rows:
                phone={key:value.get() for key,value in row.items()}
                if not phone['value'].strip():continue
                phone['position']=int(phone['position']);phone['kind']=kinds.get(phone['kind'],phone['kind'])
                phones.append(phone)
            for row in self.email_rows:
                email={key:value.get() for key,value in row.items()}
                if not any(email[k].strip() for k in ('address','display_name','source_type')):continue
                email['position']=int(email['position']);emails.append(email)
        except ValueError:
            raise ContactValidationError('順序は1以上の整数で入力してください。') from None
        addresses=tuple(dict(kind=kind,**{key:variable.get() for key,variable in row.items()}) for kind,row in self.address_rows)
        return ContactInput(fields,tuple(phones),tuple(emails),addresses)

    def save(self):
        try:
            draft=self.collect();validate_contact(draft)
            if self.save_callback is not None and not self.save_callback(draft):return
        except ContactValidationError as exc:
            messagebox.showerror('入力の確認',str(exc),parent=self.window);return
        self.result=draft;self.window.destroy()

    def cancel(self):
        self.result=None;self.window.destroy()

    def show(self):
        self.window.wait_window()
        return self.result
