"""Minimal Tkinter UI for encrypted files, CSV import, and browsing."""
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from collections import Counter
from pathlib import Path

from contactdock.database import create_database, open_database
from contactdock.importer import DuplicateImportError, save_csv_preview
from contactdock.outlook_csv import CsvValidationError, read_outlook_csv
from contactdock.repository import get_contact, search_contacts
from contactdock.service import save_contact, delete_contact, ContactValidationError, ContactConflictError

PHONE_LABELS = {
    'work_phone':'会社電話', 'company_main_phone':'会社代表電話', 'work_fax':'会社FAX',
    'home_phone':'自宅電話', 'mobile_phone':'携帯電話', 'other_phone':'その他電話',
    'other_fax':'その他FAX', 'radio_phone':'無線電話', 'telex':'テレックス',
}
ADDRESS_LABELS = {'work':'会社','home':'自宅','other':'その他'}
FIELD_LABELS = {
    'family_name':'姓','given_name':'名','family_name_kana':'姓フリガナ','given_name_kana':'名フリガナ',
    'company_name':'会社名','company_name_kana':'会社名フリガナ','department':'部署','job_title':'役職',
    'web_page':'Webページ','birthday':'誕生日',
}


def format_detail(detail):
    """Preserve values and embedded note line breaks for display."""
    lines = [f'{label}：{detail.fields[key]}' for key,label in FIELD_LABELS.items()]
    lines += ['','【電話・FAX等】']
    for p in detail.phones:
        lines.append(f"{PHONE_LABELS.get(p['kind'],p['kind'])} {p['position']}：{p['value']}")
    lines += ['','【メール】']
    for e in detail.emails:
        lines += [f"メール {e['position']}：{e['address']}",
                  f"表示名：{e['display_name']}",f"種類：{e['source_type']}"]
    lines += ['','【住所】']
    for a in detail.addresses:
        lines.append(f"■ {ADDRESS_LABELS.get(a['kind'],a['kind'])}")
        for key,label in (('country_region','国／地域'),('postal_code','郵便番号'),
                          ('prefecture','都道府県'),('city','市町村'),('street','番地'),('post_office_box','私書箱')):
            lines.append(f'{label}：{a[key]}')
    lines += ['','【メモ】',detail.fields['note']]
    return '\n'.join(lines)


def format_source(detail):
    if detail.source is None:
        return 'この連絡先には移行元情報がありません。'
    source = detail.source
    lines = [f'元ファイル：{source.filename}',f'文字コード：{source.encoding}',
             f'取込日時（UTC）：{source.imported_at}',f'元レコード番号：{source.record_number}',
             '', '【Outlookの項目名と移行時の元値】']
    lines.extend(f'{name}：{value}' for name,value in source.fields)
    return '\n'.join(lines)


def import_confirmation(preview):
    lines = [f'連絡先 {len(preview.contacts):,}件を追加します。',
             '既存連絡先は更新しません。変更したCSVの場合、連絡先が重複する可能性があります。']
    if preview.warnings:
        lines += ['',f'確認事項：{len(preview.warnings):,}件（元値は保持します）']
        counts = Counter(w.column for w in preview.warnings)
        lines.extend(f'・{column}：{count:,}件' for column,count in counts.items())
    lines += ['','取り込みますか？']
    return '\n'.join(lines)


