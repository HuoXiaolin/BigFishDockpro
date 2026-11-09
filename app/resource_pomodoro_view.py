"""Two compact timer cards and the icons shared with the collapsed capsule."""
from datetime import datetime

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (QBoxLayout, QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QToolButton, QVBoxLayout, QWidget)

from flash_view import icon
from resource_charts import DashboardCard, sync_card_controls
from resource_compact import ring, text
from resource_pomodoro import duration_text, water_amount


def reminder_ink(kind,light):
    palette={'agenda':('#6246a2','#c8b6ff'), 'battery':('#b82b47','#ff8095'),
             'water':('#1268ab','#83c7ff'), 'rest':('#087959','#72dfb4'),
             'paused':('#59657b','#b9c5d8'), 'focus':('#ab412d','#ffa08a')}
    return palette[kind.removesuffix('_done')][0 if light else 1]


def reminder_icon(p,rect,kind,ink):
    p.save()
    try:
        p.translate(rect.topLeft());p.scale(rect.width()/16,rect.height()/16)
        p.setPen(Qt.NoPen);p.setBrush(QColor(ink))
        path=QPainterPath()
        if kind=='agenda':
            p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(ink),1.5,Qt.SolidLine,Qt.RoundCap))
            p.drawRoundedRect(QRectF(2,3,12,11),2,2)
            p.drawLine(QPointF(2.5,7),QPointF(13.5,7))
            for x in (5.,11.):p.drawLine(QPointF(x,1.8),QPointF(x,4.6))
        elif kind=='battery':
            p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(ink),1.4,Qt.SolidLine,Qt.RoundCap))
            p.drawRoundedRect(QRectF(1,4,12,8),1.5,1.5)
            p.drawLine(QPointF(15,6.5),QPointF(15,9.5))
            p.setPen(Qt.NoPen);p.setBrush(QColor(ink));p.drawRoundedRect(QRectF(3,6,2,4),.6,.6)
        elif kind=='water':
            path.moveTo(8,1)
            path.cubicTo(9,3.7,13,7.4,13,10.4)
            path.cubicTo(13,16.7,3,16.7,3,10.4)
            path.cubicTo(3,7.4,7,3.7,8,1)
            p.drawPath(path)
        elif kind=='paused':
            for x in (4.,9.):p.drawRoundedRect(QRectF(x,2.5,3,11),1,1)
        elif kind=='rest':
            p.drawRoundedRect(QRectF(2,5,10,8),2,2)
            p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(ink),1.4,Qt.SolidLine,Qt.RoundCap))
            p.drawArc(QRectF(9,5.5,6,5.5),-90*16,180*16)
        elif kind.endswith('_done'):
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(ink),2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            path.moveTo(3,8);path.lineTo(6.4,11.2);path.lineTo(13,4.7)
            p.drawPath(path)
        else:
            path.moveTo(8,5);path.cubicTo(5,2,1,5,1.5,9.5)
            path.cubicTo(2,13.7,5,15,8,14.4)
            path.cubicTo(11,15,14,13.7,14.5,9.5)
            path.cubicTo(15,5,11,2,8,5)
            p.drawPath(path)
            p.setPen(QPen(QColor(ink),1.5,Qt.SolidLine,Qt.RoundCap))
            p.drawLine(QPointF(8,5),QPointF(10,1.5))
    finally:p.restore()


