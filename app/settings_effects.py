"""Apply only the settings that actually changed; keep unrelated widgets/caches."""
from PyQt5.QtWidgets import QApplication

DOCK_LAYOUT={'icon_size','items','position','custom_bottom','bottom_margin','show_name','sep_split',
             'dock_clock','dock_quick_settings','dock_add_button','dock_reflections'}
DOCK_GLASS={'theme','dock_material','theme_color','transparency','glass','clear_background','blur_px','blur_mode','dock_highlight'}


def apply_changes(tray,api,previous):
    cfg=tray.cfg;changed={key for key in set(previous)|set(cfg) if previous.get(key)!=cfg.get(key)}
    dock=tray.dock
    if not changed:return changed
    if 'lang' in changed:api.set_lang(cfg['lang'])
    if 'theme' in changed:
        dock._sys_light=api.system_is_light()
        from ui_style import apply_theme
        apply_theme(QApplication.instance(),dock.is_light())
    if changed&{'icon_size','items','dock_clock','dock_quick_settings','dock_add_button'}:dock.reload()
    elif changed&DOCK_LAYOUT:
        if 'dock_reflections' in changed:dock.extras.prepare(dock.items)
        dock.refresh_geometry()
    elif changed&DOCK_GLASS:dock.start_backdrop();dock.update()
    elif 'magnify' in changed:dock._recalc();dock._kick()
    else:dock.update()
    if 'layer' in changed:dock.apply_layer()
    if 'running_dots' in changed:
        if cfg['running_dots'] and not dock.preview and not dock.lite_mode:dock.proc_timer.start(8000);dock.refresh_running()
        else:dock.proc_timer.stop();dock.running.clear();dock.update()
    runtime=getattr(tray,'runtime',None)
    if runtime:runtime.apply_settings(changed)
    if hasattr(dock,'extras'):dock.extras.sync_clock()
    return changed


def save_changes(tray,api,changes):
    previous=dict(tray.cfg);candidate=dict(previous,**changes)
    if candidate==previous:return True
    if api.save_config(candidate) is False:return False
    tray.cfg.update(candidate);apply_changes(tray,api,previous)
    dialog=getattr(tray,'settings_dialog',None)
    if dialog and dialog.isVisible():
        # A quick action must not discard other edits pending in the main page.
        from PyQt5.QtWidgets import QComboBox,QSpinBox,QLineEdit
        for key in changes:
            field=dialog.fields.get(key)
            if not field:continue
            value=candidate[key]
            if isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
            elif isinstance(field,QSpinBox):field.setValue(100-value if key=='transparency' else value)
            elif isinstance(field,QLineEdit):field.setText(value)
            else:field.setChecked(value)
            if key in dialog._runtime_switch_baseline:dialog._runtime_switch_baseline[key]=value
    return True
