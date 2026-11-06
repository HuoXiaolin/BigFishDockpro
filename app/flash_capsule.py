"""Lifecycle and atomic updates for the independent edge-mounted flash inbox."""
import time
from PyQt5.QtCore import QObject, QTimer, Qt
from PyQt5.QtWidgets import QApplication
from flash_data import new_entry, normalize_entries, normalize_draft


class FlashCapsule(QObject):
    def __init__(self,runtime):
        super().__init__(runtime.dock)
        self.runtime=runtime
        self.edge=self.panel=self.toast=None
        self.closed=False
        self.reminder=None

    @property
    def cfg(self):
        return self.runtime.dock.cfg

    def persist(self,**changes):
        if all(self.cfg.get(k)==v for k,v in changes.items()): return True
        if self.runtime.api.save_config(dict(self.cfg,**changes)) is False:
            self.message('保存失败，请检查数据目录后重试。')
            return False
        self.cfg.update(changes)
        return True

    def message(self,text):
        if self.panel is not None:
            self.panel.message(text)
        elif self.edge is not None:
            self.edge.feedback(text)

    def commit_rows(self,rows,clear_draft=False):
        try:
            rows=normalize_entries(rows,strict=True)
        except ValueError as error:
            self.message(str(error));return False
        changes={'flash_entries':rows}
        if clear_draft: changes['flash_draft']={}
        if not self.persist(**changes): return False
        if clear_draft and self.panel is not None: self.panel.finish_edit()
        self.refresh()
        self.schedule()
        return True

    def refresh(self):
        if self.edge is not None: self.edge.update_count()
        if self.panel is not None: self.panel.render()

    def item(self,identity):
        return next((row for row in self.cfg['flash_entries'] if row['id']==identity),None)

    def add(self,text,color=None,clear_draft=False):
        try:
            row=new_entry(text,color or self.cfg['flash_color'])
        except ValueError as error:
            self.message(str(error));return None
        rows=[row, *self.cfg['flash_entries']]
        if not self.commit_rows(rows,clear_draft): return None
        self.message('已记下闪念')
        return row['id']

    def modify(self,identity,clear_draft=False,**fields):
        if not self.item(identity): return False
        rows=[dict(row,**fields) if row['id']==identity else row for row in self.cfg['flash_entries']]
        return self.commit_rows(rows,clear_draft)

    def empty_trash(self):
        rows=[row for row in self.cfg['flash_entries'] if not row['deleted']]
        return self.commit_rows(rows)

    def save_draft(self):
        if self.panel is None or not self.panel.editing: return True
        try:
            draft=normalize_draft(self.panel.draft(),strict=True)
        except ValueError as error:
            self.message(str(error));return False
        return self.persist(flash_draft=draft)

    def set_enabled(self,enabled):
        from settings_effects import save_changes
        if not enabled and not self.save_draft(): return False
        return save_changes(self.runtime.tray,self.runtime.api,{'flash_enabled':bool(enabled)})

    def open(self,compose=False,identity=None,activate=True):
        if self.closed or self.runtime.game_active: return
        if not self.cfg['flash_enabled'] and not self.set_enabled(True): return
        if self.panel is None:
            from flash_panel import FlashPanel
            self.panel=FlashPanel(self)
        self.reposition()
        self.panel.show()
        if activate:
            self.panel.raise_()
            self.panel.activateWindow()
        if identity: self.panel.reveal_item(identity)
        elif compose: self.panel.begin_edit()
        elif activate: self.panel.list.setFocus(Qt.OtherFocusReason)

    def collapse(self,force=False):
        if self.panel is None: return True
        if not force and not self.save_draft(): return False
        panel,self.panel=self.panel,None
        panel.dismiss()
        return True

    def reposition(self):
        if self.edge is not None:
            self.edge.place()
        if self.panel is not None and self.edge is not None:
            self.panel.place(self.edge)

    def sync(self,reload=False):
        if self.closed: return
        visible=self.cfg['flash_enabled'] and not self.runtime.game_active
        if visible:
            if self.edge is None:
                from flash_panel import EdgeHandle
                self.edge=EdgeHandle(self)
            self.edge.update_count()
            self.reposition()
            self.edge.show()
            if self.panel is None and not self.cfg['flash_auto_hide']:self.open(activate=False)
            if self.panel is not None:
                if reload: self.panel.load_saved_draft()
                self.panel.apply_style()
                self.panel.render()
        else:
            if self.panel is not None:
                if reload: self.panel.load_saved_draft()
                if not self.collapse(): self.panel.hide()
            if self.edge is not None:
                self.edge.dismiss();self.edge=None
            if self.toast is not None:
                self.toast.close();self.toast=None
        self.schedule()

    def schedule(self):
        deadlines=[]
        if not self.closed and self.cfg['flash_enabled'] and not self.runtime.game_active:
            deadlines=[r['due'] for r in self.cfg['flash_entries'] if r['due'] and
                       not (r['done'] or r['deleted'] or r['notified'])]
        if not deadlines:
            if self.reminder:
                self.reminder.stop();self.reminder.deleteLater();self.reminder=None
            return
        if self.reminder is None:
            self.reminder=QTimer(self);self.reminder.setSingleShot(True);self.reminder.timeout.connect(self.deliver_due)
        self.reminder.start(min(2147000000,max(1,round((min(deadlines)-time.time())*1000))))

    def deliver_due(self):
        if self.closed or not self.cfg['flash_enabled'] or self.runtime.game_active: return
        now=int(time.time())
        due=[r for r in self.cfg['flash_entries'] if 0<r['due']<=now and not (r['done'] or r['deleted'] or r['notified'])]
        if due:
            ids={r['id'] for r in due}
            rows=[dict(r,notified=True) if r['id'] in ids else r for r in self.cfg['flash_entries']]
            if not self.persist(flash_entries=rows):
                self.reminder.start(60000);return
            if self.toast is not None: self.toast.close()
            from flash_panel import ReminderToast
            self.toast=ReminderToast(self,min(due,key=lambda r:r['due']),len(due))
            self.toast.show()
            self.refresh()
        self.schedule()

    def close(self):
        self.closed=True
        self.schedule()
        self.collapse(force=True)
        if self.edge is not None: self.edge.dismiss();self.edge=None
        if self.toast is not None: self.toast.close();self.toast=None