class TimerSummary(QWidget):
    def __init__(self,window,model,water=False):
        super().__init__()
        self.owner=window;self.model=model;self.water=water
        self.setFixedHeight(69)

    def paintEvent(self,event):
        c=self.owner.colors;width=self.width()
        if not c:return
        tight=self.height()<60
        diameter=40 if tight else 54
        top=(self.height()-diameter)/2-1
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        circle=QRectF(5,top,diameter,diameter)
        start=diameter+15
        value_rect=QRectF(start,0 if tight else 6,width-start,30 if tight else 36)
        label_rect=QRectF(start+1,29 if tight else 42,width-start-1,12 if tight else 14)
        if self.water:
            enabled,ml,goal,next_at,due=self.model.water()
            percent=100*ml/goal
            value=water_amount(ml)
            mark=tone='water'
            label=f'今日目标 {water_amount(goal)} · {percent:.0f}%'
            emphasized=due
        else:
            phase,status,left,total=self.model.focus()
            percent=100*left/total
            value=duration_text(left)
            tone='paused' if status=='paused' else phase
            mark=phase+'_done' if status=='done' else 'paused' if status=='paused' else phase
            label=('专注' if phase=='focus' else '休息')+{'idle':'时间','running':'中','paused':'已暂停','done':'结束'}[status]
            emphasized=status=='done'
        accent=reminder_ink(tone,c['light'])
        ring(p,circle,percent,accent,c['hover'])
        half=8 if tight else 11
        reminder_icon(p,QRectF(circle.center().x()-half,circle.center().y()-half,2*half,2*half),mark,accent)
        text(p,value_rect,value,c['ink'],25 if tight else 29,True)
        text(p,label_rect,label,accent if emphasized else c['muted'],11,emphasized)
        if self.water:
            status=('今日目标已达成' if ml>=goal else '到喝水时间了' if due else
                    '下次 '+datetime.fromtimestamp(next_at).strftime('%H:%M') if enabled and next_at else '提醒已关闭')
            text(p,label_rect.translated(0,label_rect.height()),status,accent if due else c['muted'],10,due)


