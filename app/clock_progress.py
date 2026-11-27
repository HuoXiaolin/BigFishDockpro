"""Quick editor for the clock's primary tile and the row underneath it."""
from datetime import date
from uuid import uuid4

from PyQt5.QtCore import QDate, QDateTime, QEvent, QTime, QTimer, Qt
from PyQt5.QtWidgets import (QDateTimeEdit, QDialog, QHBoxLayout, QHeaderView,
                             QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout)

from clock_faces import MAX_COUNTDOWNS, MAX_SECONDARY, PROGRESS_ITEMS
from ui_style import ModernComboBox, SettingsHeader, button, compact_dialog, label


class ClockProgressDialog(QDialog):
    def __init__(self, parent, progress, save):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.save = save
        self.cfg=getattr(parent,'cfg',None) or getattr(getattr(getattr(parent,'clock',None),'dock',None),'cfg',{})
        self.rows = {}
        self.setWindowTitle('时光进度与倒计时')
        self.resize(790,500)
        body=QVBoxLayout(self)
        body.addWidget(SettingsHeader(self,'时光进度与倒计时'))
        from component_settings import ComponentPages, section, settings_footer
        self.tabs=ComponentPages(self,body,'时光进度')
        content=section(self.tabs.page('项目与倒计时','calendar'),'显示项目')
        hint=label(f'时钟可显示一个主项目和最多 {MAX_SECONDARY} 个次项目。勾选「日历」可同步到节日卡片和胶囊。','muted')
        hint.setWordWrap(True)
        content.addWidget(hint)
        self.table=QTableWidget(0,6)
        self.table.setObjectName('ClockProgressTable')
        self.table.setStyleSheet('QTableWidget#ClockProgressTable::item{padding:2px 4px;}')
        self.table.setHorizontalHeaderLabels(('项目','目标日期和时间','重复','时钟显示','日历',''))
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.viewport().installEventFilter(self)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setMinimumHeight(200)
        content.addWidget(self.table,1)
        self.status=label('','muted')
        for identity,title in PROGRESS_ITEMS:
            self.add_row(identity,title,self.role_for(identity,progress))
        for row in progress['countdowns']:
            self.add_row(row['id'],row['title'],self.role_for(row['id'],progress),row['date'],row['repeat'],row.get('time'),row.get('calendar',True))
        tools=QHBoxLayout()
        for title,name,repeat in (('添加倒计时','新倒计时','once'),('＋ 发薪日','发薪日','monthly'),('＋ 生日','生日','yearly')):
            tools.addWidget(button(title,lambda _,name=name,repeat=repeat:self.add_countdown(name,repeat)))
        tools.addStretch(1)
        content.addLayout(tools)
        settings_footer(self,body,self.status,self.commit)
        compact_dialog(self)

    def showEvent(self,event):
        super().showEvent(event)
        self.fit_editors()
        QTimer.singleShot(0,self.fit_editors)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Resize and watched is self.table.viewport():
            self.fit_name_column()
        return super().eventFilter(watched,event)

    def fit_name_column(self):
        table=self.table
        available=table.viewport().width()-sum(table.columnWidth(c) for c in range(1,table.columnCount()))
        minimum=max(78,table.fontMetrics().horizontalAdvance('工作日 / 下班')+14)
        table.setColumnWidth(0,max(minimum,available))

    def fit_editors(self):
        from ui_style import widget_px
        header=self.table.horizontalHeader()
        pad=2*widget_px(self,8)+2
        sizes=[0]+[header.fontMetrics().horizontalAdvance(self.table.horizontalHeaderItem(i).text())+pad for i in range(1,6)]
        metrics=self.table.fontMetrics()
        sizes[1]=max(sizes[1],metrics.horizontalAdvance('2000-12-31 23:59')+46+pad)
        for row in range(self.table.rowCount()):
            height=metrics.height()
            for col in range(6):
                field=self.table.cellWidget(row,col)
                if field is None:continue
                field.ensurePolished()
                hint=field.sizeHint().expandedTo(field.minimumSizeHint()).expandedTo(field.minimumSize())
                height=max(height,min(field.maximumHeight(),hint.height()))
                if isinstance(field,ModernComboBox):
                    content=max(field.fontMetrics().horizontalAdvance(field.itemText(i)) for i in range(field.count()))
                    sizes[col]=max(sizes[col],content+widget_px(self,42)+pad)
                elif col:sizes[col]=max(sizes[col],min(field.maximumWidth(),hint.width())+pad)
            self.table.setRowHeight(row,height+2*widget_px(self,4)+1)
        for col in range(1,6):self.table.setColumnWidth(col,sizes[col])
        self.fit_name_column()

    @staticmethod
    def role_for(identity,progress):
        return 'main' if identity==progress['primary'] else 'sub' if identity in progress['secondary'] else 'off'

    def add_row(self,identity,title,role,target=None,repeat=None,clock=None,calendar=True):
        index=self.table.rowCount()
        self.table.insertRow(index)
        select=ModernComboBox();select.setAccessibleName(title+'显示方式')
        for name,key in (('隐藏','off'),('主项目','main'),('次项目','sub')):select.addItem(name,key)
        select.setCurrentIndex(select.findData(role))
        self.table.setCellWidget(index,3,select)
        if target is None:
            self.table.setCellWidget(index,0,QLabel(title))
            fields=(None,None,None)
        else:
            name=QLineEdit(title);name.setMaxLength(28);name.setAccessibleName('倒计时名称')
            at=QDateTime(QDate.fromString(target,Qt.ISODate),QTime.fromString(clock or '00:00','HH:mm'))
            day=QDateTimeEdit(at);day.setCalendarPopup(True)
            day.setProperty('dateOnly',not clock)
            day.setDisplayFormat('yyyy-MM-dd HH:mm');day.setAccessibleName('目标日期和时间')
            from popup_style import prepare_date
            prepare_date(day)
            schedule=ModernComboBox();schedule.setAccessibleName('重复周期')
            for option,key in (('一次','once'),('每天','daily'),('每周','weekly'),('每月','monthly'),('每年','yearly')):schedule.addItem(option,key)
            schedule.setCurrentIndex(schedule.findData(repeat))
            fields=(name,day,schedule)
            for col,field in enumerate(fields):self.table.setCellWidget(index,col,field)
            remove=button('×',lambda:self.remove(identity));remove.setAccessibleName('删除倒计时')
            from ui_style import widget_px
            remove.setFixedWidth(widget_px(self,32))
            self.table.setCellWidget(index,5,remove)
            participation=QTableWidgetItem()
            participation.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable)
            participation.setCheckState(Qt.Checked if calendar else Qt.Unchecked)
            participation.setToolTip('同步此倒计时到日历、节日卡片和灵动胶囊')
            self.table.setItem(index,4,participation)
        self.rows[identity]=(select,fields)
        select.currentIndexChanged.connect(lambda _:self.role_changed(select))

    def add_countdown(self,title,repeat):
        if len(self.rows)-len(PROGRESS_ITEMS)>=MAX_COUNTDOWNS:
            self.status.setText(f'最多保留 {MAX_COUNTDOWNS} 个自定义倒计时。')
            return
        role='sub' if sum(select.currentData()=='sub' for select,_ in self.rows.values())<MAX_SECONDARY else 'off'
        self.add_row(uuid4().hex,title,role,date.today().isoformat(),repeat)
        self.fit_editors()
        self.table.scrollToBottom()

    def role_changed(self,changed):
        role=changed.currentData()
        if role=='main':
            for select,_ in self.rows.values():
                if select is not changed and select.currentData()=='main':
                    select.setCurrentIndex(select.findData('off'))
        if role=='sub' and sum(select.currentData()=='sub' for select,_ in self.rows.values())>MAX_SECONDARY:
            changed.setCurrentIndex(changed.findData('off'))
            self.status.setText(f'请先隐藏一个次项目，最多显示 {MAX_SECONDARY} 个。')
        else:self.status.clear()

    def remove(self,identity):
        index=list(self.rows).index(identity)
        del self.rows[identity]
        self.table.removeRow(index)

    def commit(self):
        progress=dict(primary='',secondary=[],countdowns=[])
        for index,(identity,(select,fields)) in enumerate(self.rows.items()):
            role=select.currentData()
            if role=='main':progress['primary']=identity
            if role=='sub':progress['secondary'].append(identity)
            name,target,schedule=fields
            if name is not None:
                title=name.text().strip()
                if not title:
                    self.status.setText('请为倒计时填写名称。')
                    name.setFocus()
                    return
                stamp=target.time().toString('HH:mm')
                progress['countdowns'].append(dict(id=identity,title=title,date=target.date().toString(Qt.ISODate),
                                                   time='' if target.property('dateOnly') and stamp=='00:00' else stamp,repeat=schedule.currentData(),
                                                   calendar=self.table.item(index,4).checkState()==Qt.Checked))
        if self.save(progress) is False:
            self.status.setText('保存失败，请重试。')
            return
        self.status.setText('已保存。')
