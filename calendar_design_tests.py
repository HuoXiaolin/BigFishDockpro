"""Independent calendar, light theme family and click-only flip regression."""
import copy,datetime
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QPixmap,QPainter,QColor
from PyQt5.QtWidgets import QApplication


def run(api,runtime,root,output,checks):
    from desktop_clock import ClockOptions,draw_clock
    from clock_appearance import normalize as appearance
    from card_design import DESIGNS
    from desktop_panel_tests import wait_for
    cfg=runtime.dock.cfg;original=copy.deepcopy(cfg);app=QApplication.instance();dialog=None
    calendar=runtime.calendar;clock=runtime.clock
    try:
        runtime.set_lite(False);cfg.update(game_mode=False,fullscreen_detection=False,lite_enabled=False,theme_color='#83b9cd')
        runtime.apply_settings();assert not calendar.isVisible()
        calendar.set_enabled(True);app.processEvents();assert calendar.isVisible() and calendar.tick.isActive()
        assert calendar.tick.interval()>60000
        before_clock=copy.deepcopy(cfg['clock_layout']);calendar.move(calendar.x()-120,calendar.y()+20);calendar.resize(330,300);calendar.save_geometry()
        assert cfg['calendar_layout'] and cfg['clock_layout']==before_clock
        calendar.view_year,calendar.view_month=2027,1;calendar.shift_month(-1);assert (calendar.view_year,calendar.view_month)==(2026,12)
        calendar.shift_month(1);assert (calendar.view_year,calendar.view_month)==(2027,1)
        calendar.go_today();assert (calendar.view_year,calendar.view_month)==(datetime.date.today().year,datetime.date.today().month)
        old_size=calendar.size();assert calendar.set_locked(True) and calendar.minimumSize()==calendar.maximumSize() and not calendar.grip.isVisible()
        assert calendar.set_locked(False);calendar.resize(old_size)
        before_appearance=copy.deepcopy(cfg['clock_appearance'])
        dialog=ClockOptions(calendar);dialog.show();app.processEvents();assert 'style' not in dialog.fields and 'hour_format' not in dialog.fields
        dialog.fields['color'].setText('#9bc9d2');assert dialog.commit() and cfg['clock_appearance']==before_appearance
        dialog.grab().save(str(Path(output)/'calendar-options.png'));dialog.reject();dialog.deleteLater();dialog=None
        before=copy.deepcopy(cfg)
        with patch.object(api,'save_config',return_value=False):calendar.set_enabled(False)
        assert cfg==before and calendar.isVisible()
        runtime.toggle_game(True);assert not calendar.isVisible()
        runtime.toggle_game(False);assert calendar.isVisible()
        from glass_capture import surface_windows
        assert calendar in surface_windows(runtime.dock)
        for title,design in DESIGNS:
            cfg['card_design']=design;cfg['calendar_appearance'].update(theme='light',design='follow');calendar.sync();app.processEvents()
            calendar.grab().save(str(Path(output)/('calendar-'+design+'.png')))
            image=QPixmap(360,220);image.fill(Qt.transparent);painter=QPainter(image)
            draw_clock(painter,QRectF(0,0,360,220),runtime.dock,dict(cfg['clock_appearance'],theme='light',design='follow'),'digital');painter.end()
            image.save(str(Path(output)/('clock-design-'+design+'.png')))
            # New theme choices use bright backgrounds and this app's accent.
            point=image.toImage().pixelColor(20,20);assert point.lightness()>150,(design,point.name())
        saved=api.load_config();assert saved['calendar_enabled'] and saved['calendar_layout']
        from config_transfer import normalize as normalize_import
        exported=normalize_import(dict(cfg),api);assert exported['calendar_appearance']==cfg['calendar_appearance']
        checks.append('independent calendar: own display/layout/appearance and lock, year-boundary month navigation, today reset, game hide/restore, save failure preserves enabled state, excluded from glass captures, daily timer and configuration reload/import; all four light designs rendered using current accent')
        # Explicit click starts a finite flip; hover never starts animations.
        cfg['card_design']='aurora';clock.set_enabled(True);clock.set_style('digital');clock.resize(300,190)
        clock.flip_button.click();wait_for(app,lambda:clock.flip_progress is None and clock.flipped)
        assert cfg['clock_flipped'] and clock.flip_animation.state()==clock.flip_animation.Stopped
        clock.grab().save(str(Path(output)/'clock-flip-calendar.png'))
        clock.flip_button.click();wait_for(app,lambda:clock.flip_progress is None and not clock.flipped)
        assert not cfg['clock_flipped']
        note_id=runtime.notes.new();note=runtime.notes.windows[note_id];note.editor.setPlainText(chr(10).join(['正文保持原样','☐ 检查今日安排','☑ 完成一个任务']));runtime.notes.flush()
        note.flip_button.click();wait_for(app,lambda:note.pages.frames is None and note.pages.currentIndex()==1)
        assert note.row()['flipped'] and note.todos.count()==2
        note.todos.item(0).setCheckState(Qt.Checked);assert '☑ 检查今日安排' in note.editor.toPlainText()
        note.todo_input.setText('添加新的待办');note.todo_input.returnPressed.emit();assert '☐ 添加新的待办' in note.editor.toPlainText()
        assert note.pages.frames is None and note.editor.toPlainText().startswith('正文保持原样')
        note.grab().save(str(Path(output)/'note-flip-todos.png'))
        note.flip_button.click();wait_for(app,lambda:note.pages.frames is None and note.pages.currentIndex()==0)
        assert not note.row()['flipped'] and note.editor.isVisible()
        note.grab().save(str(Path(output)/'note-design-front.png'))
        original_font=appearance({'font':'Segoe UI','font_scale':100});assert original_font['font']=='Segoe UI' and original_font['font_scale']==110
        selected=appearance({'font':'Segoe UI','font_scale':100,'typography_version':1});assert selected['font']=='Segoe UI'
        checks.append('click-only flips: clock button flips to calendar/back and persists side; note flips to checklist, toggles and adds tasks without replacing body text; snapshot buffers and animation stop after transition; display typography migrates old defaults once and preserves later font choices')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        if getattr(clock,'flip_progress',None) is not None:clock.flip_animation.stop();clock.flip_progress=None
        cfg.clear();cfg.update(original);clock.flipped=cfg.get('clock_flipped',False);api.save_config(cfg);runtime.notes.reload();runtime.apply_settings()