class PomodoroView(QWidget):
    def __init__(self,window):
        super().__init__()
        self.owner=window;self.model=window.service.get_pomodoro()
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(5)
        self.cards=QBoxLayout(QBoxLayout.LeftToRight)
        self.cards.setContentsMargins(0,0,0,0);self.cards.setSpacing(7)
        layout.addLayout(self.cards)

        focus,focus_head,focus_body=self.card('番茄专注','peach')
        self.configure=QToolButton();self.configure.setText('设置')
        self.configure.setAccessibleName('番茄钟与喝水设置')
        self.configure.clicked.connect(self.settings);focus_head.addWidget(self.configure)
        self.reset=QToolButton();self.reset.setAccessibleName('重置计时');self.reset.setToolTip('重置计时')
        self.reset.clicked.connect(self.model.reset);focus_head.addWidget(self.reset)
        self.focus_summary=TimerSummary(window,self.model);focus_body.addWidget(self.focus_summary)
        row=QHBoxLayout();row.setSpacing(4)
        self.focus_button=self.control(row,'专注',lambda:self.model.select('focus'),True)
        self.toggle=self.control(row,'开始',self.model.toggle)
        self.toggle.setStyleSheet('QToolButton{background:palette(highlight);color:palette(window-text);font-weight:600;}')
        self.rest_button=self.control(row,'休息',lambda:self.model.select('rest'),True)
        focus_body.addLayout(row)

        water,water_head,water_body=self.card('喝水提醒','ice')
        self.water_switch=QToolButton();self.water_switch.setCheckable(True)
        self.water_switch.setAccessibleName('开启或关闭喝水提醒')
        self.water_switch.clicked.connect(self.enable_water);water_head.addWidget(self.water_switch)
        self.water_summary=TimerSummary(window,self.model,water=True);water_body.addWidget(self.water_summary)
        row=QHBoxLayout();row.setSpacing(4)
        self.drink=self.control(row,'喝一口',self.model.drink)
        self.drink.setStyleSheet('QToolButton{background:palette(highlight);color:palette(window-text);font-weight:600;}')
        self.undo=self.control(row,'撤销',self.model.undo)
        self.delay=self.control(row,'稍后',self.model.delay_water)
        water_body.addLayout(row)

        self.status=QLabel();self.status.setObjectName('Subtle');self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.cards.addWidget(focus,1);self.cards.addWidget(water,1)
        self.refresh()

    def card(self,title,tone):
        card=DashboardCard(self.owner,tone)
        body=QVBoxLayout(card);body.setContentsMargins(9,7,9,8);body.setSpacing(3)
        head=QHBoxLayout();head.setSpacing(3)
        heading=QLabel(title);heading.setObjectName('RankTitle');head.addWidget(heading,1)
        body.addLayout(head)
        return card,head,body

    @staticmethod
    def control(row,label,action,checkable=False):
        button=QToolButton();button.setText(label);button.setCheckable(checkable)
        button.clicked.connect(action);button.setMinimumHeight(23)
        row.addWidget(button,1)
        return button

    def enable_water(self,enabled):
        if not self.owner.service.set_options(resource_water_enabled=enabled):
            self.refresh();self.status.setText('保存失败，请重试。');self.status.show()

    def refresh(self):
        if not self.owner.colors:return
        sync_card_controls(self,self.owner.colors)
        phase,status,_,_=self.model.focus()
        self.focus_button.setChecked(phase=='focus');self.rest_button.setChecked(phase=='rest')
        self.toggle.setText({'idle':'开始','running':'暂停','paused':'继续','done':'再来一轮'}[status])
        self.reset.setEnabled(status!='idle')
        ink=self.owner.colors['muted']
        if self.reset.property('iconInk')!=ink:
            self.reset.setProperty('iconInk',ink)
            self.reset.setIcon(icon('refresh',ink,13));self.reset.setIconSize(QSize(13,13))
        enabled,ml,goal,next_at,due=self.model.water()
        self.water_switch.setChecked(enabled);self.water_switch.setText('已开启' if enabled else '已关闭')
        self.drink.setAccessibleName('记录 '+water_amount(self.model.cfg['resource_water_amount']))
        self.undo.setEnabled(bool(self.model.state['last_ml']))
        self.delay.setVisible(due)
        self.status.setText(self.model.error);self.status.setVisible(bool(self.model.error))
        self.focus_summary.update();self.water_summary.update()

    def resizeEvent(self,event):
        wide=event.size().width()>=385
        direction=QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom
        if self.cards.direction()!=direction:self.cards.setDirection(direction)
        height=69 if wide else 51
        for summary in (self.focus_summary,self.water_summary):
            if summary.height()!=height:summary.setFixedHeight(height)
        layout=self.layout()
        layout.invalidate()
        minimum=layout.minimumSize().height()
        if self.minimumHeight()!=minimum:self.setMinimumHeight(minimum)
        super().resizeEvent(event)

    def settings(self):
        from resource_options import TIMER_RANGES
        from ui_style import ModernSpinBox, button, compact_dialog, exec_dialog
        dialog=QDialog(self.owner);dialog.setWindowTitle('番茄钟与喝水设置')
        layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
        fields={}
        for key,label in (
            ('resource_focus_minutes','专注（分钟）'),('resource_break_minutes','休息（分钟）'),
            ('resource_water_interval','喝水间隔（分钟）'),('resource_water_amount','每次饮水（mL）'),
            ('resource_water_goal','今日目标（mL）'),
        ):
            field=ModernSpinBox();field.setRange(*TIMER_RANGES[key]);field.setValue(self.model.cfg[key])
            field.setAccessibleName(label);form.addRow(label,field);fields[key]=field
        status=QLabel();layout.addWidget(status)
        def save():
            values={key:field.value() for key,field in fields.items()}
            interval_changed=values['resource_water_interval']!=self.model.cfg['resource_water_interval']
            if self.owner.service.set_options(**values):
                if interval_changed and self.model.water()[0] and self.model.water()[3]:self.model.delay_water()
                dialog.accept()
            else:status.setText('保存失败，请重试。')
        actions=QHBoxLayout();actions.addStretch()
        actions.addWidget(button('取消',dialog.reject));actions.addWidget(button('保存',save,'primary'))
        layout.addLayout(actions);compact_dialog(dialog)
        try:exec_dialog(dialog)
        finally:dialog.deleteLater()
