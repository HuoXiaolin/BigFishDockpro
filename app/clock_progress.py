"""Quick editor for the clock's primary tile and the row underneath it."""
from datetime import date
from uuid import uuid4

from PyQt5.QtCore import QDate, QDateTime, QTime, Qt
from PyQt5.QtWidgets import (QDateTimeEdit, QDialog, QHBoxLayout, QHeaderView,
                             QLabel, QLineEdit, QTableWidget, QVBoxLayout)

from clock_faces import MAX_COUNTDOWNS, MAX_SECONDARY, PROGRESS_ITEMS
from ui_style import ModernComboBox, SettingsHeader, button, compact_dialog, label


class ClockProgressDialog(QDialog):
    def __init__(self, parent, progress, save):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.save = save
        self.rows = {}
        self.setWindowTitle('时光进度与倒计时')
        self.resize(620,410)
        body=QVBoxLayout(self)
        body.addWidget(SettingsHeader(self,'时光进度与倒计时'))
        body.addWidget(label(f'选一个主项目与时钟并排。下方同一行可放最多 {MAX_SECONDARY} 个次项目。','muted'))
        self.table=QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(('项目','目标日期和时间','重复','显示',''))
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for i,width in enumerate((164,84,90,36),1):self.table.setColumnWidth(i,width)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        body.addWidget(self.table,1)
        self.status=label('','muted')
        for identity,title in PROGRESS_ITEMS:
            self.add_row(identity,title,self.role_for(identity,progress))
        for row in progress['countdowns']:
            self.add_row(row['id'],row['title'],self.role_for(row['id'],progress),row['date'],row['repeat'],row.get('time'))
        tools=QHBoxLayout()
        for title,name,repeat in (('添加倒计时','新倒计时','once'),('＋ 发薪日','发薪日','monthly'),('＋ 生日','生日','yearly')):
            tools.addWidget(button(title,lambda _,name=name,repeat=repeat:self.add_countdown(name,repeat)))
        tools.addStretch(1)
        tools.addWidget(button('保存',self.commit))
        body.addLayout(tools);body.addWidget(self.status)
        compact_dialog(self)

    @staticmethod
    def role_for(identity,progress):
        return 'main' if identity==progress['primary'] else 'sub' if identity in progress['secondary'] else 'off'

    def add_row(self,identity,title,role,target=None,repeat=None,clock=None):
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
            day.setDisplayFormat('yyyy-MM-dd HH:mm');day.setAccessibleName('目标日期和时间')
            schedule=ModernComboBox();schedule.setAccessibleName('重复周期')
            for option,key in (('一次','once'),('每天','daily'),('每周','weekly'),('每月','monthly'),('每年','yearly')):schedule.addItem(option,key)
            schedule.setCurrentIndex(schedule.findData(repeat))
            fields=(name,day,schedule)
            for col,field in enumerate(fields):self.table.setCellWidget(index,col,field)
            remove=button('×',lambda:self.remove(identity));remove.setAccessibleName('删除倒计时')
            self.table.setCellWidget(index,4,remove)
        self.rows[identity]=(select,fields)
        select.currentIndexChanged.connect(lambda _:self.role_changed(select))

    def add_countdown(self,title,repeat):
        if len(self.rows)-len(PROGRESS_ITEMS)>=MAX_COUNTDOWNS:
            self.status.setText(f'最多保留 {MAX_COUNTDOWNS} 个自定义倒计时。')
            return
        role='sub' if sum(select.currentData()=='sub' for select,_ in self.rows.values())<MAX_SECONDARY else 'off'
        self.add_row(uuid4().hex,title,role,date.today().isoformat(),repeat)
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
        for identity,(select,fields) in self.rows.items():
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
                progress['countdowns'].append(dict(id=identity,title=title,date=target.date().toString(Qt.ISODate),
                                                   time=target.time().toString('HH:mm'),repeat=schedule.currentData()))
        if self.save(progress) is False:
            self.status.setText('保存失败，请重试。')
            return
        self.accept()
