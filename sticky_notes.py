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
from PyQt5.QtGui import QPainter,QPainterPath,QColor,QPen,QLinearGradient,QFont,QTextCharFormat,QTextListFormat,QTextCursor,QTextDocument,QPalette
from PyQt5.QtWidgets import QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QTextEdit,QToolButton,QLabel,QSizeGrip,QApplication,QListWidget,QListWidgetItem,QTabBar,QMessageBox,QShortcut
from PyQt5.QtGui import QKeySequence
from ui_style import AlignedMenu,button,label,SettingsHeader,compact_dialog
from sticky_notes_store import STYLES,COLORS,normalize_notes,clean_editor_html
from screen_layout import capture,project,screen_records
from liquid_glass import paint_liquid_glass,tint_palette


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
            cursor.movePosition(QTextCursor.StartOfBlock);self.setTextCursor(cursor);self.parent().format_text('todo')
    def insertFromMimeData(self,source):
        if source.hasText():self.insertPlainText(source.text())


class NoteWindow(QWidget):
    def __init__(self,manager,identity):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint)
        self.manager,self.runtime,self.dock=manager,manager.runtime,manager.runtime.dock
        self.identity=identity;self.loading=True;self.disposed=False;self.drag=None;self.backdrop=None;self.ui_factor=1.0;self.expanded_height=260
        self.setObjectName('StickyNote');self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(230,150)
        self.layout_box=QVBoxLayout(self);self.layout_box.setContentsMargins(12,9,12,9);self.layout_box.setSpacing(6)
        header=QHBoxLayout();header.setSpacing(4)
        self.handle=QLabel('⋮⋮');self.handle.setToolTip('拖动便签');self.handle.installEventFilter(self);header.addWidget(self.handle)
        self.title=QLineEdit();self.title.setMaxLength(60);self.title.setPlaceholderText('便签标题');header.addWidget(self.title,1)
        self.more=self.tool('⋯','便签菜单',self.show_menu);header.addWidget(self.more)
        self.collapse_button=self.tool('−','收起 / 展开',self.toggle_collapse);header.addWidget(self.collapse_button)
        self.layout_box.addLayout(header)
        self.tools=QWidget();toolbar=QHBoxLayout(self.tools);toolbar.setContentsMargins(0,0,0,0);toolbar.setSpacing(3)
        self.format_buttons={}
        for text,tip,key in [('B','加粗 Ctrl+B','bold'),('I','斜体 Ctrl+I','italic'),('U','下划线 Ctrl+U','underline'),('S','删除线','strike'),('•','项目符号','bullet'),('☐','切换待办完成状态','todo')]:
            widget=self.tool(text,tip,lambda checked=False,k=key:self.format_text(k));toolbar.addWidget(widget);self.format_buttons[key]=widget
        toolbar.addStretch();self.layout_box.addWidget(self.tools)
        self.editor=NoteEditor(self);self.layout_box.addWidget(self.editor,1)
        footer=QHBoxLayout();self.status=QLabel('');self.status.setWordWrap(True);footer.addWidget(self.status,1)
        self.retry=self.tool('↻','立即保存 / 重试',self.manager.flush);footer.addWidget(self.retry)
        self.grip=QSizeGrip(self);self.grip.setFixedSize(12,12);footer.addWidget(self.grip,0,Qt.AlignBottom)
        self.footer=QWidget();self.footer.setLayout(footer);self.layout_box.addWidget(self.footer)
        self.title.textEdited.connect(self.changed);self.editor.textChanged.connect(self.changed)
        self.geometry_timer=QTimer(self);self.geometry_timer.setSingleShot(True);self.geometry_timer.setInterval(250);self.geometry_timer.timeout.connect(self.save_geometry)
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True);self.refresh_timer.setInterval(160);self.refresh_timer.timeout.connect(self.capture_backdrop)
        for keys,kind in [('Ctrl+B','bold'),('Ctrl+I','italic'),('Ctrl+U','underline'),('Ctrl+Shift+L','bullet')]:
            shortcut=QShortcut(QKeySequence(keys),self);shortcut.activated.connect(lambda k=kind:self.format_text(k))
        shortcut=QShortcut(QKeySequence('Ctrl+S'),self);shortcut.activated.connect(manager.flush)
        row=self.row();self.title.setText(row['title']);self.editor.setHtml(row['html'])
        self.resize(300,260);self.reposition();self.apply_style();self.loading=False

    def tool(self,text,tip,callback):
        widget=QToolButton(self);widget.setText(text);widget.setToolTip(tip);widget.setAccessibleName(tip);widget.setFixedSize(23,23);widget.clicked.connect(callback);return widget
    def row(self):return self.manager.row(self.identity)
    def changed(self):
        if self.loading:return
        text=self.editor.toPlainText()
        self.manager.update(self.identity,title=self.title.text().strip() or '新便签',html=clean_editor_html(self.editor.toHtml()),text=text)
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
    def toggle_collapse(self):
        if not self.row()['collapsed']:self.save_geometry()
        self.manager.update(self.identity,collapsed=not self.row()['collapsed']);self.apply_style();self.manager.flush()
    def set_option(self,key,value):
        if key=='style':
            color={'glass':self.dock.cfg.get('theme_color') or '#cfe8fa','paper':'#fff1a8','plain':'#eef1f5'}[value]
            self.manager.update(self.identity,style=value,color=color)
        else:self.manager.update(self.identity,**{key:value})
        self.apply_style();self.manager.flush()
    def build_menu(self):
        menu=AlignedMenu(self);menu.addAction('新建便签').triggered.connect(self.manager.new)
        styles=menu.addMenu('外观样式')
        for title,key in STYLES:
            action=styles.addAction(title);action.setCheckable(True);action.setChecked(self.row()['style']==key);action.triggered.connect(lambda checked=False,value=key:self.set_option('style',value))
        colors=menu.addMenu('便签颜色')
        for title,color in COLORS:colors.addAction(title).triggered.connect(lambda checked=False,value=color:self.set_option('color',value))
        for key,title in [('pinned','置顶显示'),('locked','锁定位置与大小')]:
            action=menu.addAction(title);action.setCheckable(True);action.setChecked(self.row()[key]);action.triggered.connect(lambda checked,k=key:self.set_option(k,checked))
        menu.addAction('展开便签' if self.row()['collapsed'] else '收起便签').triggered.connect(self.toggle_collapse)
        menu.addAction('隐藏便签（保留内容）').triggered.connect(lambda:self.manager.update_and_save(self.identity,visible=False))
        menu.addAction('便签管理…').triggered.connect(self.manager.manage)
        menu.addSeparator();menu.addAction('删除便签（可恢复）').triggered.connect(lambda:self.manager.delete(self.identity));return menu
    def show_menu(self):
        menu=self.build_menu();menu.exec_(self.more.mapToGlobal(self.more.rect().bottomLeft()));menu.deleteLater()
    def contextMenuEvent(self,event):
        menu=self.build_menu();menu.exec_(event.globalPos());menu.deleteLater()
    def eventFilter(self,widget,event):
        if widget is self.handle:
            if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton and not self.row()['locked']:self.drag=event.globalPos()-self.pos();return True
            if event.type()==QEvent.MouseMove and self.drag is not None:self.move(event.globalPos()-self.drag);return True
            if event.type()==QEvent.MouseButtonRelease and self.drag is not None:self.drag=None;self.save_geometry();self.manager.flush();return True
            if event.type()==QEvent.MouseButtonDblClick:self.toggle_collapse();return True
        return super().eventFilter(widget,event)
    def save_geometry(self):
        if self.loading or self.disposed:return
        row=self.row();geometry=[self.x(),self.y(),self.width(),self.expanded_height if row['collapsed'] else self.height()]
        self.expanded_height=geometry[3]
        self.manager.update(self.identity,geometry=geometry,layout=capture(geometry,screen_records(),self.ui_factor))
    def reposition(self):
        row=self.row();geometry=project(row.get('layout',{}),screen_records(),minimum=(160,96)) or row.get('geometry')
        if not geometry:
            screen=QApplication.primaryScreen().availableGeometry();offset=list(self.manager.rows()).index(row)*18
            geometry=[screen.left()+40+offset%180,screen.top()+50+offset%180,300,260]
        record=row.get('layout',{})
        self.ui_factor=geometry[2]/record['rect'][2]*record.get('ui_scale',1.0) if record else 1.0
        self.expanded_height=geometry[3]
        self.loading=True
        self.setMinimumSize(1,1);self.setMaximumSize(16777215,16777215);self.setGeometry(*geometry)
        self.loading=False
    def apply_style(self):
        row=self.row();collapsed=row['collapsed'];self.loading=True
        self.tools.setVisible(not collapsed);self.editor.setVisible(not collapsed);self.footer.setVisible(not collapsed)
        factor=self.ui_factor;bar=max(30,round(42*factor));small_before=self.height()<max(80,bar+2)
        self.setMinimumSize(max(160,round(230*min(1,factor))),bar if collapsed else max(96,round(150*min(1,factor))));self.setMaximumSize(16777215,16777215)
        if collapsed:self.resize(self.width(),bar)
        elif small_before:self.resize(self.width(),self.expanded_height)
        self.layout_box.setContentsMargins(*(max(5,round(v*factor)) for v in (12,9,12,9)));self.layout_box.setSpacing(max(3,round(6*factor)))
        for widget in [self.more,self.collapse_button,self.retry]+list(self.format_buttons.values()):widget.setFixedSize(max(16,round(23*factor)),max(16,round(23*factor)))
        if row['locked']:self.setFixedSize(self.size())
        self.grip.setVisible(not row['locked']);self.collapse_button.setText('▾' if collapsed else '−')
        color=QColor(row['color']);ink='#20252b' if color.lightness()>110 else '#f5f7fa'
        self.setStyleSheet('QWidget#StickyNote {background:transparent;} QLineEdit,QTextEdit,QLabel,QToolButton {background:transparent;color:'+ink+';border:0;font-family:"Microsoft YaHei UI";font-size:12px;} QLineEdit {font-weight:600;padding:0;min-height:20px;} QTextEdit {padding:3px;selection-background-color:rgba(90,140,180,80);} QToolButton {border-radius:5px;} QToolButton:hover {background:rgba(120,130,150,28);} QLabel {font-size:10px;}')
        from dpi_support import panel_css
        self.setStyleSheet(panel_css(self.styleSheet(),self.ui_factor))
        size=max(8,round(12*self.ui_factor));self.editor.setStyleSheet('font-size:%dpx;'%size)
        font=QFont('Microsoft YaHei UI');font.setPixelSize(size);self.editor.document().setDefaultFont(font)
        palette=self.editor.palette();palette.setColor(QPalette.Text,QColor(ink));palette.setColor(QPalette.Base,QColor(0,0,0,0));self.editor.setPalette(palette)
        self.setWindowTitle(row['title']+' · 大肥鱼Dock便签');self.layer();self.loading=False;self.update();self.refresh_timer.start()
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
    def showEvent(self,event):super().showEvent(event);self.layer();self.refresh_timer.start()
    def moveEvent(self,event):
        super().moveEvent(event)
        if not self.loading:self.geometry_timer.start();self.refresh_timer.start()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not self.loading:self.geometry_timer.start();self.refresh_timer.start()
    def capture_backdrop(self):
        self.backdrop=None
        if self.row()['style']!='glass' or self.runtime.lite or self.dock.preview or not self.isVisible():self.update();return
        user=ctypes.windll.user32;excluded=[]
        from ctypes import wintypes
        user.SetWindowDisplayAffinity.argtypes=[wintypes.HWND,wintypes.DWORD]
        try:
            windows=[self.dock]+list(self.manager.windows.values())+list(self.runtime.panels.windows.values())
            for window in windows:
                if window.isVisible() and user.SetWindowDisplayAffinity(int(window.winId()),0x11):excluded.append(int(window.winId()))
            if int(self.winId()) not in excluded:return
            screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen();rect=self.frameGeometry()
            if screen.geometry().contains(rect):
                image=screen.grabWindow(0,rect.x()-screen.geometry().x(),rect.y()-screen.geometry().y(),rect.width(),rect.height())
                if not image.isNull():
                    ratio=image.devicePixelRatio();self.backdrop=image.scaled(max(1,image.width()//8),max(1,image.height()//8),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).scaled(image.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation);self.backdrop.setDevicePixelRatio(ratio)
        finally:
            for hwnd in excluded:user.SetWindowDisplayAffinity(hwnd,0)
        self.update()
    def paintEvent(self,event):
        row=self.row();p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);rect=QRectF(self.rect()).adjusted(1,1,-1,-1);shape=QPainterPath();shape.addRoundedRect(rect,14*self.ui_factor,14*self.ui_factor);color=QColor(row['color'])
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
    def closeEvent(self,event):
        if self.disposed:event.accept()
        else:event.ignore();self.manager.update_and_save(self.identity,visible=False)
    def dispose(self):
        self.disposed=True;self.geometry_timer.stop();self.refresh_timer.stop();self.backdrop=None;self.close();self.deleteLater()


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
        self.remove_button=button('删除',self.remove_selected);actions.addWidget(self.remove_button);actions.addStretch();actions.addWidget(button('关闭',self.reject));body.addLayout(actions)
        self.query.textChanged.connect(self.render);self.tabs.currentChanged.connect(self.render);self.list.itemDoubleClicked.connect(self.open_selected);manager.changed.connect(self.render);compact_dialog(self);self.render()
    def render(self):
        selected=self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None;self.list.clear();trash=self.tabs.currentIndex()==1
        rows=self.manager.runtime.dock.cfg['notes_trash'] if trash else self.manager.rows();query=self.query.text().strip().casefold()
        for row in rows:
            if query and query not in (row['title']+' '+row['text']).casefold():continue
            item=QListWidgetItem(row['title']+'\n'+row['text'].replace('\n',' ')[:72]);item.setData(Qt.UserRole,row['id']);self.list.addItem(item)
            if row['id']==selected:self.list.setCurrentItem(item)
        self.open_button.setText('恢复便签' if trash else '打开便签');self.remove_button.setEnabled(not trash)
    def open_selected(self,*args):
        item=self.list.currentItem()
        if item:
            if self.tabs.currentIndex()==1:self.manager.restore(item.data(Qt.UserRole))
            else:self.manager.open(item.data(Qt.UserRole))
    def remove_selected(self):
        item=self.list.currentItem()
        if item:self.manager.delete(item.data(Qt.UserRole))


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
        row={'id':identity,'title':'新便签','html':'','text':'','style':style,'color':{'glass':cfg.get('theme_color') or '#cfe8fa','paper':'#fff1a8','plain':'#eef1f5'}[style],'pinned':False,'locked':False,'collapsed':False,'visible':True,'updated':''}
        self.pending[identity]=row
        if not self.persist(sticky_notes=self.rows(),notes_enabled=True,notes_visible=True):return None
        self.pending.clear();self.sync();window=self.windows[identity];window.raise_();window.editor.setFocus();self.changed.emit();return identity
    def update_and_save(self,identity,**changes):
        self.update(identity,**changes)
        if self.flush():self.sync();return True
        return False
    def delete(self,identity):
        if not self.flush():return False
        rows=self.rows();row=self.row(identity);trash=[old for old in self.runtime.dock.cfg['notes_trash'] if old['id']!=identity]+[row]
        if self.persist(sticky_notes=[old for old in rows if old['id']!=identity],notes_trash=trash[-32:]):self.sync();return True
        return False
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
        if self.persist(notes_visible=not self.runtime.dock.cfg['notes_visible']):self.sync()
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
        for window in self.windows.values():window.save_geometry()
        if not self.flush() and not self.backup():self.runtime.api.log('便签退出保存及恢复备份失败，请保留编辑内容。')
        self.closed=True;self.timer.stop()
        if self.dialog:self.dialog.close()
        for window in self.windows.values():window.dispose()
        self.windows.clear()
