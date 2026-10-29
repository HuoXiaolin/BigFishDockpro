"""Event-driven desktop sticky notes, with three selectable visual styles."""
import copy
import ctypes
import datetime
import json
import os
from pathlib import Path
import uuid
from types import SimpleNamespace
from PyQt5.QtCore import Qt,QObject,QTimer,QRectF,QEvent,QPoint,pyqtSignal,QVariant
from PyQt5.QtGui import QPainter,QPainterPath,QColor,QPen,QLinearGradient,QFont,QTextCharFormat,QTextListFormat,QTextCursor,QTextDocument,QPalette,QIcon
from PyQt5.QtWidgets import QWidget,QDialog,QLayout,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QTextEdit,QToolButton,QLabel,QSizeGrip,QApplication,QListWidget,QListWidgetItem,QTabBar,QMessageBox,QShortcut
from PyQt5.QtGui import QKeySequence,QCursor
from ui_style import AlignedMenu,button,label,SettingsHeader,compact_dialog,ModernComboBox,ModernSpinBox,ModernCheckBox
from sticky_notes_store import STYLES,COLORS,normalize_notes,clean_editor_html
from screen_layout import capture,project,screen_records,initial_card_factor
from liquid_glass import paint_liquid_glass,tint_palette


NOTE_ICON_COLORS={'#fff1a8':'#a56b09','#ffdce5':'#be4e7b','#d4eedc':'#278564',
                  '#cfe8fa':'#2f75d9','#e3ddf6':'#8057bd','#f6dfbf':'#ae6a27','#eef1f5':'#55738d'}


def note_icon_color(color):
    value=QColor(color)
    return NOTE_ICON_COLORS.get(value.name(),(value.darker(200) if value.lightness()>110 else value.lighter(170)).name())


class LocalDocument(QTextDocument):
    def loadResource(self,kind,url):return QVariant()  # No remote images or local-file reads.


class NoteEditor(QTextEdit):
    def __init__(self,parent):
        super().__init__(parent)
        self.setDocument(LocalDocument(self));self.setAcceptRichText(False)
        self.setPlaceholderText('写点什么…  选中文字可设置格式')
        self.setTabChangesFocus(False)
    def mousePressEvent(self,event):
        self.press_point=event.pos();super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        cursor=self.cursorForPosition(event.pos())
        if event.button()==Qt.LeftButton and hasattr(self,'press_point') and (event.pos()-self.press_point).manhattanLength()<4 and not self.textCursor().hasSelection() and cursor.positionInBlock()<=1 and cursor.block().text().startswith(('☐ ','☑ ')):
            cursor.movePosition(QTextCursor.StartOfBlock);self.setTextCursor(cursor);self.window().format_text('todo')
    def insertFromMimeData(self,source):
        if source.hasText():self.insertPlainText(source.text())


class NoteTitle(QLineEdit):
    committed=pyqtSignal()
    def __init__(self):
        super().__init__();self.editing=False;self.before='';self.setReadOnly(True);self.setFocusPolicy(Qt.NoFocus);self.setCursor(Qt.ArrowCursor)
        self.setMaxLength(60);self.setPlaceholderText('便签标题');self.setToolTip('双击修改标题；Enter保存，Esc取消')
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.before=self.text();self.editing=True;self.setReadOnly(False);self.setFocusPolicy(Qt.StrongFocus);self.setCursor(Qt.IBeamCursor)
            self.setFocus(Qt.MouseFocusReason);self.selectAll();event.accept();return
        super().mouseDoubleClickEvent(event)
    def finish_edit(self,cancel=False):
        if not self.editing:return
        self.editing=False
        value=self.before if cancel else self.text().strip() or '新便签'
        self.setText(value);self.setReadOnly(True);self.setFocusPolicy(Qt.NoFocus);self.setCursor(Qt.ArrowCursor);self.deselect()
        if not cancel and value!=self.before:self.committed.emit()
    def keyPressEvent(self,event):
        if self.editing and event.key() in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Escape):
            self.finish_edit(event.key()==Qt.Key_Escape);self.clearFocus();event.accept();return
        super().keyPressEvent(event)
    def focusOutEvent(self,event):
        self.finish_edit();super().focusOutEvent(event)


