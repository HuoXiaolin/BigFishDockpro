"""Direct-manipulation card groups: drag, multi-select and inline group naming."""
import copy,json,uuid
from PyQt5.QtCore import Qt,QMimeData,QSize
from PyQt5.QtGui import QDrag,QIcon,QFont,QColor,QBrush
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QTreeWidget,QTreeWidgetItem,
    QAbstractItemView,QHeaderView,QWidget,QMessageBox,QStyledItemDelegate,QStyleOptionViewItem,QStyle)
from ui_style import SettingsHeader,ModernCheckBox,AlignedMenu,label,button,compact_dialog
from desktop_catalog import CATEGORIES

MIME='application/x-bigfishdock-panel-groups'
ROLE=Qt.UserRole


class GroupDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);opt.state &= ~QStyle.State_HasFocus
        super().paint(painter,opt,index)


class GroupTree(QTreeWidget):
    def __init__(self,dialog):
        super().__init__();self.dialog=dialog
        self.setAccessibleName('拖拽卡片分组');self.setItemDelegate(GroupDelegate(self))
        self.setColumnCount(2);self.setHeaderHidden(True);self.setIndentation(20);self.setRootIsDecorated(False)
        self.header().setSectionResizeMode(0,QHeaderView.Stretch);self.header().setSectionResizeMode(1,QHeaderView.Fixed);self.setColumnWidth(1,180)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection);self.setDragEnabled(True);self.setAcceptDrops(True)
        self.setDropIndicatorShown(True);self.setDragDropMode(QAbstractItemView.DragDrop);self.setDefaultDropAction(Qt.MoveAction)
        self.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed)
        self.setContextMenuPolicy(Qt.CustomContextMenu);self.customContextMenuRequested.connect(dialog.context_menu)
        self.setProperty('lightGroupTree',True)

    def startDrag(self,actions):
        identities=[item.data(0,ROLE) for item in self.dialog.card_items() if item.isSelected()]
        if not identities:return
        mime=QMimeData();mime.setData(MIME,json.dumps(identities).encode('utf-8'))
        drag=QDrag(self);drag.setMimeData(mime);drag.exec_(Qt.MoveAction)

    def valid_drag(self,event):
        return event.source() is self and event.mimeData().hasFormat(MIME)

    def dragEnterEvent(self,event):
        if self.valid_drag(event):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        if self.valid_drag(event):
            super().dragMoveEvent(event);event.acceptProposedAction()
        else:event.ignore()

    def dropEvent(self,event):
        if not self.valid_drag(event):event.ignore();return
        item=self.itemAt(event.pos())
        if item is None:event.ignore();return
        parent=item.parent() or item;group=parent.data(0,ROLE)
        before=None
        if item.parent():
            index=parent.indexOfChild(item)
            if event.pos().y()>self.visualItemRect(item).center().y():index+=1
            before=parent.child(index).data(0,ROLE) if index<parent.childCount() else None
        try:identities=json.loads(bytes(event.mimeData().data(MIME)).decode('utf-8'))
        except (ValueError,UnicodeDecodeError):event.ignore();return
        if self.dialog.move_cards(identities,group,before):event.acceptProposedAction()
        else:event.ignore()


