"""Named desktop layouts using the application's common settings surface."""
from PyQt5.QtCore import Qt,QSize
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,QListWidgetItem,QMessageBox
from ui_style import SettingsHeader,SettingsGrip,compact_dialog,label,button
from layout_profiles import create,apply,normalize_profiles


class LayoutDialog(QDialog):
    def __init__(self,runtime,parent=None):
        super().__init__(parent,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.runtime=runtime;self.setProperty('compactDialog',True)
        self.setWindowTitle('布局方案 · 大肥鱼Dock');self.resize(620,440);self.setMinimumSize(490,350)
        body=QVBoxLayout(self);body.setContentsMargins(18,12,18,12);body.setSpacing(10)
        body.addWidget(SettingsHeader(self,'布局方案'))
        body.addWidget(label('保存组件的位置、尺寸、显隐与卡片分组，快速切换桌面布局。','muted'))
        row=QHBoxLayout();row.setSpacing(8);row.addWidget(label('方案名称'))
        self.name=QLineEdit();self.name.setMaxLength(40);self.name.setPlaceholderText('例如：日常工作、专注、演示')
        self.name.setAccessibleName('布局方案名称');row.addWidget(self.name,1)
        self.save_button=button('保存当前布局',self.save_current);row.addWidget(self.save_button);body.addLayout(row)
        self.list=QListWidget();self.list.setAccessibleName('已保存的布局方案');self.list.setSpacing(2)
        self.list.currentItemChanged.connect(self.select);body.addWidget(self.list,1)
        self.empty=label('尚无布局方案，输入名称后保存当前布局。','muted');body.addWidget(self.empty)
        body.addWidget(label('主题外观、便签内容和文件引用保持不变。','muted'))
        self.status=label('','muted');body.addWidget(self.status)
        footer=QHBoxLayout();footer.setSpacing(8)
        self.rename_button=button('重命名',self.rename_selected);self.delete_button=button('删除方案',self.delete_selected)
        footer.addWidget(self.rename_button);footer.addWidget(self.delete_button);footer.addStretch()
        footer.addWidget(button('关闭',self.reject));self.apply_button=button('应用布局',self.apply_selected,'primary');footer.addWidget(self.apply_button)
        self.grip=SettingsGrip(self);self.grip.setFixedSize(12,18);footer.addWidget(self.grip,0,Qt.AlignBottom);body.addLayout(footer)
        self.list.itemDoubleClicked.connect(lambda *_:self.apply_selected())
        self.name.returnPressed.connect(self.save_current)
        self.render();compact_dialog(self)
        from idle_resources import watch
        watch(self)

    @property
    def cfg(self):return self.runtime.dock.cfg

    def profiles(self):return normalize_profiles(self.cfg.get('layout_profiles',[]))

    def current(self):
        item=self.list.currentItem()
        return next((row for row in self.profiles() if item and row['id']==item.data(Qt.UserRole)),None)

    def render(self,identity=None):
        if identity is None:
            current=self.current();identity=current['id'] if current else None
        profiles=self.profiles();self.list.blockSignals(True);self.list.clear()
        for row in profiles:
            values=row['layout'].get('values',{})
            visible=[]
            for enabled,title in [(values.get('dock_visible'),'Dock'),
                                  (values.get('panel_enabled') and values.get('panels_visible'),'卡片'),
                                  (values.get('notes_enabled') and values.get('notes_visible'),'便签'),
                                  (values.get('clock_enabled'),'时钟'),(values.get('calendar_enabled'),'日历')]:
                if enabled:visible.append(title)
            detail=' · '.join(visible) if visible else '组件保持隐藏'
            item=QListWidgetItem(row['name']+'\n'+detail);item.setData(Qt.UserRole,row['id']);item.setToolTip(row['name'])
            item.setSizeHint(QSize(100,54));self.list.addItem(item)
            if row['id']==identity:self.list.setCurrentItem(item)
        self.list.blockSignals(False);self.empty.setVisible(not profiles)
        self.select(self.list.currentItem(),None)

    def refresh(self):self.render()

    def release_idle_resources(self):
        if self.isVisible():return False
        dialogs=getattr(self.runtime.productivity,'dialogs',{})
        if dialogs.get('layouts') is self:dialogs.pop('layouts')
        self.deleteLater();return True

    def select(self,current,previous=None):
        row=self.current();enabled=row is not None
        for control in (self.rename_button,self.delete_button,self.apply_button):control.setEnabled(enabled)
        if row:self.name.setText(row['name'])

    def ready(self):
        layout=self.runtime.layout
        if layout.pending or layout.applying:
            self.status.setText('屏幕布局正在适配，请稍后重试。');return False
        if not self.runtime.notes.flush():
            self.status.setText('便签尚未保存，请先重试保存，再切换布局。');return False
        return True

    def persist(self,candidate,title,refresh=False):
        try:ok=self.runtime.productivity.commit(candidate,title,history=False,refresh=refresh)
        except Exception as error:
            self.runtime.api.log('布局方案保存失败：'+str(error));ok=False
        if not ok:self.status.setText('保存失败，布局未更改，请检查数据目录后重试。')
        return bool(ok)

    def confirm(self,title,text,action):
        box=QMessageBox(QMessageBox.Question,title,text,parent=self)
        accept=box.addButton(action,QMessageBox.AcceptRole);cancel=box.addButton('取消',QMessageBox.RejectRole)
        box.setDefaultButton(cancel);box.setEscapeButton(cancel);box.exec_()
        accepted=box.clickedButton() is accept;box.deleteLater();return accepted

    def save_current(self):
        name=self.name.text().strip()
        if not name:self.status.setText('请填写方案名称。');self.name.setFocus();return False
        profiles=self.profiles();existing=next((row for row in profiles if row['name'].casefold()==name.casefold()),None)
        if existing and not self.confirm('更新布局方案','将当前布局保存到“'+existing['name']+'”？','更新布局'):return False
        if not existing and len(profiles)>=12:self.status.setText('最多保存 12 个方案，请先删除不再使用的方案。');return False
        if not self.ready():return False
        # These component methods preserve expanded anchors while a ball/capsule
        # is visible; the collapsed widget rectangle must never be the snapshot.
        self.runtime.panels.save_visible_geometry()
        for window in self.runtime.notes.windows.values():window.title.finish_edit();window.save_geometry()
        self.runtime.clock.save_geometry();self.runtime.calendar.save_geometry();self.runtime.layout.ensure_profiles()
        if not self.runtime.notes.flush():self.status.setText('便签保存失败，未保存布局。');return False
        profile=create(self.cfg,name)
        if existing:
            profile['id']=existing['id'];profiles=[profile if row['id']==existing['id'] else row for row in profiles]
        else:profiles.append(profile)
        if not self.persist(dict(self.cfg,layout_profiles=profiles),'保存布局方案'):return False
        self.render(profile['id']);self.status.setText('已保存：'+name);return True

    def apply_selected(self):
        profile=self.current()
        if profile is None or not self.ready():return False
        candidate=apply(self.cfg,profile)
        if not self.persist(candidate,'应用布局方案',refresh=True):return False
        self.render(profile['id']);self.status.setText('已应用：'+profile['name']);return True

    def rename_selected(self):
        profile=self.current();name=self.name.text().strip()
        if profile is None:return False
        if not name:self.status.setText('请填写新的方案名称。');self.name.setFocus();return False
        profiles=self.profiles()
        if any(row['id']!=profile['id'] and row['name'].casefold()==name.casefold() for row in profiles):
            self.status.setText('已有同名方案，请换一个名称。');return False
        for row in profiles:
            if row['id']==profile['id']:row['name']=name
        if not self.persist(dict(self.cfg,layout_profiles=profiles),'重命名布局方案'):return False
        self.render(profile['id']);self.status.setText('方案已重命名。');return True

    def delete_selected(self):
        profile=self.current()
        if profile is None or not self.confirm('删除布局方案','删除“'+profile['name']+'”？当前桌面布局不受影响。','删除方案'):return False
        profiles=[row for row in self.profiles() if row['id']!=profile['id']]
        if not self.persist(dict(self.cfg,layout_profiles=profiles),'删除布局方案'):return False
        self.name.clear();self.render();self.status.setText('方案已删除，当前布局保持不变。');return True