class ContactDockApplication:
    def __init__(self, root):
        self.root = root
        self.connection = None
        self.db_path = None
        root.title('ContactDock')
        root.geometry('1280x780')
        root.minsize(900,560)
        root.protocol('WM_DELETE_WINDOW',self.close)
        toolbar = ttk.Frame(root,padding=8);toolbar.pack(fill='x')
        ttk.Button(toolbar,text='DB新規作成',command=lambda:self.choose_database(True)).pack(side='left')
        ttk.Button(toolbar,text='DBを開く',command=lambda:self.choose_database(False)).pack(side='left',padx=6)
        self.import_button = ttk.Button(toolbar,text='CSV取込',command=self.import_csv,state='disabled')
        self.import_button.pack(side='left')
        self.new_button=ttk.Button(toolbar,text='新規登録',command=lambda:self.edit_contact(False),state='disabled')
        self.new_button.pack(side='left',padx=6)
        self.edit_button=ttk.Button(toolbar,text='編集',command=lambda:self.edit_contact(True),state='disabled')
        self.edit_button.pack(side='left')
        self.delete_button=ttk.Button(toolbar,text='削除',command=self.delete_selected_contact,state='disabled')
        self.delete_button.pack(side='left',padx=6)
        self.file_label = ttk.Label(toolbar,text='DB未選択');self.file_label.pack(side='left',padx=12)
        searchbar = ttk.Frame(root,padding=(8,0,8,8));searchbar.pack(fill='x')
        ttk.Label(searchbar,text='検索（メモを含む）').pack(side='left')
        self.query = tk.StringVar()
        self.entry = ttk.Entry(searchbar,textvariable=self.query,state='disabled')
        self.entry.pack(side='left',fill='x',expand=True,padx=8)
        self.entry.bind('<Return>',lambda event:self.refresh())
        self.search_button=ttk.Button(searchbar,text='検索',command=self.refresh,state='disabled')
        self.search_button.pack(side='left')
        self.clear_button=ttk.Button(searchbar,text='クリア',command=self.clear_search,state='disabled')
        self.clear_button.pack(side='left',padx=6)
        panes = ttk.Panedwindow(root,orient='horizontal');panes.pack(fill='both',expand=True,padx=8)
        left=ttk.Frame(panes);right=ttk.Frame(panes)
        panes.add(left,weight=3);panes.add(right,weight=2)
        columns=('name','company','department','title','work','mobile','email')
        self.tree=ttk.Treeview(left,columns=columns,show='headings',selectmode='browse')
        for key,label,width in zip(columns,('氏名','会社名','部署','役職','会社電話','携帯電話','第1メール'),(160,200,130,100,130,130,220)):
            self.tree.heading(key,text=label);self.tree.column(key,width=width,minwidth=70,stretch=False)
        vertical=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview)
        horizontal=ttk.Scrollbar(left,orient='horizontal',command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns')
        horizontal.grid(row=1,column=0,sticky='ew')
        left.rowconfigure(0,weight=1);left.columnconfigure(0,weight=1)
        self.tree.bind('<<TreeviewSelect>>',self.select_contact)
        notebook=ttk.Notebook(right);notebook.pack(fill='both',expand=True)
        self.detail_text=self.text_tab(notebook,'詳細')
        self.source_text=self.text_tab(notebook,'移行元')
        self.status=ttk.Label(root,text='DBを新規作成、または既存DBを開いてください。',padding=8)
        self.status.pack(fill='x')

    def text_tab(self, notebook, label):
        frame=ttk.Frame(notebook);notebook.add(frame,text=label)
        text=tk.Text(frame,wrap='word',state='disabled',width=45)
        scroll=ttk.Scrollbar(frame,command=text.yview);text.configure(yscrollcommand=scroll.set)
        text.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        return text

    @staticmethod
    def put_text(widget,value):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',value);widget.configure(state='disabled')

    def clear_detail(self):
        self.put_text(self.detail_text,'');self.put_text(self.source_text,'')
        self.edit_button.configure(state='disabled')
        self.delete_button.configure(state='disabled')

    def choose_database(self, create):
        options=dict(parent=self.root,filetypes=[('ContactDock DB','*.db'),('すべて','*.*')])
        path=(filedialog.asksaveasfilename(defaultextension='.db',**options) if create else filedialog.askopenfilename(**options))
        if not path:return
        password=simpledialog.askstring('パスワード','DBのパスワードを入力してください。',show='*',parent=self.root)
        if password is None:return
        if create:
            repeated=simpledialog.askstring('パスワード確認','同じパスワードをもう一度入力してください。',show='*',parent=self.root)
            if repeated is None:return
            if repeated!=password:
                messagebox.showerror('確認','パスワードが一致しません。',parent=self.root);return
            del repeated
        try:
            connection=create_database(path,password) if create else open_database(path,password)
        except FileExistsError:
            messagebox.showerror('DB作成','既存ファイルへは上書きしません。別のファイル名を指定してください。',parent=self.root);return
        except Exception:
            messagebox.showerror('DBを開けません','パスワード、ファイルの状態、保存先のアクセス権を確認してください。',parent=self.root);return
        finally:
            del password
        if self.connection is not None:self.connection.close()
        self.connection=connection;self.db_path=Path(path)
        self.root.title(f'ContactDock — {self.db_path.name}')
        self.file_label.configure(text=self.db_path.name)
        for widget in (self.entry,self.import_button,self.search_button,self.clear_button,self.new_button):widget.configure(state='normal')
        self.query.set('');self.refresh()

    def refresh(self):
        if self.connection is None:return
        try:rows=search_contacts(self.connection,self.query.get())
        except Exception:
            self.status.configure(text='検索に失敗しました。')
            messagebox.showerror('検索','DBの読み取りに失敗しました。',parent=self.root);return
        self.tree.delete(*self.tree.get_children());self.clear_detail()
        for row in rows:
            self.tree.insert('', 'end',iid=str(row.id),values=(row.display_name,row.company_name,row.department,
                row.job_title,row.work_phone,row.mobile_phone,row.primary_email))
        self.status.configure(text=f'{len(rows):,}件' if rows else '該当する連絡先はありません。')

    def clear_search(self):
        self.query.set('');self.refresh()

    def select_contact(self,event=None):
        selected=self.tree.selection()
        if self.connection is None or not selected:self.clear_detail();return
        try:detail=get_contact(self.connection,int(selected[0]))
        except Exception:
            self.clear_detail();messagebox.showerror('詳細','連絡先または移行元情報を読み取れません。',parent=self.root);return
        if detail is None:self.clear_detail();return
        self.put_text(self.detail_text,format_detail(detail));self.put_text(self.source_text,format_source(detail))
        self.edit_button.configure(state='normal')
        self.delete_button.configure(state='normal')

    def import_csv(self):
        if self.connection is None:return
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('Outlook CSV','*.csv'),('すべて','*.*')])
        if not path:return
        try:
            preview=read_outlook_csv(path)
            if self.connection.execute('SELECT id FROM import_batches WHERE source_sha256=?',(preview.source_sha256,)).fetchone():
                messagebox.showinfo('CSV取込','同じCSVは取込済みです。',parent=self.root);return
            if not messagebox.askyesno('CSV取込の確認',import_confirmation(preview),parent=self.root):return
            result=save_csv_preview(self.connection,preview)
        except CsvValidationError as exc:
            messagebox.showerror('CSVの確認',str(exc),parent=self.root);return
        except DuplicateImportError:
            messagebox.showinfo('CSV取込','同じCSVは取込済みです。',parent=self.root);return
        except Exception:
            messagebox.showerror('CSV取込','取込に失敗しました。入力ファイルやDBの状態を確認してください。',parent=self.root);return
        self.query.set('');self.refresh()
        messagebox.showinfo('CSV取込',f'{result.contact_count:,}件を取り込みました。',parent=self.root)

    def edit_contact(self, editing):
        if self.connection is None:return
        from contactdock.editor import ContactEditor
        detail=None
        if editing:
            selected=self.tree.selection()
            if not selected:return
            try:detail=get_contact(self.connection,int(selected[0]))
            except Exception:
                messagebox.showerror('編集','連絡先を読み取れません。',parent=self.root);return
            if detail is None:self.refresh();return
        saved_id=None

        def persist(draft):
            nonlocal saved_id
            try:
                saved_id=save_contact(self.connection,draft,
                    detail.id if detail else None,detail.updated_at if detail else None)
                return True
            except (ContactValidationError,ContactConflictError) as exc:
                messagebox.showerror('保存の確認',str(exc),parent=editor.window)
            except Exception:
                messagebox.showerror('保存','保存に失敗しました。入力内容はこの画面に残しています。',parent=editor.window)
            return False

        editor=ContactEditor(self.root,detail,save_callback=persist)
        editor.show()
        if saved_id is not None:
            self.query.set('');self.refresh()
            identifier=str(saved_id)
            if self.tree.exists(identifier):
                self.tree.selection_set(identifier);self.tree.focus(identifier);self.tree.see(identifier)
                self.select_contact()

    def delete_selected_contact(self):
        if self.connection is None:return
        selected=self.tree.selection()
        if not selected:return
        try:
            detail=get_contact(self.connection,int(selected[0]))
            if detail is None:self.refresh();return
            name=detail.display_name or '（氏名未設定）'
            company=detail.fields['company_name'] or '（会社名未設定）'
            text=(f'氏名：{name}\n会社名：{company}\n連絡先ID：{detail.id}\n\n'
                  'この連絡先を一覧・検索から除外します。\n'
                  'データは内部に保持します。復元画面はまだありません。\n\n削除しますか？')
            if not messagebox.askyesno('連絡先の削除',text,parent=self.root):return
            delete_contact(self.connection,detail.id,detail.updated_at)
        except (ContactValidationError,ContactConflictError) as exc:
            messagebox.showerror('削除の確認',str(exc),parent=self.root);self.refresh();return
        except Exception:
            messagebox.showerror('削除','削除に失敗しました。DBの状態を確認してください。',parent=self.root);return
        self.refresh()

    def close(self):
        if self.connection is not None:self.connection.close();self.connection=None
        self.root.destroy()


def main():
    root=tk.Tk()
    ContactDockApplication(root)
    root.mainloop()