class GroupDialog(QDialog):
    def __init__(self,manager):
        super().__init__(None,Qt.Dialog|Qt.FramelessWindowHint)
        self.manager=manager;self.merge_groups=copy.deepcopy(manager.cfg['merge_groups']);self.nodes={};self.loading=True
        self.setProperty('compactDialog',True);self.setWindowTitle('卡片分组 · 大肥鱼Dock');self.resize(780,640);self.setMinimumSize(660,480)
        body=QVBoxLayout(self);body.setContentsMargins(18,14,18,16);body.setSpacing(10)
        body.addWidget(SettingsHeader(self,'卡片分组'))
        body.addWidget(label('拖入合并组即可归组，组内拖动排序；拖到“独立显示”即可拆出。','muted'))
        toolbar=QHBoxLayout();toolbar.addWidget(button('新建合并组',lambda:self.create_group(),'primary'));toolbar.addWidget(button('新建卡片',self.create));toolbar.addStretch()
        self.merged=ModernCheckBox('启用合并');self.merged.setChecked(manager.cfg['merged_panels']);toolbar.addWidget(self.merged);body.addLayout(toolbar)
        self.tree=GroupTree(self);body.addWidget(self.tree,1)
        bulk=QHBoxLayout();self.selection=label('可按 Ctrl / Shift 多选','muted');bulk.addWidget(self.selection,1)
        self.move_button=button('移至…',self.move_menu);self.detach_button=button('独立显示',lambda:self.move_selected('independent'));bulk.addWidget(self.move_button);bulk.addWidget(self.detach_button);body.addLayout(bulk)
        self.move_button.setEnabled(False);self.detach_button.setEnabled(False)
        body.addWidget(label('勾选控制卡片显示；双击合并组名称可直接改名。删除合并组会将卡片移回默认组。','muted'))
        self.status=label('调整后点击“保存分组”；关闭放弃本页尚未保存的分组调整。','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addWidget(button('编辑卡片名称与格式',self.edit));actions.addStretch();actions.addWidget(button('关闭',self.reject));actions.addWidget(button('保存分组',self.commit,'primary'));body.addLayout(actions)
        self.populate();self.tree.itemChanged.connect(self.item_changed);self.tree.itemSelectionChanged.connect(self.selection_changed);self.loading=False
        compact_dialog(self)

    def card_items(self):
        return [self.tree.topLevelItem(i).child(j) for i in range(self.tree.topLevelItemCount()) for j in range(self.tree.topLevelItem(i).childCount())]

    def find_card(self,identity):
        return next((item for item in self.card_items() if item.data(0,ROLE)==identity),None)

    def add_group_node(self,key,name):
        node=QTreeWidgetItem([name]);node.setData(0,ROLE,key)
        flags=Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsDropEnabled|Qt.ItemIsUserCheckable|Qt.ItemIsAutoTristate
        if key!='independent':flags|=Qt.ItemIsEditable
        node.setFlags(flags);font=node.font(0);font.setWeight(QFont.DemiBold);node.setFont(0,font)
        node.setSizeHint(0,QSize(0,44));shade=QBrush(QColor(128,128,128,18));node.setBackground(0,shade);node.setBackground(1,shade)
        self.tree.addTopLevelItem(node);node.setExpanded(True);self.nodes[key]=node
        if key!='independent':
            tools=QWidget();row=QHBoxLayout(tools);row.setContentsMargins(0,0,3,0);row.setSpacing(5)
            count=label('','muted');count.setObjectName('GroupCount');row.addWidget(count,1)
            if key!='default':row.addWidget(button('删除组',lambda checked=False,g=key:self.remove_group(g)))
            self.tree.setItemWidget(node,1,tools)
        return node

    def populate(self):
        # Keep unsaved membership/order/display states when a new card is created.
        previous=[(item.data(0,ROLE),item.parent().data(0,ROLE),item.checkState(0)) for item in self.card_items()]
        previous_by_id={key:(group,state) for key,group,state in previous}
        models={model['id']:model for model in self.manager.cfg['desktop_panels']}
        order=list(dict.fromkeys([key for key,_,_ in previous]+list(models)+[key for key,_ in CATEGORIES]))
        self.tree.blockSignals(True);self.tree.clear();self.nodes={}
        for group in self.merge_groups:self.add_group_node(group['id'],group['name'])
        self.add_group_node('independent','独立显示')
        from glass_panel import category_icon,category_color
        for identity in order:
            model=models.get(identity,{'id':identity,'name':dict(CATEGORIES).get(identity,'收纳卡片')})
            group=model.get('merge_group','default') if model.get('merged',True) else 'independent'
            enabled=model.get('enabled',True) and identity not in self.manager.cfg['disabled_categories']
            group,state=previous_by_id.get(identity,(group,Qt.Checked if enabled else Qt.Unchecked))
            if group not in self.nodes:group='default'
            details='默认分类' if identity in dict(CATEGORIES) else (' '.join(model.get('extensions',[])) or '手动收纳')
            item=QTreeWidgetItem([model['name'],details]);item.setData(0,ROLE,identity)
            item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsDragEnabled|Qt.ItemIsDropEnabled|Qt.ItemIsUserCheckable)
            item.setCheckState(0,state);item.setToolTip(0,model['name']+' · '+details)
            item.setIcon(0,QIcon(category_icon(identity,category_color(identity),16,self.devicePixelRatioF())))
            self.nodes[group].addChild(item)
        self.refresh_counts();self.tree.blockSignals(False)

    def refresh_counts(self):
        for key,node in self.nodes.items():
            widget=self.tree.itemWidget(node,1)
            if widget:
                count=widget.findChild(QWidget,'GroupCount')
                if count:count.setText('%d 张卡片'%node.childCount())

    def selection_changed(self):
        count=sum(item.isSelected() for item in self.card_items());self.selection.setText('已选 %d 张卡片'%count if count else '可按 Ctrl / Shift 多选')
        self.move_button.setEnabled(count>0);self.detach_button.setEnabled(count>0)

    def item_changed(self,item,column):
        if self.loading or item.parent() or item.data(0,ROLE)=='independent':return
        key=item.data(0,ROLE);row=next(group for group in self.merge_groups if group['id']==key)
        name=item.text(0).strip()[:40]
        self.tree.blockSignals(True);item.setText(0,name or row['name']);self.tree.blockSignals(False)
        if name and name!=row['name']:row['name']=name;self.status.setText('组名已调整，保存后应用。')

    def move_cards(self,identities,group,before=None):
        if not isinstance(identities,list) or not identities or group not in self.nodes:return False
        if len(identities)>256 or not all(isinstance(identity,str) for identity in identities):return False
        ids=set(identities)
        items=[item for item in self.card_items() if item.data(0,ROLE) in ids]
        if len(items)!=len(ids):return False
        target=self.nodes[group];anchor=self.find_card(before) if before else None
        if anchor in items:return False
        if anchor and anchor.parent() is not target:return False
        self.tree.blockSignals(True)
        for item in items:item.parent().takeChild(item.parent().indexOfChild(item))
        index=target.indexOfChild(anchor) if anchor else target.childCount()
        for offset,item in enumerate(items):target.insertChild(index+offset,item);item.setSelected(True)
        target.setExpanded(True);self.refresh_counts();self.tree.blockSignals(False)
        if group!='independent':self.merged.setChecked(True)
        self.tree.scrollToItem(items[0]);self.selection_changed();self.status.setText('已移动 %d 张卡片到“%s”，保存后应用。'%(len(items),target.text(0)))
        return True

    def selected_ids(self):return [item.data(0,ROLE) for item in self.card_items() if item.isSelected()]
    def move_selected(self,group):return self.move_cards(self.selected_ids(),group)

    def create_group(self,name=None):
        if len(self.merge_groups)>=64:self.status.setText('最多支持 64 个合并组。');return False
        if not isinstance(name,str) or not name.strip():
            used={row['name'] for row in self.merge_groups};number=1
            while '合并组 %d'%number in used:number+=1
            name='合并组 %d'%number
        selected=self.selected_ids()
        key=uuid.uuid4().hex;self.merge_groups.append({'id':key,'name':name.strip()[:40],'active':'','geometry':[],'collapsed':False,'compact':True})
        self.populate();node=self.nodes[key];self.merged.setChecked(True)
        if selected:self.move_cards(selected,key)
        else:self.tree.setCurrentItem(node)
        self.tree.scrollToItem(node)
        self.status.setText(('已新建“%s”并移入 %d 张卡片，保存后应用。'%(node.text(0),len(selected))) if selected else '已新建“%s”，可直接拖入卡片；双击组名可改名。'%node.text(0));return key

    def remove_group(self,key):
        if key=='default' or key not in self.nodes:return False
        if QMessageBox.question(self,'删除合并组','删除“%s”？其中卡片移回默认组，文件与引用会保留。'%self.nodes[key].text(0),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return False
        identities=[self.nodes[key].child(i).data(0,ROLE) for i in range(self.nodes[key].childCount())]
        if identities:self.move_cards(identities,'default')
        self.merge_groups=[row for row in self.merge_groups if row['id']!=key]
        node=self.nodes.pop(key);self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(node));self.refresh_counts();return True

    def move_menu(self):
        if not self.selected_ids():self.status.setText('请先选择要移动的卡片，支持多选。');return
        menu=AlignedMenu(self)
        for key,node in self.nodes.items():menu.addAction(node.text(0)).triggered.connect(lambda checked=False,g=key:self.move_selected(g))
        from PyQt5.QtGui import QCursor
        menu.exec_(QCursor.pos());menu.deleteLater()

    def context_menu(self,point):
        item=self.tree.itemAt(point)
        if not item:return
        menu=AlignedMenu(self)
        if item.parent():
            if not item.isSelected():self.tree.clearSelection();item.setSelected(True)
            submenu=menu.addMenu('移至')
            for key,node in self.nodes.items():submenu.addAction(node.text(0)).triggered.connect(lambda checked=False,g=key:self.move_selected(g))
            menu.addAction('编辑名称与格式…').triggered.connect(self.edit)
        else:
            key=item.data(0,ROLE)
            if key!='independent':menu.addAction('重命名').triggered.connect(lambda:self.tree.editItem(item,0))
            if key not in ('default','independent'):menu.addAction('删除合并组').triggered.connect(lambda:self.remove_group(key))
        if menu.actions():menu.exec_(self.tree.viewport().mapToGlobal(point))
        menu.deleteLater()

    def create(self):
        if self.manager.new_panel():self.populate()

    def edit(self):
        item=self.tree.currentItem()
        if not item or not item.parent():self.status.setText('请选择一张卡片。');return
        identity=item.data(0,ROLE)
        if identity in dict(CATEGORIES):self.status.setText('默认卡片按内置规则分类；可直接勾选开启或关闭。');return
        from panel_management import PanelDefinition
        dialog=PanelDefinition(self.manager.model(identity),self)
        if dialog.exec_()==dialog.Accepted:
            self.manager.update_panel(identity,name=dialog.name.text().strip()[:40],extensions=dialog.extensions());self.populate();self.manager.schedule_scan()

    def commit(self):
        self.tree.setFocus()  # Commit any inline group-name editor first.
        self.manager.save_visible_geometry()
        current={row['id']:row for row in self.manager.cfg['desktop_panels']};definitions=dict(CATEGORIES);panels=[];enabled={}
        for item in self.card_items():
            identity=item.data(0,ROLE);visible=item.checkState(0)==Qt.Checked;enabled[identity]=visible
            if identity not in current and not visible:continue
            row=copy.deepcopy(current.get(identity,{'id':identity,'name':definitions.get(identity,'收纳卡片')}))
            group=item.parent().data(0,ROLE);row.update(enabled=visible,merged=group!='independent',merge_group='default' if group=='independent' else group);panels.append(row)
        current_groups={row['id']:row for row in self.manager.cfg['merge_groups']}
        groups=[dict(copy.deepcopy(current_groups.get(row['id'],row)),name=row['name']) for row in self.merge_groups]
        changes=dict(desktop_panels=panels,disabled_categories=[key for key,_ in CATEGORIES if not enabled.get(key,True)],merge_groups=groups,merged_panels=self.merged.isChecked(),merge_initialized=self.manager.cfg.get('merge_initialized',False) or self.merged.isChecked())
        if self.manager.commit(**changes):
            self.manager.status('');self.manager.sync_windows();self.manager.schedule_scan();self.status.setText('分组已保存。')
            return True
        self.status.setText('保存失败，原分组保持不变。');return False
