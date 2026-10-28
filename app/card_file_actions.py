"""File operations requested by the user; card references follow successful renames."""
import copy
import os
import re
from pathlib import Path
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QInputDialog, QMessageBox
from app_catalog import path_key


def rename_file(panel,paths=None):
    paths=list(paths if paths is not None else panel.selected_paths())
    if len(paths)!=1:panel.notice.setText('请选择一个文件或文件夹重命名。');return False
    old=os.path.abspath(paths[0]);panel.collapse_timer.stop()
    try:
        name,accepted=QInputDialog.getText(panel,'重命名','文件或文件夹名称：',text=os.path.basename(old))
        if not accepted:return False
        if name==os.path.basename(old):return False
        if (not name or name in ('.','..') or len(name)>255 or name[-1] in ' .' or
            re.search(r'[\\/:*?"<>|\x00-\x1f]',name) or
            re.match(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)',name,re.I)):
            raise ValueError('名称无效，请勿使用路径、保留名称或特殊字符。')
        new=os.path.join(os.path.dirname(old),name)
        if path_key(old)!=path_key(new) and os.path.lexists(new):raise FileExistsError('同名文件或文件夹已存在，请更换名称。')
        before=os.stat(old,follow_symlinks=False)
        manager=panel.manager;changes={}
        for field in ('desktop_entries','desktop_excluded','desktop_panels'):changes[field]=copy.deepcopy(manager.cfg[field])
        def update_rows(rows):
            for row in rows:
                if path_key(row['path'])==path_key(old):row.update(path=new,name=name)
        def update_keys(keys):return list(dict.fromkeys(path_key(new) if path_key(key)==path_key(old) else key for key in keys))
        update_rows(changes['desktop_entries']);changes['desktop_excluded']=update_keys(changes['desktop_excluded'])
        for model in changes['desktop_panels']:
            for field in ('pinned_paths','excluded'):
                if field in model:model[field]=update_keys(model[field])
        os.rename(old,new)  # Windows rejects collisions, including races after the preflight.
        try:
            if not manager.commit(**changes):raise OSError('收纳设置保存失败')
        except Exception as error:
            try:
                current=os.stat(new,follow_symlinks=False)
                if (current.st_dev,current.st_ino)!=(before.st_dev,before.st_ino):raise OSError('文件身份已变化')
                if path_key(old)!=path_key(new) and os.path.lexists(old):raise OSError('原名称已被占用')
                os.rename(new,old)
            except OSError as rollback:
                raise OSError('文件已改名为 %s，但收纳设置保存失败，文件名恢复失败：%s。请重新拖入。'%(new,rollback)) from error
            raise OSError('收纳设置保存失败，文件名已恢复。') from error
        update_rows(manager.scanned_rows)
        manager.status('');manager.sync_windows();manager.schedule_scan();panel.notice.setText('已重命名，相关卡片引用已更新。')
        return True
    except (OSError,ValueError) as error:
        panel.notice.setText(str(error));return False
    finally:
        if not panel.disposed and panel.option('auto_hide'):panel.collapse_timer.start()


def prune_deleted_references(manager,paths):
    if manager.closed:return
    # Only paths explicitly submitted to Delete; cancellation keeps every reference.
    missing={path_key(path) for path in paths if not os.path.lexists(path) and os.path.isdir(os.path.dirname(path))}
    if not missing:return
    entries=[row for row in manager.cfg['desktop_entries'] if path_key(row['path']) not in missing]
    if entries!=manager.cfg['desktop_entries'] and manager.commit(desktop_entries=entries):manager.sync_windows()


def shell_action(panel,verb):
    paths=panel.selected_paths()
    if not paths:return False
    panel.collapse_timer.stop();menu=None
    try:
        if verb=='delete' and QMessageBox.question(panel,'删除文件','确定删除所选 %d 项原文件？此操作会影响磁盘中的实际文件。'%len(paths),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return False
        from native_file_menu import NativeFileMenu
        menu=NativeFileMenu(int(panel.winId()),paths);panel._active_file_menu=menu
        result=menu.invoke_verb(verb)
        if result=='shell':
            panel.manager.schedule_scan()
            if verb=='delete':
                manager=panel.manager
                prune_deleted_references(manager,paths)
                for delay in (800,2500):QTimer.singleShot(delay,lambda m=manager,p=tuple(paths):prune_deleted_references(m,p))
        return result=='shell'
    except (OSError,ValueError) as error:
        panel.notice.setText(str(error));return False
    finally:
        panel._active_file_menu=None
        if menu:menu.close()
        if not panel.disposed and panel.option('auto_hide'):panel.collapse_timer.start()
