"""Work-calendar boundaries, responsive faces and actual grouped settings UI."""
import copy,datetime,json
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QPixmap,QPainter,QColor,QFont
from PyQt5.QtWidgets import QApplication,QFileDialog


def run(api,runtime,root,output,checks):
    import work_schedule as work
    from clock_appearance import normalize,STYLES,PRESETS
    from desktop_clock import draw_clock,ClockOptions
    app=QApplication.instance();cfg=runtime.dock.cfg;saved=copy.deepcopy(cfg);dialog=None
    try:
        base=work.normalize({});assert len(work.builtin(2026)['holidays'])==33 and len(work.builtin(2026)['workdays'])==6
        assert work.day_info(datetime.date(2026,1,4),base)==(True,'调休上班',True)
        assert work.day_info(datetime.date(2026,10,1),base)==(False,'国庆节',True)
        assert not work.day_info(datetime.date(2027,1,1),base)[2]
        assert work.progress(datetime.datetime(2026,10,28,8),base)['state']=='before'
        assert work.progress(datetime.datetime(2026,10,28,9),base)['ratio']==0
        assert work.progress(datetime.datetime(2026,10,28,13,30),base)['ratio']==.5
        assert work.progress(datetime.datetime(2026,10,28,18),base)['state']=='done'
        assert work.progress(datetime.datetime(2026,10,1,12),base)['ratio'] is None
        pause=work.normalize(dict(base,break_enabled=True));state=work.progress(datetime.datetime(2026,10,28,12,30),pause)
        assert state['state']=='break' and state['ratio']==3/8
        assert work.progress(datetime.datetime(2026,10,28,14),pause)['ratio']==.5
        night=dict(base,start='22:00',end='06:00')
        state=work.progress(datetime.datetime(2026,9,25,2),night);assert state['shift_date']=='2026-09-24' and state['state']=='working' and state['ratio']==.5
        assert work.progress(datetime.datetime(2026,9,25,6,1),night)['state']=='rest'
        custom=work.normalize(dict(base,rest_dates=['2026-10-28'],work_dates=['2026-10-31']))
        assert not work.day_info(datetime.date(2026,10,28),custom)[0] and work.day_info(datetime.date(2026,10,31),custom)[0]
        for bad in ({'start':'24:00'},{'end':'09:00'},{'rest_dates':['2026-02-30']},{'work_dates':['2026-10-28'],'rest_dates':['2026-10-28']},{'break_enabled':True,'break_start':'08:00'}):
            try:work.normalize(bad,True)
            except ValueError:pass
            else:raise AssertionError(bad)
        checks.append('work progress: 2026 official 33 rest days/6 make-up days; Sunday make-up, statutory holiday, unknown-year flag, before/start/mid/end, optional rest deduction, overnight shift into holiday, custom overrides and invalid schedules checked')
        now=datetime.datetime(2026,10,28,15,42);styles=STYLES+[('独立月历','calendar_card')]
        sheet=QPixmap(1120,780);sheet.fill(QColor('#eef3f8'));sp=QPainter(sheet)
        for index,(title,style) in enumerate(styles):
            for theme in ('light','dark'):
                for width,height in [(520,280),(290,400),(180,120)]:
                    options=normalize(dict(PRESETS[0][1],theme=theme,work=base))
                    options['_now']=now
                    image=QPixmap(width,height);image.fill(Qt.transparent);p=QPainter(image);draw_clock(p,QRectF(0,0,width,height),runtime.dock,options,style);p.end()
                    assert not image.isNull()
                    if theme=='light' and (width,height)==(520,280):image.save(str(Path(output)/('clock-redesign-'+style+'.png')))
            if index<6:
                options=normalize(dict(PRESETS[0][1],work=base));options['_now']=now
                tile=QPixmap(350,205);tile.fill(Qt.transparent);p=QPainter(tile);draw_clock(p,QRectF(0,0,350,205),runtime.dock,options,style);p.end()
                x=15+(index%3)*370;y=32+(index//3)*260
                sp.setPen(QColor('#36516a'));sp.setFont(QFont('Microsoft YaHei UI',11));sp.drawText(x,y-7,title);sp.drawPixmap(x,y,tile)
        sp.end();sheet=sheet.copy(0,0,1120,530);sheet.save(str(Path(output)/'clock-redesign-overview.png'))
        runtime.clock.resize(520,280);dialog=ClockOptions(runtime.clock);dialog.show();app.processEvents()
        assert dialog.tabs.count()==4 and len(dialog.style_buttons)==6
        assert sum(item.isChecked() for item,value in dialog.style_buttons)==1
        dialog.style_buttons[4][0].click();assert dialog.fields['style'].currentData()=='orbit' and dialog.style_buttons[4][0].isChecked()
        import clock_design
        with patch.object(clock_design,'draw',wraps=clock_design.draw) as render:
            dialog.preview.grab();assert render.call_args.args[2:4]==(dialog.fields['width'].value(),dialog.fields['height'].value())
        for index in range(4):
            dialog.tabs.setCurrentIndex(index);app.processEvents();dialog.grab().save(str(Path(output)/('clock-redesign-settings-%d.png'%index)))
        dialog.fields['start'].setText('22:00');dialog.fields['end'].setText('06:00');dialog.fields['accent_color'].setText('#4b8eb6')
        dialog.fields['font_weight'].setCurrentIndex(dialog.fields['font_weight'].findData(75));dialog.fields['width'].setValue(580);dialog.fields['height'].setValue(320)
        assert dialog.commit() and cfg['clock_appearance']['work']['start']=='22:00' and cfg['clock_appearance']['font_weight']==75
        before=copy.deepcopy(cfg)
        dialog.fields['end'].setText('22:00');assert not dialog.commit() and cfg==before
        dialog.fields['end'].setText('06:00')
        with patch.object(api,'save_config',return_value=False):assert not dialog.commit()
        assert cfg==before
        calendar={'year':2027,'source':'演示自定义日历','holidays':{'2027-01-01':'示例休息日'},'workdays':['2027-01-02']}
        file=Path(root)/'demo-work-calendar.json';file.write_text(json.dumps(calendar),encoding='utf-8')
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(file),'')):dialog.import_calendar()
        assert dialog.commit() and cfg['clock_appearance']['work']['calendars']['2027']['workdays']==['2027-01-02']
        from config_transfer import normalize as import_config
        imported=import_config(copy.deepcopy(cfg),api);assert imported['clock_appearance']['work']==cfg['clock_appearance']['work']
        assert api.load_config()['clock_appearance']['work']==cfg['clock_appearance']['work']
        bad=copy.deepcopy(cfg);bad['clock_appearance']['work']['start']='25:00'
        try:import_config(bad,api)
        except ValueError:pass
        else:raise AssertionError('Malformed imported shift must be rejected')
        dialog.calendar_years.setCurrentIndex(dialog.calendar_years.findData('2027'));dialog.remove_calendar();assert dialog.commit() and '2027' not in cfg['clock_appearance']['work']['calendars']
        dialog.tabs.setCurrentIndex(3);app.processEvents()
        viewport=dialog.tabs.currentWidget().viewport()
        for field in dialog.weekdays:assert field.mapTo(viewport,field.rect().bottomRight()).x()<viewport.width(),'weekday selector clipped'
        dialog.grab().save(str(Path(output)/'clock-redesign-settings-3.png'))
        runtime.clock.resize(320,180);runtime.clock.position_flip();app.processEvents()
        assert runtime.clock.flip_button.y()==14 and runtime.clock.flip_button.size().width()==12 and runtime.clock.flip_button.size().height()==12 and runtime.clock.flip_button.iconSize().width()==12 and not runtime.clock.flip_button.text()
        from clock_design import draw
        from clock_appearance import normalize as clock_options
        options=clock_options({});options['_header_controls']=True;labels=[];image=QPixmap(320,180);image.fill(Qt.transparent);p=QPainter(image)
        draw('orbit',p,320,180,now,options,QColor('#19364d'),QColor('#537084'),QColor('#318ab6'),lambda box,value,*args:labels.append((box,value)),'09:30','');p.end()
        assert all(box.right()<=278 for box,value in labels if value.startswith('星期') and box.top()<36)
        runtime.clock.grab().save(str(Path(output)/'clock-footer-button.png'))
        checks.append('all six clock faces plus standalone calendar rendered light/dark and landscape/portrait/compact; four grouped settings pages, independent typography/accent/size, valid save, invalid time rejection, failed save and annual-calendar import/configuration reload-transfer checked')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        cfg.clear();cfg.update(saved);api.save_config(cfg);runtime.clock.reposition();runtime.calendar.reposition();runtime.apply_settings();app.processEvents()
