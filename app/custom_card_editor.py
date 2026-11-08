"""Visual editing and paste import for native desktop card descriptions."""
import json
from uuid import uuid4

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QApplication,QColorDialog,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,QInputDialog,
                             QLineEdit,QPlainTextEdit,QScrollArea,QTableWidget,QTabWidget,QVBoxLayout,QWidget)

from custom_card_data import ARRANGEMENTS,KINDS,MAX_CARDS,MAX_ROWS,STYLES,TEMPLATE,TOOLS,developer_prompt,parse_card_json,validate_card
from ui_style import ModernCheckBox,ModernComboBox,ModernSpinBox,SettingsHeader,button,compact_dialog,label


class CardEditor(QDialog):
    def __init__(self,manager,identity):
        super().__init__(manager.runtime.dock,Qt.Dialog|Qt.FramelessWindowHint)
        self.manager=manager;self.identity=identity
        self.setProperty('simpleForms',True)
        self.setWindowTitle('原生卡片编辑器')
        self.resize(620,500)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'原生卡片编辑器'))
        picker=QHBoxLayout()
        self.cards=ModernComboBox();self.cards.setAccessibleName('选择卡片');picker.addWidget(self.cards,1)
        self.remove_button=button('删除卡片',self.remove);picker.addWidget(self.remove_button)
        body.addLayout(picker)
        self.tabs=QTabWidget();body.addWidget(self.tabs,1)
        basic=QWidget();base=QVBoxLayout(basic);self.tabs.addTab(basic,'内容')
        form=QFormLayout();self.title=QLineEdit();self.title.setMaxLength(28)
        self.title.setAccessibleName('卡片名称');form.addRow('名称',self.title)
        self.style=ModernComboBox()
        for value,name in STYLES.items():self.style.addItem(name,value)
        form.addRow('背景',self.style)
        self.width_field=ModernSpinBox();self.width_field.setRange(190,640);form.addRow('宽度',self.width_field)
        self.visible=ModernCheckBox('在桌面显示');form.addRow('',self.visible)
        base.addLayout(form)
        self.fields=QTableWidget(0,4)
        self.fields.setHorizontalHeaderLabels(('内容类型','显示名称','文字 / 日期 / 字段',''))
        header=self.fields.horizontalHeader();header.setSectionResizeMode(2,QHeaderView.Stretch)
        for col,width in ((0,111),(1,105),(3,35)):self.fields.setColumnWidth(col,width)
        self.fields.verticalHeader().hide();self.fields.setSelectionMode(QTableWidget.NoSelection)
        base.addWidget(self.fields,1)
        add_row=QHBoxLayout();add_row.addWidget(button('添加一行',lambda:self.add_row({'kind':'text'})));add_row.addStretch();base.addLayout(add_row)
        self.build_design()
        self.build_tools()
        actions=QHBoxLayout()
        actions.addWidget(button('导入 JSON',self.import_json))
        actions.addWidget(button('复制开发提示词',self.copy_prompt))
        actions.addStretch(1);actions.addWidget(button('保存卡片',self.commit,'primary'))
        body.addLayout(actions)
        self.status=label('每张卡片最多 6 行，可组合文字、倒计时与系统读数。','muted')
        body.addWidget(self.status)
        self.cards.currentIndexChanged.connect(self.load)
        self.fill_cards(identity)
        compact_dialog(self)

    @staticmethod
    def combo(values):
        field=ModernComboBox()
        for key,title in values.items():field.addItem(title,key)
        return field

    @staticmethod
    def spin(low,high):
        field=ModernSpinBox();field.setRange(low,high);return field

    def file_input(self,form,title,formats):
        field=QLineEdit();field.setAccessibleName(title);field.setMaxLength(1024)
        row=QHBoxLayout();row.addWidget(field,1)
        def browse():
            name,_=QFileDialog.getOpenFileName(self,title,'',formats)
            if name:field.setText(name)
        row.addWidget(button('选择…',browse));form.addRow(title,row)
        return field

    def build_design(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True);self.tabs.addTab(scroll,'排版与配图')
        page=QWidget();form=QFormLayout(page);form.setRowWrapPolicy(QFormLayout.WrapLongRows);scroll.setWidget(page)
        self.arrangement=self.combo(ARRANGEMENTS);form.addRow('排版',self.arrangement)
        self.header_date=ModernCheckBox('标题右侧显示日期');form.addRow(self.header_date)
        self.image=self.file_input(form,'配图','图片 (*.jpg *.jpeg *.png *.webp *.bmp)')
        self.fit=self.combo({'contain':'完整显示','cover':'裁切填满'});form.addRow('图片适配',self.fit)
        self.image_height=self.spin(48,250);form.addRow('图片高度',self.image_height)
        self.fonts={}
        for key,title in (('title','标题字号'),('label','标签字号'),('body','正文字号')):
            self.fonts[key]=self.spin(9,32);form.addRow(title,self.fonts[key])
        self.colors={}
        for key,title in (('surface','背景色'),('text','文字色'),('accent','强调色')):
            field=QLineEdit();field.setPlaceholderText('跟随应用 / #RRGGBB');field.setMaxLength(7)
            row=QHBoxLayout();row.addWidget(field,1)
            row.addWidget(button('选色',lambda _,field=field:self.choose_color(field)))
            self.colors[key]=field;form.addRow(title,row)
        self.data_file=self.file_input(form,'本地数据文件','JSON 文件 (*.json)')

    def choose_color(self,field):
        color=QColorDialog.getColor(QColor(field.text() or '#87bcd6'),self,'卡片配色')
        if color.isValid():field.setText(color.name())

    def build_tools(self):
        page=QWidget();lay=QVBoxLayout(page);self.tabs.addTab(page,'工具与接口')
        self.tool=self.combo(TOOLS);lay.addWidget(self.tool)
        lay.addWidget(label('可选模板，也可在下方修改工具参数或导入提示词生成的完整卡片 JSON。','muted'))
        self.tool_json=QPlainTextEdit();self.tool_json.setAccessibleName('工具 JSON');lay.addWidget(self.tool_json,1)
        self.tool.currentIndexChanged.connect(self.reset_tool)

    def reset_tool(self):
        kind=self.tool.currentData()
        options={'search':dict(engine='bing'),'pomodoro':dict(minutes=25,break_minutes=5),'history':dict(lang='zh',limit=3),
                 'rates':{'from':'USD','to':'CNY','amount':100},'feed':dict(url='',interval=1440),
                 'convert':dict(units=[dict(name='千米',factor=1000),dict(name='米',factor=1)])}
        value=dict(kind=kind,**options[kind]) if kind in options else {}
        self.tool_json.setPlainText(json.dumps(value,ensure_ascii=False,indent=2))

    def fill_cards(self,identity):
        blocked=self.cards.blockSignals(True)
        self.cards.clear();self.cards.addItem('新建卡片',None)
        for row in self.manager.cards:self.cards.addItem(row['title'],row['id'])
        self.cards.setCurrentIndex(max(0,self.cards.findData(identity)))
        self.cards.blockSignals(blocked);self.load()

    def load(self):
        self.identity=self.cards.currentData()
        self.remove_button.setEnabled(self.identity is not None)
        row=next((row for row in self.manager.cards if row['id']==self.identity),TEMPLATE)
        self.fill(row)

    def fill(self,row):
        visible=row.get('visible',True)
        row=validate_card(row)
        self.title.setText(row['title']);self.style.setCurrentIndex(self.style.findData(row['style']))
        self.width_field.setValue(row['width']);self.visible.setChecked(visible)
        self.arrangement.setCurrentIndex(self.arrangement.findData(row['arrangement']));self.header_date.setChecked(row['header_date'])
        image=row['image'];self.image.setText(image.get('path',''));self.fit.setCurrentIndex(self.fit.findData(image.get('fit','contain')))
        self.image_height.setValue(image.get('height',120));self.data_file.setText(row['data_file'])
        for key,field in self.fonts.items():field.setValue(row['fonts'][key])
        for key,field in self.colors.items():field.setText(row['colors'].get(key,''))
        self.tool.setCurrentIndex(max(0,self.tool.findData(row['tool'].get('kind',''))))
        self.tool_json.setPlainText(json.dumps(row['tool'],ensure_ascii=False,indent=2))
        self.fields.setRowCount(0)
        for item in row['rows']:self.add_row(item)

    def add_row(self,item):
        if self.fields.rowCount()>=MAX_ROWS:
            self.status.setText('最多可添加 6 行。')
            return
        row=self.fields.rowCount();self.fields.insertRow(row)
        kind=ModernComboBox()
        for key,name in KINDS.items():kind.addItem(name,key)
        kind.setCurrentIndex(max(0,kind.findData(item['kind'])))
        title=QLineEdit(item.get('label',''));title.setMaxLength(18);title.setPlaceholderText('可留空')
        value=QLineEdit(item.get('value','').replace('\n','\\n'));value.setMaxLength(520)

        def update():
            key=kind.currentData()
            value.setEnabled(key in ('text','countdown','data','remote'))
            value.setPlaceholderText({'countdown':'YYYY-MM-DD','text':'可用 \\n 换行','data':'字段名','remote':'如 items.0.title'}.get(key,'自动读取'))
        kind.currentIndexChanged.connect(update);update()
        delete=button('×',lambda:self.remove_row(kind))
        for col,field in enumerate((kind,title,value,delete)):self.fields.setCellWidget(row,col,field)

    def remove_row(self,widget):
        for row in range(self.fields.rowCount()):
            if self.fields.cellWidget(row,0) is widget:
                self.fields.removeRow(row)
                return

    def values(self):
        rows=[]
        for i in range(self.fields.rowCount()):
            kind,title,value=(self.fields.cellWidget(i,col) for col in range(3))
            rows.append(dict(kind=kind.currentData(),label=title.text(),value=value.text().replace('\\n','\n')))
        tool_text=self.tool_json.toPlainText().strip()
        if len(tool_text)>4096:raise ValueError('工具 JSON 过长。')
        try:tool=json.loads(tool_text or '{}')
        except (ValueError,RecursionError):raise ValueError('工具 JSON 格式无效。') from None
        return validate_card(dict(title=self.title.text(),style=self.style.currentData(),width=self.width_field.value(),rows=rows,
            arrangement=self.arrangement.currentData(),header_date=self.header_date.isChecked(),data_file=self.data_file.text(),tool=tool,
            image=dict(path=self.image.text(),fit=self.fit.currentData(),height=self.image_height.value()),
            fonts={key:field.value() for key,field in self.fonts.items()},colors={key:field.text().strip() for key,field in self.colors.items()}))

    def copy_prompt(self):
        QApplication.clipboard().setText(developer_prompt())
        self.status.setText('已复制开发提示词。生成的配置可粘贴到「导入 JSON」。')

    def import_json(self):
        raw,ok=QInputDialog.getMultiLineText(self,'导入卡片 JSON','粘贴一个卡片配置')
        if not ok:return
        try:
            card=parse_card_json(raw)
        except json.JSONDecodeError as error:
            self.status.setText(f'JSON 第 {error.lineno} 行第 {error.colno} 列格式无效。路径可写为 D:/图片/配图.png。');return
        except RecursionError:
            self.status.setText('JSON 层级过深。');return
        except ValueError as error:
            self.status.setText(str(error));return
        self.fill(card);self.status.setText('配置已载入编辑器，保存后显示。')

    def commit(self):
        try:card=self.values()
        except ValueError as error:
            self.status.setText(str(error));return False
        card['visible']=self.visible.isChecked()
        if self.identity is None:
            if len(self.manager.cards)>=MAX_CARDS:
                self.status.setText('最多可保存 8 张卡片。');return False
            identity=uuid4().hex
            saved=self.manager.save([*self.manager.cards,dict(card,id=identity,layout={},locked=False)])
        else:
            identity=self.identity;saved=self.manager.change(identity,**card)
        if not saved:
            self.status.setText('卡片保存失败。');return False
        self.fill_cards(identity);self.status.setText('已保存卡片。')
        return True

    def remove(self):
        if self.identity is not None and self.manager.save([row for row in self.manager.cards if row['id']!=self.identity]):
            self.fill_cards(None);self.status.setText('已删除选中的卡片。')
