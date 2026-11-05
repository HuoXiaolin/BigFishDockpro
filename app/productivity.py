"""Small on-demand tools for arranging and finding existing desktop content."""
import copy
from PyQt5.QtCore import QObject
from arrangement_history import ArrangementHistory
HISTORY_KEYS={'items','desktop_entries','desktop_excluded','desktop_panels','merge_groups','disabled_categories','merged_panels','merged_active','merged_geometry','merged_collapsed','merged_compact','display_layout','merge_initialized'}

class Productivity(QObject):
    def __init__(self,runtime):
        super().__init__(runtime.dock)
        self.runtime=runtime;self.dialogs={};self.message='';self.closed=False
        self.history=ArrangementHistory(runtime.dock.cfg,runtime.api.save_config,self.apply)

    def apply(self,previous,refresh=True):
        runtime=self.runtime
        from settings_effects import apply_changes,sync_main_fields
        changed=apply_changes(runtime.tray,runtime.api,previous)
        runtime.apply_visibility()
        if refresh and changed&{'display_layout','desktop_panels','merge_groups','merged_geometry','clock_layout','calendar_layout','sticky_notes','position','custom_bottom','bottom_margin','icon_size','merged_collapsed','merged_active','merged_panels'}:
            runtime.layout.apply()
            runtime.panels.restore_layout_state()
        sync_main_fields(runtime.tray,{k:runtime.dock.cfg[k] for k in changed if k in runtime.dock.cfg})
        if hasattr(runtime.tray,'rebuild'):runtime.tray.rebuild()

    def commit(self,candidate,title,history=True,refresh=True):
        runtime=self.runtime;cfg=runtime.dock.cfg
        changes={k:copy.deepcopy(v) for k,v in candidate.items() if cfg.get(k)!=v}
        if not changes:self.message='内容没有变化';return True
        if runtime.layout.pending:self.message='显示器正在切换，请稍后重试。';return False
        if not runtime.notes.flush():self.message='便签尚未保存，请先重试保存。';return False
        previous=copy.deepcopy(cfg);candidate=dict(cfg,**changes)
        if runtime.api.save_config(candidate) is False:self.message='保存失败，改动未应用。';return False
        cfg.update(changes)
        try:self.apply(previous,refresh)
        except Exception as error:
            cfg.clear();cfg.update(previous)
            saved=runtime.api.save_config(previous)
            try:self.apply(candidate,refresh)
            except Exception as rollback:runtime.api.log('整理恢复界面失败：'+str(rollback))
            runtime.api.log('整理应用失败：'+str(error))
            self.message='应用失败，已恢复原配置。' if saved else '应用失败且配置恢复失败，请检查数据目录。'
            return False
        if history:
            keys=set(changes)&HISTORY_KEYS
            self.history.record({k:previous.get(k) for k in keys},{k:cfg.get(k) for k in keys},title)
        self.message=title+'已保存';return True

    def undo(self):
        if self.runtime.layout.pending:self.message='显示器正在切换，请稍后撤销。';return False
        result=self.history.undo();self.message=self.history.message
        self.runtime.tray.showMessage('整理撤销',self.message,self.runtime.tray.icon(),2500)
        return result

    def show(self,key):
        if self.closed:return None
        from PyQt5 import sip
        dialog=self.dialogs.get(key)
        if dialog is None or sip.isdeleted(dialog):
            if key=='search':
                from command_search import SearchDialog
                dialog=SearchDialog(self.runtime)
            elif key=='layouts':
                from layout_dialog import LayoutDialog
                dialog=LayoutDialog(self.runtime)
            else:
                from reference_dialog import ReferencesDialog
                dialog=ReferencesDialog(self.runtime)
            self.dialogs[key]=dialog
            dialog.destroyed.connect(lambda _,name=key,owned=dialog:self.dialogs.pop(name,None) if self.dialogs.get(name) is owned else None)
        dialog.show();dialog.raise_();dialog.activateWindow()
        if hasattr(dialog,'refresh'):dialog.refresh()
        return dialog

    def open_layouts(self):return self.show('layouts')
    def open_references(self):return self.show('references')
    def open_search(self):return self.show('search')

    def close(self):
        self.closed=True
        for dialog in list(self.dialogs.values()):dialog.close()
        self.dialogs.clear();self.history.close()
