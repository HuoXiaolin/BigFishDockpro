"""Panel group switches, merged navigation and non-exclusive file format rules."""
import copy
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QListWidget,QListWidgetItem
from ui_style import SettingsHeader,ModernCheckBox,label,button
from desktop_catalog import CATEGORIES,parse_extensions


class PanelDefinition(QDialog):
    def __init__(self, model=None, parent=None):
        super().__init__(parent,Qt.Dialog|Qt.FramelessWindowHint)
        self.setProperty('compactDialog',True)
        self.setWindowTitle('面板名称与格式')
        self.resize(480,320)
        self.setMinimumWidth(440)
        body=QVBoxLayout(self);body.setContentsMargins(18,14,18,16);body.setSpacing(12)
        body.addWidget(SettingsHeader(self,'编辑面板' if model else '新建面板'))
        form=QFormLayout();form.setVerticalSpacing(12)
        self.name=QLineEdit((model or {}).get('name',''))
        self.name.setMaxLength(40)
        self.formats=QLineEdit(' '.join((model or {}).get('extensions',[])))
        self.formats.setPlaceholderText('.pdf .docx .png，留空仅手动收纳')
        form.addRow('面板名称',self.name);form.addRow('自动归入格式',self.formats);body.addLayout(form)
        body.addWidget(label('格式规则作用于桌面内容，也识别快捷方式目标格式。同一文件可以同时出现在默认分组和多个自定义面板中，原文件保持原位。','muted'))
        self.status=label('','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('取消',self.reject));actions.addWidget(button('确定',self.validate,'primary'));body.addLayout(actions)

    def extensions(self): return parse_extensions(self.formats.text())

    def validate(self):
        if not self.name.text().strip(): self.status.setText('请填写面板名称。');return
        try:self.extensions()
        except ValueError as error:self.status.setText(str(error));return
        self.accept()


class GroupDialog(QDialog):
    def __init__(self,manager):
        super().__init__(None,Qt.Dialog|Qt.FramelessWindowHint)
        self.manager=manager
        self.merge_states={model['id']:model.get('merged',True) for model in manager.cfg['desktop_panels']}
        self.setWindowTitle('面板分组与合并管理');self.setProperty('compactDialog',True)
        self.resize(580,560);self.setMinimumSize(480,420)
        body=QVBoxLayout(self);body.setContentsMargins(18,14,18,16);body.setSpacing(10)
        body.addWidget(SettingsHeader(self,'分组与合并管理'))
        body.addWidget(label('勾选要显示的分组。关闭分组保留收纳引用和外观，再次开启即可恢复。','muted'))
        self.list=QListWidget();body.addWidget(self.list,1)
        sorting=QHBoxLayout()
        sorting.addWidget(button('上移',lambda:self.move_selected(-1)))
        sorting.addWidget(button('下移',lambda:self.move_selected(1)))
        sorting.addStretch()
        body.addLayout(sorting)
        self.member=ModernCheckBox('将所选分组加入合并卡片')
        body.addWidget(self.member)
        self.list.currentItemChanged.connect(self.select_member)
        self.member.toggled.connect(self.change_member)
        self.merged=ModernCheckBox('启用卡片合并（仅合并已选择的分组）')
        self.merged.setChecked(manager.cfg['merged_panels']);body.addWidget(self.merged)
        actions=QHBoxLayout();actions.addWidget(button('新建面板',self.create));actions.addWidget(button('编辑名称与格式',self.edit));body.addLayout(actions)
        self.status=label('选中分组后，可单独选择是否参与合并；不参与的卡片独立显示。格式规则允许重复匹配。','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('关闭',self.reject));actions.addWidget(button('保存分组',self.commit,'primary'));body.addLayout(actions)
        self.populate()
        self.list.setCurrentRow(0)

    def select_member(self, current, previous=None):
        self.member.blockSignals(True)
        self.member.setText('将“%s”加入合并卡片' % self.manager.model(current.data(Qt.UserRole))['name'] if current and current.data(Qt.UserRole) in {m['id'] for m in self.manager.cfg['desktop_panels']} else '将所选分组加入合并卡片')
        self.member.setEnabled(current is not None)
        self.member.setChecked(self.merge_states.get(current.data(Qt.UserRole),True) if current else False)
        self.member.blockSignals(False)

    def change_member(self, checked):
        item=self.list.currentItem()
        if item:self.merge_states[item.data(Qt.UserRole)]=checked

    def populate(self):
        states={self.list.item(i).data(Qt.UserRole):self.list.item(i).checkState() for i in range(self.list.count())}
        previous=list(states)
        selected=self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.list.clear()
        models={model['id']:model for model in self.manager.cfg['desktop_panels']}
        order=list(dict.fromkeys(previous+list(models)+[key for key,_ in CATEGORIES]))
        definitions=[(key,models.get(key,{'id':key,'name':dict(CATEGORIES).get(key,'收纳面板')})) for key in order]
        for key,model in definitions:
            formats=' '.join(model.get('extensions',[]))
            text=model['name']+(' · 默认分组' if key in dict(CATEGORIES) else (' · '+formats if formats else ' · 手动收纳'))
            item=QListWidgetItem(text);item.setData(Qt.UserRole,key)
            item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
            enabled=model.get('enabled',True) and key not in self.manager.cfg['disabled_categories']
            item.setCheckState(states.get(key,Qt.Checked if enabled else Qt.Unchecked));self.list.addItem(item)
            if key==selected:self.list.setCurrentItem(item)

    def move_selected(self, direction):
        row=self.list.currentRow()
        target=row+direction
        if row<0 or target<0 or target>=self.list.count():return
        item=self.list.takeItem(row);self.list.insertItem(target,item);self.list.setCurrentItem(item)
        self.status.setText('分组顺序已调整，保存后应用到卡片顶部栏目。')

    def create(self):
        if self.manager.new_panel():self.populate()

    def edit(self):
        item=self.list.currentItem()
        if not item:return
        key=item.data(Qt.UserRole)
        if key in dict(CATEGORIES):self.status.setText('默认分组使用内置分类；可通过勾选开启或关闭。自定义面板可编辑格式。');return
        model=self.manager.model(key);dialog=PanelDefinition(model,self)
        if dialog.exec_()==dialog.Accepted:
            self.manager.update_panel(key,name=dialog.name.text().strip()[:40],extensions=dialog.extensions())
            self.populate();self.manager.schedule_scan()

    def commit(self):
        self.manager.save_visible_geometry()
        enabled={self.list.item(i).data(Qt.UserRole):self.list.item(i).checkState()==Qt.Checked for i in range(self.list.count())}
        panels=copy.deepcopy(self.manager.cfg['desktop_panels']);known={model['id'] for model in panels}
        for key,name in CATEGORIES:
            if key not in known and enabled.get(key):panels.append({'id':key,'name':name})
        for model in panels:
            model['enabled']=enabled.get(model['id'],True)
            model['merged']=self.merge_states.get(model['id'],True)
        by_id={model['id']:model for model in panels}
        order=[self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        panels=[by_id[key] for key in order if key in by_id]+[model for model in panels if model['id'] not in order]
        changes=dict(desktop_panels=panels,disabled_categories=[key for key,_ in CATEGORIES if not enabled.get(key,True)],merged_panels=self.merged.isChecked())
        if self.manager.commit(**changes):
            self.manager.sync_windows();self.manager.schedule_scan();self.status.setText('分组设置已保存。')
        else:self.status.setText('保存失败，分组未更改。')
