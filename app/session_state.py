"""One durable session snapshot, without per-window disk writes or shutdown dialogs."""
import copy


def save_state(runtime):
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);notes=runtime.notes
    try:
        for window in notes.windows.values():window.title.finish_edit();window.save_geometry()
        notes.timer.stop()
        runtime.panels.save_visible_geometry(persist=False)
        runtime.clock.save_geometry(persist=False);runtime.calendar.save_geometry(persist=False)
        cfg.update(sticky_notes=notes.rows(),runtime_lite=runtime.lite)
        if runtime.api.save_config(cfg) is False:raise OSError('configuration write failed')
    except (OSError,ValueError,TypeError,RuntimeError) as error:
        cfg.clear();cfg.update(before)
        if not notes.backup():runtime.api.log('结束会话时便签恢复备份失败，请保留数据目录。')
        runtime.api.log('结束会话时保存状态失败：'+str(error));return False
    notes.pending.clear();notes.message='已保存到本机'
    try:notes.recovery.unlink(missing_ok=True)
    except OSError:runtime.api.log('便签已保存，旧恢复记录暂未清除。')
    return True
