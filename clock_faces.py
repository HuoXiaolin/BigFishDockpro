"""Calendar and time-progress compositions, redrawn only on the clock minute tick."""
import calendar
import datetime
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QColor,QPen,QFont,QLinearGradient


def period_progress(now):
    day=(now.hour*60+now.minute)/1440
    return {'day':day,'week':(now.weekday()+day)/7,
            'month':(now.day-1+day)/calendar.monthrange(now.year,now.month)[1],
            'year':(now.timetuple().tm_yday-1+day)/(366 if calendar.isleap(now.year) else 365)}


def draw_face(style,painter,w,h,now,options,ink,muted,accent,text,time_text,period):
    if style not in ('calendar','orbit','month','calendar_card'):return False
    margin=max(7,min(w,h)*.07);scale=options['font_scale']/100
    def wash(rect,alpha=22,radius=10,color=accent):
        tint=QColor(color);tint.setAlpha(alpha);painter.setPen(Qt.NoPen);painter.setBrush(tint);painter.drawRoundedRect(rect,radius,radius)
    def line(rect,ratio,color=accent):
        wash(rect,55,rect.height()/2,ink)
        if ratio>0:wash(QRectF(rect.x(),rect.y(),rect.width()*max(0,min(1,ratio)),rect.height()),210,rect.height()/2,color)
    weekdays='一二三四五六日'
    if style=='calendar_card':
        year=options.get('_calendar_year',now.year);month=options.get('_calendar_month',now.month)
        top=max(38,min(52,h*.18));bottom=max(23,h*.09);width=w-margin*2;cell_width=width/7
        header_size=max(12,min(20,h*.07))*scale
        text(QRectF(margin,8,max(70,w-130),28),'%d 年 %d 月'%(year,month),header_size,ink,QFont.DemiBold)
        cell_height=max(1,(h-top-bottom-margin)/7)
        for col in range(7):text(QRectF(margin+col*cell_width,top,cell_width,cell_height),weekdays[col],min(14,cell_height*.52)*scale,muted,QFont.Medium,Qt.AlignCenter)
        weeks=calendar.monthcalendar(year,month)
        for row in range(6):
            for col in range(7):
                day=weeks[row][col] if row<len(weeks) else 0
                if not day:continue
                box=QRectF(margin+col*cell_width,top+(row+1)*cell_height,cell_width,cell_height)
                current=(year,month,day)==(now.year,now.month,now.day)
                if current:wash(box.adjusted(cell_width*.1,1,-cell_width*.1,-1),80,7)
                text(box,str(day),min(20,cell_height*.62)*scale,ink if current else muted,QFont.DemiBold if current else QFont.Medium,Qt.AlignCenter)
        text(QRectF(margin,h-bottom,width,bottom*.75),'今天 · %d月%d日  星期%s'%(now.month,now.day,weekdays[now.weekday()]),min(12,h*.044),muted,align=Qt.AlignCenter)
    elif style=='calendar':
        left=w*.34;right=w-left-margin*2
        wash(QRectF(margin,margin,left,h-margin*2),30,12)
        text(QRectF(margin*1.5,margin+h*.02,left-margin,h*.16),'%d 年 · %02d 月'%(now.year,now.month),h*.071,muted,QFont.Medium)
        text(QRectF(margin*1.5,h*.23,left-margin,h*.43),'%02d'%now.day,h*.37*scale,ink,QFont.DemiBold)
        text(QRectF(margin*1.5,h*.72,left-margin,h*.12),'星期'+weekdays[now.weekday()],h*.083,ink,QFont.Medium)
        x=left+margin*1.5
        if period:text(QRectF(x,h*.08,right,h*.10),period,h*.07,muted)
        text(QRectF(x,h*.22,right,h*.25),time_text,h*.24*scale,ink,QFont.DemiBold)
        text(QRectF(x,h*.51,right,h*.10),'本周',h*.068,muted,QFont.Medium)
        monday=now.date()-datetime.timedelta(days=now.weekday());cell=right/7
        for index in range(7):
            day=monday+datetime.timedelta(days=index);box=QRectF(x+cell*index,h*.65,cell-1,h*.23)
            if day==now.date():wash(box,65,5)
            color=ink if day==now.date() else muted
            text(QRectF(box.x(),box.y(),box.width(),box.height()*.38),weekdays[index],h*.058,color,QFont.Medium,Qt.AlignCenter)
            text(QRectF(box.x(),box.y()+box.height()*.4,box.width(),box.height()*.55),str(day.day),h*.068,color,QFont.DemiBold if day==now.date() else QFont.Normal,Qt.AlignCenter)
    elif style=='orbit':
        horizontal=w>=h*1.25
        diameter=min(h*.78,w*.37) if horizontal else min(w*.68,h*.43)
        x=margin if horizontal else (w-diameter)/2;y=(h-diameter)/2 if horizontal else margin
        ring=QRectF(x,y,diameter,diameter);track=QColor(ink);track.setAlpha(42)
        base=QColor(options.get('color') or accent);hue=base.hslHueF()
        if hue<0:hue=.55
        bright=ink.lightness()>200
        progress_ink=QColor.fromHslF(hue,.42,.76 if bright else .48)
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(track,max(4,diameter*.052),Qt.SolidLine,Qt.RoundCap));painter.drawEllipse(ring)
        values=period_progress(now);progress=values['day']
        painter.setPen(QPen(progress_ink,max(4,diameter*.052),Qt.SolidLine,Qt.RoundCap));painter.drawArc(ring,90*16,-round(progress*360*16))
        text(QRectF(x+diameter*.055,y+diameter*.27,diameter*.89,diameter*.28),time_text,diameter*.29*scale,ink,QFont.Bold,Qt.AlignCenter)
        text(QRectF(x+diameter*.08,y+diameter*.59,diameter*.84,diameter*.13),'今日已过 %d%%'%round(progress*100),diameter*.085,ink,QFont.DemiBold,Qt.AlignCenter)
        x2=x+diameter+margin*1.65 if horizontal else margin;y2=h*.14 if horizontal else h*.51
        width=w-x2-margin if horizontal else w-margin*2
        text(QRectF(x2,y2,width,h*(.15 if horizontal else .08)),'%d月%d日'%(now.month,now.day),h*(.125 if horizontal else .08),ink,QFont.DemiBold)
        text(QRectF(x2,y2+h*(.17 if horizontal else .09),width,h*(.11 if horizontal else .07)),'星期'+weekdays[now.weekday()],h*(.085 if horizontal else .06),ink,QFont.DemiBold)
        for index,(title,ratio) in enumerate([('本周',values['week']),('本月',values['month']),('本年',values['year'])]):
            top=h*(.46+index*.17) if horizontal else h*(.69+index*.09)
            label_height=h*(.09 if horizontal else .05)
            text(QRectF(x2,top,width*.6,label_height),title,h*(.076 if horizontal else .05),ink,QFont.DemiBold)
            text(QRectF(x2+width*.65,top,width*.35,label_height),'%d%%'%round(ratio*100),h*(.078 if horizontal else .05),ink,QFont.Bold,align=Qt.AlignRight|Qt.AlignVCenter)
            bar=QRectF(x2,top+label_height+h*.022,width,max(5,min(12,h*.032)) if horizontal else max(4,h*.018))
            wash(bar,42,bar.height()/2,ink)
            if ratio>0:
                hue_shift=(-.025,0,.025)[index]
                start=QColor.fromHslF((hue+hue_shift)%1,.44,.82 if bright else .63)
                end=QColor.fromHslF((hue+hue_shift)%1,.47,.71 if bright else .46)
                fill=QLinearGradient(bar.topLeft(),bar.topRight());fill.setColorAt(0,start);fill.setColorAt(1,end)
                painter.setPen(Qt.NoPen);painter.setBrush(fill);painter.drawRoundedRect(QRectF(bar.x(),bar.y(),bar.width()*ratio,bar.height()),bar.height()/2,bar.height()/2)
    else:
        # A six-row grid keeps the cell positions stable between months.
        header=h*.25;usable=w-margin*2
        text(QRectF(margin,margin,usable*.52,header*.52),'%d 年 %d 月'%(now.year,now.month),h*.095,ink,QFont.DemiBold)
        text(QRectF(margin+usable*.58,margin,usable*.42,header*.52),time_text,h*.12*scale,ink,QFont.DemiBold)
        top=margin+header*.72;cell_width=usable/7;cell_height=max(1,(h-top-margin)/7)
        for index in range(7):text(QRectF(margin+index*cell_width,top,cell_width,cell_height),weekdays[index],cell_height*.62,muted,QFont.Medium,Qt.AlignCenter)
        weeks=calendar.Calendar(firstweekday=0).monthdatescalendar(now.year,now.month)
        start=weeks[0][0]
        for offset in range(42):
            day=start+datetime.timedelta(days=offset);row,col=divmod(offset,7)
            box=QRectF(margin+col*cell_width,top+(row+1)*cell_height,cell_width,cell_height)
            current=day==now.date();color=QColor(ink if current else muted)
            if day.month!=now.month:color.setAlpha(170)
            if current:wash(box.adjusted(cell_width*.12,0,-cell_width*.12,0),75,5)
            text(box,str(day.day),cell_height*.62,color,QFont.DemiBold if current else QFont.Normal,Qt.AlignCenter)
    return True
