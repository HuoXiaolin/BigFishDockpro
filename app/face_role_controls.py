"""Shared settings controls for importing and selecting a face skin."""
from PyQt5.QtWidgets import QApplication, QFileDialog, QHBoxLayout
from ui_style import ModernComboBox, button


ROLE_PROMPT = """请为大肥鱼Dock制作一个本地表情角色包。我会告诉你想要的形象，例如戴蓝白鲸鱼帽、有短发的女孩。请给出每个文件名和可直接保存的 UTF-8 文件内容。

必需文件只有 manifest.json 和 body.svg。需要刘海、帽檐等盖在五官上时，再提供 front.svg，并在 layers 中增加 "front": "front.svg"。文件都放在同一个文件夹。清单请输出标准 JSON，字段和结构如下。

{
  "version": 1,
  "id": "whale-girl",
  "name": "鲸鱼女孩",
  "layers": {"back": "body.svg"},
  "anchors": {"left_eye": [39, 54], "right_eye": [61, 54], "mouth": [50, 69]},
  "ink": "#23344D"
}

把 id 改成适合角色的小写英文标识，以字母开头，可含数字和连字符，最多 40 个字符。name 是设置里的名称，最多 32 字。ink 为五官颜色，省略或留空时使用应用主题色。

SVG 根节点使用 <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">。两个图层共用这一坐标系，x 向右、y 向下。back 画角色主体，front 画少量遮挡。请为两只眼睛和嘴留出空间，勿把它们画进 SVG。将三个锚点改成实际五官中心的 [x, y]。left_eye 是画面左眼，right_eye 是画面右眼，坐标范围 0 至 100。应用会在锚点绘制表情和视线跟随。

画布背景保持透明，轮廓和配色在 24 至 32 像素下也应清楚。可用 g、path、rect、circle、ellipse、line、polyline、polygon 和 defs 中的 linearGradient、radialGradient、stop。请用 fill、stroke 等元素属性配色，渐变只用 url(#id) 引用本文件定义。不使用 CSS、脚本、动画、滤镜、文字、use、图片或外部链接。每个 SVG 最多 64 KiB，清单最多 8 KiB。

保存后在大肥鱼Dock中点「导入角色包」，选择 manifest.json，再保存设置。
"""


class RolePicker(ModernComboBox):
    def __init__(self, library, selected):
        super().__init__()
        self.library = library
        self.setAccessibleName('表情角色')
        self.select(selected)

    def select(self, role_id):
        blocked = self.blockSignals(True)
        try:
            self.clear()
            self.addItem('内置表情', '')
            for name, key in self.library.choices():
                self.addItem(name, key)
            index = self.findData(role_id)
            if index < 0 and role_id:
                index = self.count()
                self.addItem('缺少角色包 · ' + role_id, role_id)
            self.setCurrentIndex(max(0, index))
        finally:
            self.blockSignals(blocked)

    def showPopup(self):
        self.select(self.currentData())
        super().showPopup()


def add_role_controls(owner, form, runtime, status, selected):
    picker = RolePicker(runtime.face_roles, selected)
    form.addRow('表情角色', picker)

    def import_role():
        path, _ = QFileDialog.getOpenFileName(owner, '选择角色包清单', '', '角色清单 (manifest.json)')
        if not path:
            return
        try:
            role_id = runtime.face_roles.import_package(path)
        except ValueError as error:
            status.setText(str(error))
            return
        except OSError:
            status.setText('无法读取或保存角色包，请检查文件和目录权限。')
            return
        picker.select(role_id)
        runtime.refresh_face_roles(role_id)
        status.setText('角色包已导入。保存设置后应用所选角色。')

    def copy_prompt():
        QApplication.clipboard().setText(ROLE_PROMPT)
        status.setText('已复制角色包提示词。')

    row = QHBoxLayout()
    row.addWidget(button('导入角色包…', import_role))
    row.addWidget(button('复制提示词', copy_prompt))
    row.addStretch()
    form.addRow(row)
    return picker
