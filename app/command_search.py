"""Search only configured references, notes and settings. No disk index or service."""
import copy
import os
from PyQt5.QtCore import Qt,QTimer,QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,QListWidgetItem,QComboBox
from dock_folders import application_entries
from reference_repair import reference_key


def search_identity(row):
    path=row.get("path", "")
    # Pure lexical identity: typing must never resolve network files or COM links.
    target=path if "://" in path or path.casefold().startswith("shell:") else reference_key(path)
    return (target, row.get("arguments", ""), row.get("working_directory", ""), row.get("app_user_model_id", ""), row.get("verb", ""))
from ui_style import SettingsHeader,compact_dialog,button,label,ModernComboBox


def matches(cfg,notes,settings,query,scope='all',limit=100):
    query=query.strip().casefold();words=query.split();found=[];seen=set()
    def add(kind,name,detail,payload,haystack=''):
        text=(str(name)+' '+str(detail)+' '+haystack).casefold()
        if scope not in ('all',kind) or not all(word in text for word in words):return
        rank=0 if query and str(name).casefold()==query else 1 if query and str(name).casefold().startswith(query) else 2
        found.append((rank,{'kind':kind,'name':str(name),'detail':str(detail),'payload':payload}))
    if scope in ('all','apps'):
        for row in application_entries(cfg.get('items',[])):
            key=("apps",search_identity(row))
            if key in seen:continue
            seen.add(key);add('apps',row.get('name') or os.path.basename(row['path']),row['path']+(' '+row['arguments'] if row.get('arguments') else ''),copy.deepcopy(row))
    if scope in ('all','files'):
        for row in cfg.get('desktop_entries',[]):
            key=('files',reference_key(row['path']))
            if key in seen:continue
            seen.add(key);add('files',row.get('name') or os.path.basename(row['path']),row['path'],row['path'])
    if scope in ('all','notes'):
        for row in notes:add('notes',row['title'],row.get('text','').replace('\n',' ')[:100],row['id'],row.get('text',''))
    if scope in ('all','flash'):
        for row in cfg.get('flash_entries',[]):
            if not row['deleted']:
                add('flash',row['text'].splitlines()[0][:75],'已完成' if row['done'] else '未完成',row['id'],row['text'])
    if scope in ('all','settings'):
        for row in settings:add('settings',row['title'],row['page'],row['key'],row.get('options','')+' '+row['key'])
    found.sort(key=lambda row:(row[0],row[1]['kind'],row[1]['name'].casefold()))
    return [row for _,row in found[:limit]],len(found)


class SearchDialog(QDialog):
    def __init__(self,runtime,parent=None,settings_only=False):
        super().__init__(parent,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.runtime=runtime;self.setWindowTitle('搜索 · 大肥鱼Dock');self.resize(720,530)
        self.setAttribute(Qt.WA_DeleteOnClose);self.results=[]
        body=QVBoxLayout(self);body.setContentsMargins(18,12,18,14);body.setSpacing(12)
        body.addWidget(SettingsHeader(self,'搜索已收纳内容'))
        controls=QHBoxLayout();self.query=QLineEdit();self.query.setPlaceholderText('搜索应用、文件、便签、闪念和设置');self.query.setClearButtonEnabled(True)
        controls.addWidget(self.query,1);self.scope=ModernComboBox()
        for name,key in [('全部','all'),('应用','apps'),('文件','files'),('便签','notes'),('闪念','flash'),('设置','settings')]:self.scope.addItem(name,key)
        if settings_only:self.scope.setCurrentIndex(self.scope.findData('settings'))
        controls.addWidget(self.scope);body.addLayout(controls)
        self.list=QListWidget();self.list.setIconSize(QSize(28,28));body.addWidget(self.list,1)
        footer=QHBoxLayout();self.status=label('仅搜索本应用已收纳的内容，不扫描磁盘。','muted');footer.addWidget(self.status,1)
        footer.addWidget(button('关闭',self.close));footer.addWidget(button('打开',self.activate,'primary'));body.addLayout(footer)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(120);self.timer.timeout.connect(self.refresh)
        self.query.textChanged.connect(lambda:self.timer.start());self.scope.currentIndexChanged.connect(lambda:self.timer.start())
        self.query.returnPressed.connect(self.activate);self.list.itemActivated.connect(lambda _:self.activate())
        self.query.installEventFilter(self)
        compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,runtime.dock.cfg)
        self.query.setFocus()

    def settings_window(self):
        tray=self.runtime.tray
        if not hasattr(tray,'settings_dialog'):
            from settings_dialog import SettingsDialog
            tray.settings_dialog=SettingsDialog(tray,self.runtime.api)
        return tray.settings_dialog

    def refresh(self):
        scope=self.scope.currentData()
        targets=self.settings_window().search_targets() if scope in ('all','settings') else []
        self.results,total=matches(self.runtime.dock.cfg,self.runtime.notes.rows(),targets,self.query.text(),self.scope.currentData())
        self.list.clear()
        names={'apps':'应用','files':'文件','notes':'便签','flash':'闪念','settings':'设置'}
        for result in self.results:
            item=QListWidgetItem(result['name']+'    · '+names[result['kind']]+'\n'+result['detail'])
            item.setToolTip(result['detail']);item.setSizeHint(QSize(0,56));self.list.addItem(item)
        if self.results:self.list.setCurrentRow(0)
        self.status.setText(('找到 %d 项'%total)+('，显示前 100 项，请缩小范围。' if total>100 else ' · Enter 打开，Esc 关闭'))

    def eventFilter(self,obj,event):
        from PyQt5.QtCore import QEvent
        if obj is self.query and event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Up,Qt.Key_Down):
            if self.list.count():self.list.setCurrentRow(max(0,min(self.list.count()-1,self.list.currentRow()+(1 if event.key()==Qt.Key_Down else -1))))
            return True
        return super().eventFilter(obj,event)

    def activate(self):
        if self.timer.isActive():self.timer.stop();self.refresh()
        index=self.list.currentRow()
        if index<0 or index>=len(self.results):return
        row=self.results[index];runtime=self.runtime
        if row['kind']=='settings':
            runtime.show_settings();runtime.tray.settings_dialog.focus_setting(row['payload'])
        elif row['kind']=='flash':
            target=runtime.flash.item(row['payload'])
            if not target or target['deleted']:
                self.refresh();self.status.setText('该闪念已移入回收站。');return
            runtime.flash.open(identity=row['payload'])
        elif row['kind']=='notes':
            if not any(note['id']==row['payload'] for note in runtime.notes.rows()):
                self.refresh();self.status.setText('该便签已删除，请重新选择。');return
            runtime.notes.open(row['payload'])
        else:runtime.dock.launch(row['payload'],source='dock_launch' if row['kind']=='apps' else 'file_open')
        self.close()

    def closeEvent(self,event):
        self.timer.stop();self.results.clear();super().closeEvent(event)