class NoteWindow(QWidget):
    def __init__(self,manager,identity):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint)
        self.manager,self.runtime,self.dock=manager,manager.runtime,manager.runtime.dock
        self.identity=identity;self.loading=True;self.disposed=False;self.drag=None;self.backdrop=None;self.ui_factor=1.0;self.expanded_height=260
        self.setObjectName('StickyNote');self.setAttribute(Qt.WA_ShowWithoutActivating);self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(230,150)
        self.layout_box=QVBoxLayout(self);self.layout_box.setSizeConstraint(QLayout.SetNoConstraint);self.layout_box.setContentsMargins(12,9,12,9);self.layout_box.setSpacing(6)
        header=QHBoxLayout();header.setSpacing(4)
        self.handle=QLabel('');self.handle.setToolTip('拖动便签');self.handle.setAccessibleName('便签图标，拖动移动便签');self.handle.installEventFilter(self);header.addWidget(self.handle)
        self.title=NoteTitle();header.addWidget(self.title);header.addStretch(1)
        self.flip_button=self.tool('↔','点击翻面：正文 / 待办',self.flip);header.addWidget(self.flip_button)
        self.settings_button=self.tool('','便签设置',self.open_settings);header.addWidget(self.settings_button)
        self.more=self.tool('⋯','便签菜单',self.show_menu);header.addWidget(self.more)
        self.collapse_button=self.tool('−','收起 / 展开',self.toggle_collapse);header.addWidget(self.collapse_button)
        self.layout_box.addLayout(header)
        self.tools=QWidget();toolbar=QHBoxLayout(self.tools);toolbar.setContentsMargins(0,0,0,0);toolbar.setSpacing(3)
        self.format_buttons={}
        for text,tip,key in [('B','加粗 Ctrl+B','bold'),('I','斜体 Ctrl+I','italic'),('U','下划线 Ctrl+U','underline'),('S','删除线','strike'),('•','项目符号','bullet'),('☐','切换待办完成状态','todo')]:
            widget=self.tool(text,tip,lambda checked=False,k=key:self.format_text(k));toolbar.addWidget(widget);self.format_buttons[key]=widget
        toolbar.addStretch();self.layout_box.addWidget(self.tools)
        from flip_stack import FlipStack
        self.pages=FlipStack(self);self.editor=NoteEditor(self);self.pages.addWidget(self.editor)
        self.todo_page=QWidget();self.todo_page.setObjectName('NoteTodoPage');self.todo_page.setAutoFillBackground(False);self.todo_page.setStyleSheet('QWidget#NoteTodoPage {background:transparent;border:0;}');todo_layout=QVBoxLayout(self.todo_page);todo_layout.setContentsMargins(0,0,0,0);todo_layout.setSpacing(5)
        todo_layout.addWidget(label('待办清单','section'));self.todos=QListWidget();self.todos.setObjectName('NoteTodos');todo_layout.addWidget(self.todos,1)
        self.todo_input=QLineEdit();self.todo_input.setPlaceholderText('输入待办，按 Enter 添加');self.todo_input.returnPressed.connect(self.add_todo);todo_layout.addWidget(self.todo_input)
        self.pages.addWidget(self.todo_page);self.layout_box.addWidget(self.pages,1);self.todos.itemChanged.connect(self.toggle_todo)

        footer=QHBoxLayout();self.status=QLabel('');self.status.setWordWrap(True);footer.addWidget(self.status,1)
        self.retry=self.tool('↻','立即保存 / 重试',self.manager.flush);footer.addWidget(self.retry)
        from ui_style import SubtleSizeGrip
        self.grip=SubtleSizeGrip(self,lambda:QColor(self.row()['color']).lightness()>110);self.grip.setFixedSize(12,12);footer.addWidget(self.grip,0,Qt.AlignBottom)
        self.footer=QWidget();self.footer.setLayout(footer);self.layout_box.addWidget(self.footer)
        self.title.committed.connect(self.changed);self.title.textChanged.connect(self.fit_title);self.editor.textChanged.connect(self.changed)
        self.title.installEventFilter(self);self.editor.installEventFilter(self)
        self.geometry_timer=QTimer(self);self.geometry_timer.setSingleShot(True);self.geometry_timer.setInterval(250);self.geometry_timer.timeout.connect(self.save_geometry)
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True);self.refresh_timer.setInterval(160);self.refresh_timer.timeout.connect(self.capture_backdrop)
        self.collapse_timer=QTimer(self);self.collapse_timer.setSingleShot(True);self.collapse_timer.setInterval(650);self.collapse_timer.timeout.connect(self.collapse_if_outside)
        self.expand_timer=QTimer(self);self.expand_timer.setSingleShot(True);self.expand_timer.setInterval(160);self.expand_timer.timeout.connect(self.expand_if_inside)
        for keys,kind in [('Ctrl+B','bold'),('Ctrl+I','italic'),('Ctrl+U','underline'),('Ctrl+Shift+L','bullet')]:
            shortcut=QShortcut(QKeySequence(keys),self);shortcut.activated.connect(lambda k=kind:self.format_text(k))
        shortcut=QShortcut(QKeySequence('Ctrl+S'),self);shortcut.activated.connect(manager.flush)
        row=self.row();self.title.setText(row['title']);self.editor.setHtml(clean_editor_html(row['html']));self.pages.setCurrentIndex(1 if row.get('flipped') else 0);self.rebuild_todos()
        self.resize(300,260);self.reposition();self.apply_style();self.loading=False

    def tool(self,text,tip,callback):
        widget=QToolButton(self);widget.setText(text);widget.setToolTip(tip);widget.setAccessibleName(tip);widget.setFixedSize(23,23);widget.clicked.connect(callback);return widget
    def nativeEvent(self,event_type,message):
        from fold_options import native_minimum
        if native_minimum(self,message):return True,0
        return super().nativeEvent(event_type,message)
    def row(self):return self.manager.row(self.identity)
    def changed(self):
        if self.loading or self.disposed or self.manager.closed:return
        if self.row().get('flipped') and not getattr(self,'_toggling_todo',False):self.rebuild_todos()
        text=self.editor.toPlainText()
        self.manager.update(self.identity,title=self.row()['title'] if self.title.editing else self.title.text().strip() or '新便签',html=clean_editor_html(self.editor.toHtml()),text=text)
    def flip(self):
        if self.disposed or self.row()['collapsed']:return
        target=not self.row().get('flipped',False)
        if target:self.rebuild_todos()
        if not self.manager.update_and_save(self.identity,flipped=target):
            self.manager.update(self.identity,flipped=not target);return
        self.tools.setVisible(not target);self.layout_box.activate()
        self.pages.flip_to(1 if target else 0)
        self.flip_button.setToolTip('点击翻面：'+('返回正文' if target else '查看待办'))

    def rebuild_todos(self):
        self.todos.blockSignals(True);self.todos.clear();block=self.editor.document().begin()
        while block.isValid():
            value=block.text()
            if value.startswith(('☐ ','☑ ')):
                item=QListWidgetItem(value[2:]);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if value.startswith('☑') else Qt.Unchecked);item.setData(Qt.UserRole,block.blockNumber());self.todos.addItem(item)
            block=block.next()
        if not self.todos.count():
            item=QListWidgetItem('暂无待办，可在下方直接添加');item.setFlags(Qt.NoItemFlags);self.todos.addItem(item)
        self.todos.blockSignals(False)

    def add_todo(self):
        value=self.todo_input.text().strip()
        if not value:return
        cursor=self.editor.textCursor();cursor.movePosition(QTextCursor.End)
        if self.editor.toPlainText():cursor.insertBlock()
        cursor.insertText('☐ '+value);self.todo_input.clear();self.changed();self.manager.flush()

    def toggle_todo(self,item):
        block=self.editor.document().findBlockByNumber(item.data(Qt.UserRole))
        if not block.isValid() or not block.text().startswith(('☐ ','☑ ')):return
        self._toggling_todo=True
        try:
            cursor=QTextCursor(block);cursor.movePosition(QTextCursor.Right,QTextCursor.KeepAnchor);cursor.insertText('☑' if item.checkState()==Qt.Checked else '☐')
        finally:self._toggling_todo=False
        self.changed();self.manager.flush()

    def fit_title(self,*args):
        self.title.ensurePolished()
        limit=max(60,min(round(140*self.ui_factor),round(self.width()*.45)))
        width=max(48,min(limit,self.title.fontMetrics().horizontalAdvance(self.title.text() or '新便签')+12))
        self.title.setFixedWidth(width)
        if not self.title.editing:self.title.setCursorPosition(0)
        self.title.setToolTip((self.title.text() or '便签标题')+' · 双击修改，Enter保存，Esc取消')
    def open_settings(self):
        if self.disposed:return
        self.title.finish_edit();self.collapse_timer.stop();self.expand_timer.stop()
        dialog=NoteOptions(self);dialog.exec_();dialog.deleteLater()
        if not self.disposed and self.row()['auto_hide']:self.collapse_timer.start()
    def format_text(self,kind):
        cursor=self.editor.textCursor();fmt=QTextCharFormat()
        if kind=='bullet':
            if cursor.currentList():
                block=cursor.blockFormat();block.setObjectIndex(-1);cursor.setBlockFormat(block)
            else:
                listing=QTextListFormat();listing.setStyle(QTextListFormat.ListDisc);cursor.createList(listing)
        elif kind=='todo':
            cursor.movePosition(QTextCursor.StartOfBlock);text=cursor.block().text()
            if text.startswith(('☐ ','☑ ')):
                cursor.movePosition(QTextCursor.Right,QTextCursor.KeepAnchor)
                cursor.insertText('☑' if text.startswith('☐') else '☐')
            else:cursor.insertText('☐ ')
        else:
            current=cursor.charFormat()
            if kind=='bold':fmt.setFontWeight(QFont.Normal if current.fontWeight()>=QFont.Bold else QFont.Bold)
            elif kind=='italic':fmt.setFontItalic(not current.fontItalic())
            elif kind=='underline':fmt.setFontUnderline(not current.fontUnderline())
            else:fmt.setFontStrikeOut(not current.fontStrikeOut())
            cursor.mergeCharFormat(fmt);self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setTextCursor(cursor);self.editor.setFocus();self.changed()
    def set_collapsed(self,value):
        if self.disposed or self.row()['collapsed']==value:return
        self.collapse_timer.stop();self.expand_timer.stop()
        if value:self.save_geometry();self._fold_expanded=list(self.geometry().getRect())
        self.manager.update(self.identity,collapsed=value);self.apply_style();self.manager.flush()
    def toggle_collapse(self):self.set_collapsed(not self.row()['collapsed'])
    def collapse_if_outside(self):
        if self.disposed or not self.row()['auto_hide'] or not self.isVisible() or self.row()['collapsed']:return
        if self.drag is not None or self.rect().contains(self.mapFromGlobal(QCursor.pos())):return
        if QApplication.activeModalWidget() or QApplication.activePopupWidget() or (self.isActiveWindow() and (self.editor.hasFocus() or self.title.hasFocus() or self.todo_input.hasFocus() or self.todos.hasFocus())):return
        layout=getattr(self.runtime,'layout',None)
        if layout and (layout.pending or layout.applying):return
        self.set_collapsed(True)
    def expand_if_inside(self):
        if not self.disposed and self.isVisible() and self.row()['auto_hide'] and self.rect().contains(self.mapFromGlobal(QCursor.pos())):self.set_collapsed(False)
    def enterEvent(self,event):
        if hasattr(self,'collapse_timer'):self.collapse_timer.stop()
        if hasattr(self,'expand_timer') and self.row()['auto_hide'] and self.row()['collapsed']:self.expand_timer.start()
        super().enterEvent(event)
    def leaveEvent(self,event):
        if hasattr(self,'expand_timer'):self.expand_timer.stop()
        if hasattr(self,'collapse_timer') and self.row()['auto_hide']:self.collapse_timer.start()
        super().leaveEvent(event)
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.ActivationChange and hasattr(self,'collapse_timer') and not self.disposed and not self.isActiveWindow() and self.row()['auto_hide']:self.collapse_timer.start()
    def hideEvent(self,event):
        for name in ('collapse_timer','expand_timer','refresh_timer'):
            timer=getattr(self,name,None)
            if timer:timer.stop()
        super().hideEvent(event)
    def set_option(self,key,value):
        if key=='style':
            color={'glass':self.dock.cfg.get('theme_color') or '#cfe8fa','paper':'#fff1a8','plain':'#eef1f5'}[value]
            self.manager.update(self.identity,style=value,color=color)
        else:self.manager.update(self.identity,**{key:value})
        self.apply_style();self.manager.flush()
        if key=='auto_hide':
            self.collapse_timer.stop();self.expand_timer.stop()
            if value:self.collapse_timer.start()
    def build_menu(self):
        menu=AlignedMenu(self)
        menu.addAction('便签设置…').triggered.connect(self.open_settings)
        menu.addAction('卡片尺寸与文字…').triggered.connect(lambda:self.runtime.open_card_sizing('note',self.identity))
        menu.addAction('新建便签').triggered.connect(self.manager.new)
        styles=menu.addMenu('外观样式')
        for title,key in STYLES:
            action=styles.addAction(title);action.setCheckable(True);action.setChecked(self.row()['style']==key);action.triggered.connect(lambda checked=False,value=key:self.set_option('style',value))
        colors=menu.addMenu('便签颜色')
        for title,color in COLORS:colors.addAction(title).triggered.connect(lambda checked=False,value=color:self.set_option('color',value))
        for key,title in [('auto_hide','自动收起（鼠标离开后）'),('pinned','置顶显示'),('locked','锁定位置与大小')]:
            action=menu.addAction(title);action.setCheckable(True);action.setChecked(self.row()[key]);action.triggered.connect(lambda checked,k=key:self.set_option(k,checked))
        from fold_options import FoldOptions
        menu.addAction('收起样式…').triggered.connect(lambda:FoldOptions(self).exec_())
        menu.addAction('展开便签' if self.row()['collapsed'] else '收起便签').triggered.connect(self.toggle_collapse)
        menu.addAction('隐藏便签（保留内容）').triggered.connect(lambda:self.manager.update_and_save(self.identity,visible=False))
        menu.addAction('便签管理…').triggered.connect(self.manager.manage)
        menu.addSeparator();menu.addAction('删除便签（可恢复）').triggered.connect(lambda:self.manager.delete(self.identity))
        menu.addAction('永久删除…').triggered.connect(lambda:self.manager.permanent_delete(self.identity,self));return menu
    def show_menu(self):
        menu=self.build_menu();menu.exec_(self.more.mapToGlobal(self.more.rect().bottomLeft()));menu.deleteLater()
        if not self.disposed and self.row()['auto_hide']:self.collapse_timer.start()
    def contextMenuEvent(self,event):
        menu=self.build_menu();menu.exec_(event.globalPos());menu.deleteLater()
        if not self.disposed and self.row()['auto_hide']:self.collapse_timer.start()
    def eventFilter(self,widget,event):
        if widget in (getattr(self,'title',None),getattr(self,'editor',None)) and event.type()==QEvent.FocusOut and hasattr(self,'collapse_timer') and not self.disposed and self.row()['auto_hide']:self.collapse_timer.start()
        if widget is self.handle or (widget is getattr(self,'title',None) and self.title.isReadOnly()):
            if widget is getattr(self,'title',None) and event.type()==QEvent.MouseButtonDblClick:
                self.drag=None;return False
            if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton and not self.row()['locked']:self.collapse_timer.stop();self.expand_timer.stop();self.drag=event.globalPos()-self.pos();return True
            if event.type()==QEvent.MouseMove and self.drag is not None:self.move(event.globalPos()-self.drag);return True
            if event.type()==QEvent.MouseButtonRelease and self.drag is not None:
                self.drag=None;self.save_geometry();self.manager.flush()
                if self.row()['auto_hide']:self.collapse_timer.start()
                return True
            if event.type()==QEvent.MouseButtonDblClick:self.toggle_collapse();return True
        return super().eventFilter(widget,event)
    def save_geometry(self):
        if self.loading or self.disposed:return
        layout=getattr(self.runtime,'layout',None)
        if layout and (layout.pending or layout.applying):return
        row=self.row()
        if row.get('layout') and self.geometry().getRect()==getattr(self,'_saved_geometry',None):return
        offset=getattr(self,'_fold_offset',(0,0)) if row['collapsed'] else (0,0)
        expanded=getattr(self,'_fold_expanded',[self.x(),self.y(),self.width(),self.expanded_height])
        geometry=[self.x()-offset[0],self.y()-offset[1],expanded[2] if row['collapsed'] else self.width(),expanded[3] if row['collapsed'] else self.height()]
        self._fold_expanded=list(geometry)
        self.expanded_height=geometry[3]
        self.manager.update(self.identity,geometry=geometry,layout=capture(geometry,screen_records(),self.ui_factor,self.dock.cfg.get('card_scale',70)/100))
        self._saved_geometry=self.geometry().getRect()
    def reposition(self):
        self.geometry_timer.stop();row=self.row();screens=screen_records();record=row.get('layout',{})
        if not record:
            geometry=row.get('geometry')
            if not geometry:
                screen=QApplication.primaryScreen().availableGeometry();offset=list(self.manager.rows()).index(row)*18
                factor=initial_card_factor(list(screen.getRect()))
                geometry=[screen.left()+40+offset%180,screen.top()+50+offset%180,round(300*factor),round(260*factor)]
                from card_metrics import new_geometry,metrics
                geometry=new_geometry(self.dock.cfg,geometry,screens)
                _,factor,_=metrics(self.dock.cfg,geometry,screens)
                record=capture(geometry,screens,ui_scale=factor,density=self.dock.cfg.get('card_scale',70)/100)
            if not record:record=capture(geometry,screens)
        geometry=project(record,screens,minimum=(160,96),density=self.dock.cfg.get('card_scale',70)/100) or row.get('geometry',[40,50,300,260])
        from card_metrics import metrics
        from screen_layout import choose_screen
        geometry,self.ui_factor,_=metrics(self.dock.cfg,geometry,screens,choose_screen(record,screens))
        self.expanded_height=geometry[3];self._fold_expanded=list(geometry)
        self.loading=True
        self.setMinimumSize(1,1);self.setMaximumSize(16777215,16777215);self.setGeometry(*geometry)
        self.loading=False
    def apply_style(self):
        row=self.row();collapsed=row['collapsed'];self.loading=True
        self.tools.setVisible(not collapsed and not row.get('flipped'));self.pages.setVisible(not collapsed);self.footer.setVisible(not collapsed)
        factor=self.ui_factor;bar=max(30,round(42*factor));small_before=self.height()<max(80,bar+2)
        self.setMinimumSize(max(160,round(230*min(1,factor))),bar if collapsed else max(96,round(150*min(1,factor))));self.setMaximumSize(16777215,16777215)
        if collapsed:self.resize(self.width(),bar)
        elif small_before:self.resize(self.width(),self.expanded_height)
        self.layout_box.setContentsMargins(*(max(5,round(v*factor)) for v in (12,9,12,9)));self.layout_box.setSpacing(max(3,round(6*factor)))
        for widget in [self.flip_button,self.settings_button,self.more,self.collapse_button,self.retry]+list(self.format_buttons.values()):widget.setFixedSize(max(16,round(23*factor)),max(16,round(23*factor)))
        if row['locked']:self.setFixedSize(self.size())
        self.grip.setVisible(not row['locked']);self.collapse_button.setText('▾' if collapsed else '−')
        color=QColor(row['color']);ink='#20252b' if color.lightness()>110 or self.dock.cfg.get('card_design') in ('gradient','paper','minimal') else '#f5f7fa'
        from glass_panel import category_icon
        icon_size=max(12,round(17*factor));self.handle.setFixedSize(icon_size,icon_size)
        self.handle.setPixmap(category_icon('note',note_icon_color(row['color']),icon_size,self.devicePixelRatioF()))
        self.setStyleSheet('QWidget#StickyNote {background:transparent;} QLineEdit,QTextEdit,QLabel,QToolButton {background:transparent;color:'+ink+';border:0;font-family:"Microsoft YaHei UI";font-size:12px;} QLineEdit {font-weight:600;padding:0;min-height:20px;} QTextEdit {padding:3px;selection-background-color:rgba(90,140,180,80);} QToolButton {border-radius:5px;} QToolButton:hover {background:rgba(120,130,150,28);} QLabel {font-size:10px;}')
        from dpi_support import panel_css
        self.setStyleSheet(panel_css(self.styleSheet(),self.ui_factor))
        size=self.text_pixels();self.editor.setStyleSheet('font-size:%dpx;'%size)
        self.editor.viewport().setAutoFillBackground(False);self.todos.viewport().setAutoFillBackground(False)
        self.todos.setStyleSheet('QListWidget {background:transparent;border:0;color:%s;font-size:%dpx;} QListWidget::item {padding:5px 2px;} QListWidget::indicator:unchecked {background:rgba(255,255,255,180);border:1px solid #98a7b4;border-radius:4px;width:14px;height:14px;}'%(ink,size))
        from card_metrics import font_pixels
        self.title.setStyleSheet('font-size:%dpx;padding:0 2px;'%font_pixels(self.dock.cfg,self.ui_factor));self.fit_title()
        self.settings_button.setIcon(QIcon(category_icon('settings',ink,max(12,round(16*factor)),self.devicePixelRatioF())));self.settings_button.setIconSize(self.handle.size())
        font=QFont('Microsoft YaHei UI');font.setPixelSize(size);self.editor.document().setDefaultFont(font)
        palette=self.editor.palette();palette.setColor(QPalette.Text,QColor(ink));palette.setColor(QPalette.Base,QColor(0,0,0,0));self.editor.setPalette(palette)
        from fold_options import note_geometry
        note_geometry(self,collapsed)
        self.setWindowTitle(row['title']+' · 大肥鱼Dock便签');self.layer();self.loading=False;self.update();self.refresh_timer.start()
        if not self.geometry_timer.isActive():self._saved_geometry=self.geometry().getRect()
    def text_pixels(self):
        row=self.row()
        if 'body_font_size' in row:return max(8,min(72,round(row['body_font_size']*self.ui_factor/row.get('body_font_scale',1.0))))
        from card_metrics import font_pixels
        return font_pixels(self.dock.cfg,self.ui_factor)

    def layer(self):
        user=ctypes.windll.user32
        from ctypes import wintypes
        user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        if self.row()['pinned']:user.SetWindowPos(int(self.winId()),-1,0,0,0,0,0x13)
        else:
            user.SetWindowPos(int(self.winId()),-2,0,0,0,0,0x13)
            if not self.dock.preview and not os.environ.get('FISHDOCK_TEST_DESKTOP'):
                user.GetShellWindow.restype=wintypes.HWND;owner=user.GetShellWindow()
                if owner:
                    user.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t];user.SetWindowLongPtrW(int(self.winId()),-8,int(owner))
            user.SetWindowPos(int(self.winId()),1,0,0,0,0,0x13)
    def showEvent(self,event):super().showEvent(event);self.layer();self.refresh_timer.start();self.collapse_timer.start() if self.row()['auto_hide'] else None
    def moveEvent(self,event):
        super().moveEvent(event)
        if not self.loading:self.geometry_timer.start();self.refresh_timer.start()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not self.loading:self.geometry_timer.start();self.refresh_timer.start();self.fit_title()
    def capture_backdrop(self):
        self.backdrop=None
        if self.row()['style']!='glass' or self.runtime.lite or self.dock.preview or not self.isVisible():self.update();return
        from glass_capture import capture_behind,surface_windows
        image=capture_behind(self,surface_windows(self.dock))
        if image is not None:
            ratio=image.devicePixelRatio();self.backdrop=image.scaled(max(1,image.width()//8),max(1,image.height()//8),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).scaled(image.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation);self.backdrop.setDevicePixelRatio(ratio)
        self.update()
    def paintEvent(self,event):
        row=self.row();p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);rect=QRectF(self.rect()).adjusted(1,1,-1,-1);shape=QPainterPath();shape.addRoundedRect(rect,self.height()/2 if row['collapsed'] and __import__('fold_options').settings(self)['style']!='bar' else 14*self.ui_factor,self.height()/2 if row['collapsed'] and __import__('fold_options').settings(self)['style']!='bar' else 14*self.ui_factor);color=QColor(row['color'])
        if row['style']=='glass':
            colors=tint_palette(self.dock.base_theme_colors('light'),row['color'])
            surface=SimpleNamespace(cfg={'glass':True,'clear_background':False,'dock_material':'liquid'},backdrop=self.backdrop,spec_x=self.width()*.5,spec_alpha=.25)
            paint_liquid_glass(surface,p,shape,rect,rect,colors,105,self.dock.merged_grad_stops(colors))
        else:
            p.setClipPath(shape)
            if row['style']=='paper':
                fill=QLinearGradient(0,0,0,self.height());fill.setColorAt(0,color.lighter(108));fill.setColorAt(1,color);p.fillRect(rect,fill)
                p.setPen(QPen(color.darker(118),1));p.drawLine(12,round(43*self.ui_factor),self.width()-12,round(43*self.ui_factor))
            else:p.fillRect(rect,color)
            p.setClipping(False);p.setBrush(Qt.NoBrush);p.setPen(QPen(color.darker(120),1));p.drawPath(shape)
        from card_design import paint_design
        paint_design(p,rect,self.dock.cfg,corner_radius=self.height()/2 if row['collapsed'] and __import__('fold_options').settings(self)['style']!='bar' else 14*self.ui_factor,body_top=rect.bottom() if row['collapsed'] else None,header_separator=not row['collapsed'])
    def closeEvent(self,event):
        if self.disposed or QApplication.instance().isSavingSession():event.accept()
        else:event.ignore();self.manager.update_and_save(self.identity,visible=False)
    def dispose(self):
        self.pages.animation.stop();self.pages.frames=None
        self.disposed=True;self.collapse_timer.stop();self.expand_timer.stop();self.geometry_timer.stop();self.refresh_timer.stop();self.backdrop=None;self.close();self.deleteLater()


class NoteOptions(QDialog):
    def __init__(self,note):
        super().__init__(note,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.note=note;self.manager=note.manager;self.loading=True;row=note.row();self.custom='body_font_size' in row
        self.setWindowTitle('便签设置 · 大肥鱼Dock');self.resize(570,400);self.setMinimumSize(480,340)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'便签设置'));form=QFormLayout();body.addLayout(form)
        self.style=ModernComboBox();self.color=ModernComboBox()
        for title,key in STYLES:self.style.addItem(title,key)
        self.style.setCurrentIndex(self.style.findData(row['style']))
        for title,key in COLORS:self.color.addItem(title,key)
        if self.color.findData(row['color'])<0:self.color.addItem('当前颜色',row['color'])
        self.color.setCurrentIndex(self.color.findData(row['color']))
        form.addRow('外观样式',self.style);form.addRow('主题色',self.color)
        self.body_font=ModernSpinBox();self.body_font.setRange(8,72);self.body_font.setValue(note.text_pixels());self.body_font.setAccessibleName('便签正文字号')
        font_row=QHBoxLayout();font_row.addWidget(self.body_font,1);self.follow_button=button('跟随卡片',self.follow_font);font_row.addWidget(self.follow_button);form.addRow('正文字号（像素）',font_row)
        self.auto_hide=ModernCheckBox('鼠标离开后自动收起');self.auto_hide.setChecked(row['auto_hide']);form.addRow(self.auto_hide)
        flags=QHBoxLayout();self.pinned=ModernCheckBox('置顶显示');self.locked=ModernCheckBox('锁定位置与大小')
        self.pinned.setChecked(row['pinned']);self.locked.setChecked(row['locked']);flags.addWidget(self.pinned);flags.addWidget(self.locked);flags.addStretch();form.addRow(flags)
        body.addWidget(label('正文字号只影响这张便签，标题使用卡片字号。标题双击后编辑，Enter保存、Esc取消。','muted'))
        self.status=label('修改后保存，窗口保持打开。','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('关闭',self.reject));actions.addWidget(button('保存设置',self.commit,'primary'));body.addLayout(actions)
        self.body_font.valueChanged.connect(self.font_changed);self.follow_button.setEnabled(self.custom);self.loading=False;compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,note.dock.cfg)
    def font_changed(self):
        if not self.loading:self.custom=True;self.follow_button.setEnabled(True)
    def follow_font(self):
        from card_metrics import font_pixels
        self.loading=True;self.body_font.setValue(font_pixels(self.note.dock.cfg,self.note.ui_factor));self.loading=False
        self.custom=False;self.follow_button.setEnabled(False)
    def commit(self):
        if self.note.disposed:self.status.setText('便签已关闭。');return False
        if not self.manager.flush():self.status.setText('正文尚未保存，请重试。');return False
        rows=self.manager.rows();row=next((row for row in rows if row['id']==self.note.identity),None)
        if row is None:return False
        row.update(style=self.style.currentData(),color=self.color.currentData(),auto_hide=self.auto_hide.isChecked(),pinned=self.pinned.isChecked(),locked=self.locked.isChecked())
        if self.custom:row.update(body_font_size=self.body_font.value(),body_font_scale=self.note.ui_factor)
        else:row.pop('body_font_size',None);row.pop('body_font_scale',None)
        if not self.manager.persist(sticky_notes=rows):self.status.setText('保存失败，原设置保持不变。');return False
        self.note.apply_style();self.status.setText('已保存，窗口保持打开。');return True


