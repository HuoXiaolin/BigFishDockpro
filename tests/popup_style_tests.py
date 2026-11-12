"""Native popup themes and real calendar/table geometry on a private desktop."""
import json,sys,traceback
from pathlib import Path
from types import SimpleNamespace


def run(app,output,checks):
    from PyQt5.QtCore import Qt,QDate,QPointF,QEvent,QTimer
    from PyQt5.QtGui import QPalette,QMouseEvent
    from PyQt5.QtWidgets import QApplication,QWidget,QDialog,QVBoxLayout,QDateTimeEdit
    from ui_style import apply_theme
    from popup_style import ThemedCalendar,prepare_popup
    from resource_pages import AiView
    from reset_credits import summary,expiry_rows,credit_count
    output=Path(output);today=QDate.currentDate().toString('yyyy-MM-dd')
    totals=dict(tokens=261798443,input=1000,output=2000,cacheRead=500,cacheWrite=0,records=314,cost=93.49,estimated=True,unpriced=31)
    provider=dict(id='Codex',name='Codex',plan='prolite',status='已连接',usageAvailable=True,usageComplete=True,
        quotas=[dict(label='每周额度',percent=39,reset='2026-11-18T12:00:00Z')],
        days=[dict(date=today,model='gpt-6.1-sol',summary=totals)],hours=[],
        resetCredits=dict(available=2,expiries=['2026-12-02T01:00:00Z','2026-12-01T01:00:00Z','invalid'],status='ok'))
    assert credit_count(provider)==2 and len(expiry_rows(provider))==2
    assert '0 张' in summary(dict(provider,resetCredits=dict(available=0,status='ok')))
    assert '暂不可用' in summary(dict(provider,resetCredits=dict(available=None,status='unavailable')))
    assert credit_count(dict(provider,resetCredits=dict(available=True))) is None
    host=QWidget();host.setStyleSheet('QWidget{background:transparent;color:#080808} QLabel{font-size:10px} QDateEdit{background:#111111} QHeaderView::section{background:white}')
    host.colors={};host.service=SimpleNamespace(deck=SimpleNamespace(providers=[provider],ai_status='已更新'))
    view=AiView(host);view.setParent(host);host.ai_view=view
    date_dialog=None
    try:
        for light in (True,False):
            apply_theme(app,light);palette=app.palette()
            host.colors=dict(light=light,ink='#17212c' if light else '#f3f5fa',muted='#566777' if light else '#bec9d6',
                hover='#dae7f2' if light else '#384552',field='#f2f7fa' if light else '#25313e',surface='#f5f8fb' if light else '#20262e')
            view.refresh();view.resize(620,450);view.show();host.resize(620,450);host.show();app.processEvents()
            assert len(view.summary.reset_buttons)==1 and '2 张' in view.summary.reset_buttons[0].text()
            assert not view.summary.reset_buttons[0].icon().isNull() and '12-01' in view.summary.reset_buttons[0].text()
            view.summary.grab().save(str(output/('quota-reset-'+('light' if light else 'dark')+'.png')))
            view.grab().save(str(output/('ai-overview-reset-'+('light' if light else 'dark')+'.png')))
            opened=[]
            def inspect_credit_details():
                modal=app.activeModalWidget()
                try:
                    from PyQt5.QtWidgets import QTableWidget
                    table=modal.findChild(QTableWidget)
                    opened.append(bool(table and table.rowCount()==2 and table.item(0,0).text()<table.item(1,0).text()))
                    opened.append(table.palette().color(QPalette.Text)==app.palette().color(QPalette.Text))
                    modal.grab().save(str(output/('reset-credit-details-'+('light' if light else 'dark')+'.png')))
                finally:
                    if modal:modal.accept()
            QTimer.singleShot(0,inspect_credit_details)
            view.summary.reset_buttons[0].click()
            assert opened==[True,True]
            dialog=view.detail_dialog
            for width in (720,620):
                dialog.resize(width,390);dialog.show();app.processEvents()
                assert dialog.property('themedPopup') and dialog.palette().color(QPalette.Window)==palette.color(QPalette.Window)
                assert view.models.rowCount()==1 and view.models.item(0,1).text()=='261,798,443'
                header=view.models.horizontalHeader()
                assert header.length()<=view.models.viewport().width()+2,(width,header.length(),view.models.viewport().width())
                assert view.start.geometry().right()<view.end.geometry().left()
                dialog.grab().save(str(output/('ai-detail-'+('light' if light else 'dark')+'-'+str(width)+'.png')))
            calendar=view.end.calendarWidget()
            assert isinstance(calendar,ThemedCalendar)
            assert calendar.palette().color(QPalette.Base)==palette.color(QPalette.Base)
            assert calendar.sizeHint().width()>=280
            point=QPointF(view.end.width()-12,view.end.height()/2)
            for kind in (QEvent.MouseButtonPress,QEvent.MouseButtonRelease):
                QApplication.sendEvent(view.end,QMouseEvent(kind,point,Qt.LeftButton,Qt.LeftButton if kind==QEvent.MouseButtonPress else Qt.NoButton,Qt.NoModifier))
            app.processEvents()
            assert calendar.isVisible()
            calendar.grab().save(str(output/('calendar-'+('light' if light else 'dark')+'.png')))
            calendar.window().hide();dialog.hide();host.hide()
            date_dialog=QDialog(host);lay=QVBoxLayout(date_dialog);field=QDateTimeEdit();field.setCalendarPopup(True);lay.addWidget(field)
            prepare_popup(date_dialog);date_dialog.show();app.processEvents()
            assert isinstance(field.calendarWidget(),ThemedCalendar)
            date_dialog.hide();date_dialog.deleteLater();date_dialog=None;app.processEvents()
        checks.append('popup themes: AI detail table retains full numeric columns at 720/620 px; date popups and ordinary datetime dialogs isolate glass-parent styles in light/dark; reset count, zero, unavailable and sorted expiry details remain distinct')
    finally:
        if date_dialog:date_dialog.deleteLater()
        host.close();view.detail_dialog.close();view.detail_dialog.deleteLater();host.deleteLater();apply_theme(app,True);app.processEvents()


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(root/'app'),str(root/'tools'),str(root/'tests'),str(root)]
    from run_isolated_test import assert_isolated
    assert_isolated()
    from PyQt5.QtWidgets import QApplication
    from ui_style import shutdown_ui
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);output=Path(sys.argv[-1]);checks=[]
    try:run(app,output,checks);result=dict(passed=True,checks=checks)
    except Exception:result=dict(passed=False,error=traceback.format_exc())
    finally:shutdown_ui(app)
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.exit(0 if result['passed'] else 1)
