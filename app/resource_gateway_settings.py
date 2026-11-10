"""Manage opt-in AI usage sources. Credentials stay in the local protected store."""
from uuid import uuid4

from PyQt5.QtWidgets import QDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QVBoxLayout

from resource_gateway import ENDPOINTS,KINDS,MAX_ACCOUNTS,UsageError,account_value,load_accounts,save_accounts
from ui_style import ModernComboBox,SettingsHeader,button,compact_dialog,exec_dialog


class GatewaySettings(QDialog):
    def __init__(self,service,parent):
        super().__init__(parent)
        self.service=service
        self.directory=service.runtime.api.CONFIG_DIR
        self.setWindowTitle('自定义用量接口');self.resize(510,314);self.setProperty('simpleForms',True)
        layout=QVBoxLayout(self);layout.addWidget(SettingsHeader(self,self.windowTitle()))
        form=QFormLayout();layout.addLayout(form)
        self.saved=ModernComboBox();self.kind=ModernComboBox()
        for key,label in KINDS.items():self.kind.addItem(label,key)
        self.name=QLineEdit();self.name.setMaxLength(48);self.name.setPlaceholderText('可留空')
        self.url=QLineEdit();self.url.setMaxLength(2048)
        self.url.setPlaceholderText('https://供应商地址/v1')
        self.token=QLineEdit();self.token.setMaxLength(4096);self.token.setEchoMode(QLineEdit.Password)
        for label,field in (('连接',self.saved),('供应商',self.kind),('显示名称',self.name),('API 地址',self.url),('Token',self.token)):
            field.setAccessibleName(label);form.addRow(label,field)
        self.hint=QLabel('自动识别可填写常用 API 地址。也可以指定完整用量地址。Token 使用 Windows 加密保存在本机。')
        self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.remove_button=button('移除连接',self.remove);actions.addWidget(self.remove_button);actions.addStretch()
        actions.addWidget(button('关闭',self.accept));actions.addWidget(button('保存连接',self.save,'primary'))
        self.saved.currentIndexChanged.connect(self.select)
        self.kind.currentIndexChanged.connect(self.preset)
        try:self.accounts=load_accounts(self.directory)
        except (ValueError,OSError):
            self.accounts=[];self.status.setText('旧连接文件读取失败，请重新添加。')
        self.reload(self.accounts[0]['id'] if self.accounts else None)
        compact_dialog(self)

    def reload(self,identity):
        self.saved.blockSignals(True);self.saved.clear();self.saved.addItem('新增连接',None)
        for row in self.accounts:self.saved.addItem(row['name'],row['id'])
        self.saved.setCurrentIndex(max(0,self.saved.findData(identity)));self.saved.blockSignals(False)
        self.select()

    def select(self):
        identity=self.saved.currentData()
        row=next((row for row in self.accounts if row['id']==identity),None)
        self.kind.blockSignals(True);self.kind.setCurrentIndex(self.kind.findData(row['kind'] if row else 'auto'))
        self.kind.blockSignals(False)
        self.name.setText(row['name'] if row else '')
        self.url.setText(row['url'] if row else '')
        self.token.setText(row['token'] if row else '')
        self.remove_button.setEnabled(row is not None)

    def preset(self):
        value=self.kind.currentData()
        if value in ENDPOINTS:self.url.setText(ENDPOINTS[value])

    def apply_accounts(self,rows,identity):
        try:save_accounts(self.directory,rows)
        except (ValueError,OSError):
            self.status.setText('保存失败，请检查本机数据目录。');return False
        self.accounts=rows;self.reload(identity)
        if self.service.deck:self.service.deck.load_gateways(rows)
        self.service.sync()
        return True

    def save(self):
        identity=self.saved.currentData()
        if identity is None and len(self.accounts)>=MAX_ACCOUNTS:
            self.status.setText(f'最多保存 {MAX_ACCOUNTS} 个用量连接。');return False
        try:
            row=account_value(dict(id=identity or uuid4().hex,kind=self.kind.currentData(),name=self.name.text(),
                                   url=self.url.text(),token=self.token.text()))
        except UsageError as error:
            self.status.setText(str(error));return False
        rows=[row if item['id']==identity else item for item in self.accounts]
        if identity is None:rows.append(row)
        if not self.apply_accounts(rows,row['id']):return False
        self.status.setText('已保存。AI 用量开启时会自动同步。')
        return True

    def remove(self):
        identity=self.saved.currentData()
        if identity and self.apply_accounts([row for row in self.accounts if row['id']!=identity],None):
            self.status.setText('已移除连接。')


def edit_gateways(service,parent):
    dialog=GatewaySettings(service,parent)
    try:exec_dialog(dialog)
    finally:dialog.deleteLater()