class NotesDialog(QDialog):
    def __init__(self,manager):
        super().__init__(None,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint);self.manager=manager
        self.resize(660,500);self.setMinimumSize(540,400);self.setWindowTitle('便签管理 · 大肥鱼Dock')
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'便签管理'))
        self.query=QLineEdit();self.query.setPlaceholderText('搜索便签标题与内容');body.addWidget(self.query)
        self.tabs=QTabBar();self.tabs.addTab('全部便签');self.tabs.addTab('最近删除');body.addWidget(self.tabs)
        self.list=QListWidget();body.addWidget(self.list,1)
        self.notice=label('输入后自动保存；删除可从最近删除恢复（保留最近32张）。','muted');body.addWidget(self.notice)
        actions=QHBoxLayout();actions.addWidget(button('新建',manager.new));self.open_button=button('打开便签',self.open_selected);actions.addWidget(self.open_button)
        self.remove_button=button('删除',self.remove_selected);actions.addWidget(self.remove_button);self.permanent_button=button('永久删除…',self.permanent_selected);actions.addWidget(self.permanent_button);actions.addStretch();actions.addWidget(button('关闭',self.reject));body.addLayout(actions)
        self.query.textChanged.connect(self.render);self.tabs.currentChanged.connect(self.render);self.list.itemDoubleClicked.connect(self.open_selected);manager.changed.connect(self.render);self.list.currentItemChanged.connect(self.selection_changed);compact_dialog(self);self.render()
    def render(self):
        selected=self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None;self.list.clear();trash=self.tabs.currentIndex()==1
        rows=self.manager.runtime.dock.cfg['notes_trash'] if trash else self.manager.rows();query=self.query.text().strip().casefold()
        for row in rows:
            if query and query not in (row['title']+' '+row['text']).casefold():continue
            item=QListWidgetItem(row['title']+'\n'+row['text'].replace('\n',' ')[:72]);item.setData(Qt.UserRole,row['id']);self.list.addItem(item)
            if row['id']==selected:self.list.setCurrentItem(item)
        self.open_button.setText('恢复便签' if trash else '打开便签');self.selection_changed()
    def selection_changed(self,*args):
        selected=self.list.currentItem() is not None
        self.open_button.setEnabled(selected);self.remove_button.setEnabled(selected and self.tabs.currentIndex()==0);self.permanent_button.setEnabled(selected)
    def open_selected(self,*args):
        item=self.list.currentItem()
        if item:
            if self.tabs.currentIndex()==1:self.manager.restore(item.data(Qt.UserRole))
            else:self.manager.open(item.data(Qt.UserRole))
    def remove_selected(self):
        item=self.list.currentItem()
        if item:self.manager.delete(item.data(Qt.UserRole))
    def permanent_selected(self):
        item=self.list.currentItem()
        if item:self.manager.permanent_delete(item.data(Qt.UserRole),self)


class NotesManager(QObject):
    changed=pyqtSignal()
    def __init__(self,runtime):
        super().__init__(runtime.dock);self.runtime=runtime;self.windows={};self.pending={};self.dialog=None;self.closed=False;self.message=''
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(600);self.timer.timeout.connect(self.flush)
        self.recovery=Path(runtime.api.CONFIG_DIR)/'notes-recovery.json'
        if self.recovery.exists():
            try:
                if self.recovery.stat().st_size>4*1024*1024:raise ValueError('recovery too large')
                data=json.loads(self.recovery.read_text(encoding='utf-8'))
                if data.get('project')!='BigFishDockpro':raise ValueError('wrong recovery project')
                for row in normalize_notes(data['notes'],strict=True):self.pending[row['id']]=row
                if self.flush():self.recovery.unlink(missing_ok=True)
            except (OSError,ValueError,KeyError):self.message='便签恢复记录无法读取，已保留原文件。'
    def rows(self):
        rows={row['id']:copy.deepcopy(row) for row in self.runtime.dock.cfg.get('sticky_notes',[])};rows.update(copy.deepcopy(self.pending));return list(rows.values())
    def row(self,identity):return next(row for row in self.rows() if row['id']==identity)
    def update(self,identity,**changes):
        row=self.row(identity);row.update(changes);row['updated']=datetime.datetime.now(datetime.timezone.utc).isoformat();self.pending[identity]=row;self.message='尚未保存';self.timer.start();self.status()
    def status(self):
        for window in self.windows.values():window.status.setText(self.message)
    def persist(self,**changes):
        candidate=dict(self.runtime.dock.cfg,**copy.deepcopy(changes))
        try:
            normalize_notes(candidate['sticky_notes'],strict=True)
            if len(json.dumps([candidate['sticky_notes'],candidate['notes_trash']],ensure_ascii=False).encode('utf-8'))>4*1024*1024:raise ValueError('便签总量超过4 MiB，请减少内容后重试。')
            if self.runtime.api.save_config(candidate) is False:raise OSError('configuration write failed')
        except (OSError,ValueError) as error:
            self.message='保存失败，内容仍在窗口中；点击 ↻ 重试。';self.runtime.api.log('便签保存失败: '+str(error));self.status();return False
        self.runtime.dock.cfg.update({key:candidate[key] for key in changes});self.message='已保存到本机';self.status();self.changed.emit();return True
    def flush(self):
        self.timer.stop()
        if not self.pending:return True
        rows=self.rows()
        if not self.persist(sticky_notes=rows):return False
        self.pending.clear();return True
    def new(self):
        if len(self.rows())>=64:self.message='最多保留64张便签。';self.status();return None
        cfg=self.runtime.dock.cfg;style=cfg['note_style'];identity=uuid.uuid4().hex
        row={'id':identity,'title':'新便签','html':'','text':'','style':style,'color':{'glass':cfg.get('theme_color') or '#cfe8fa','paper':'#fff1a8','plain':'#eef1f5'}[style],'pinned':False,'locked':False,'collapsed':False,'auto_hide':False,'visible':True,'updated':'','font_size':12,'font_scale':1.0}
        self.pending[identity]=row
        if not self.persist(sticky_notes=self.rows(),notes_enabled=True,notes_visible=True):return None
        self.pending.clear();self.sync();window=self.windows[identity];window.raise_();window.editor.setFocus();self.changed.emit()
        from usage_stats import record
        record(self.runtime,'note_new');return identity
    def update_and_save(self,identity,**changes):
        self.update(identity,**changes)
        if self.flush():self.sync();return True
        return False
    def delete(self,identity):
        if not self.flush():return False
        rows=self.rows();row=self.row(identity);trash=[old for old in self.runtime.dock.cfg['notes_trash'] if old['id']!=identity]+[row]
        if self.persist(sticky_notes=[old for old in rows if old['id']!=identity],notes_trash=trash[-32:]):self.sync();return True
        return False
    def permanent_delete(self,identity,parent=None):
        if self.closed:return False
        row=next((row for row in self.rows()+self.runtime.dock.cfg['notes_trash'] if row['id']==identity),None)
        if row is None:return False
        box=QMessageBox(QMessageBox.Warning,'永久删除便签','确定永久删除“'+row['title']+'”？\n删除后无法从“最近删除”恢复。',parent=parent)
        remove=box.addButton('永久删除',QMessageBox.DestructiveRole);cancel=box.addButton('取消',QMessageBox.RejectRole)
        box.setDefaultButton(cancel);box.setEscapeButton(cancel);box.exec_()
        if box.clickedButton() is not remove:return False
        if not self.flush():return False
        rows=[row for row in self.rows() if row['id']!=identity]
        trash=[row for row in self.runtime.dock.cfg['notes_trash'] if row['id']!=identity]
        if not self.persist(sticky_notes=rows,notes_trash=trash):return False
        self.sync();return True

    def restore(self,identity):
        if not self.flush() or len(self.rows())>=64:return False
        trash=self.runtime.dock.cfg['notes_trash'];row=copy.deepcopy(next(row for row in trash if row['id']==identity));row['visible']=True
        if self.persist(sticky_notes=self.rows()+[row],notes_trash=[old for old in trash if old['id']!=identity],notes_enabled=True,notes_visible=True):self.sync();return True
        return False
    def open(self,identity):
        if self.persist(notes_enabled=True,notes_visible=True):
            self.update_and_save(identity,visible=True);window=self.windows.get(identity)
            if window:window.raise_();window.editor.setFocus()
    def toggle(self):
        cfg=self.runtime.dock.cfg
        changes={'notes_visible':not cfg['notes_visible']} if cfg['notes_enabled'] else {'notes_enabled':True,'notes_visible':True}
        if self.persist(**changes):self.sync()
    def sync(self):
        if self.closed:return
        rows={row['id']:row for row in self.rows()};cfg=self.runtime.dock.cfg
        for identity in set(self.windows)-set(rows):self.windows.pop(identity).dispose()
        for identity,row in rows.items():
            if identity not in self.windows:self.windows[identity]=NoteWindow(self,identity)
            window=self.windows[identity];window.apply_style()
            window.setVisible(cfg['notes_enabled'] and cfg['notes_visible'] and row['visible'] and not self.runtime.game_active)
        self.status()
    def reload(self):
        for window in self.windows.values():window.dispose()
        self.windows.clear();self.pending.clear();self.sync()
    def reposition(self):
        for window in self.windows.values():window.reposition();window.apply_style()
    def set_lite(self):
        if self.runtime.lite:
            for window in self.windows.values():window.backdrop=None;window.refresh_timer.stop();window.update()
    def manage(self):
        if self.dialog is None:self.dialog=NotesDialog(self)
        self.dialog.render();self.dialog.show();self.dialog.raise_();self.dialog.activateWindow()
    def backup(self):
        try:
            self.recovery.parent.mkdir(parents=True,exist_ok=True);temporary=self.recovery.with_suffix('.tmp')
            temporary.write_text(json.dumps({'project':'BigFishDockpro','notes':self.rows()},ensure_ascii=False),encoding='utf-8');os.replace(temporary,self.recovery);return True
        except OSError:return False
    def close(self):
        if self.closed:return
        for window in self.windows.values():window.title.finish_edit();window.save_geometry()
        if not self.flush() and not self.backup():self.runtime.api.log('便签退出保存及恢复备份失败，请保留编辑内容。')
        self.closed=True;self.timer.stop()
        if self.dialog:self.dialog.close()
        for window in self.windows.values():window.dispose()
        self.windows.clear()
