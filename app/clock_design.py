"""All clock faces share clear typography, accent roles and responsive spacing."""
import math,calendar,datetime
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QPen,QFont,QLinearGradient
from clock_faces import period_progress
from work_schedule import progress as work_progress,day_info


def draw(style,p,w,h,now,o,ink,muted,accent,text,time_text,period):
    scale=o['font_scale']/100;m=min(w,h)*o['padding']/100
    wide=o['layout']=='wide' or (o['layout']=='auto' and w>=h*1.4)
    compact=w<230 or h<145
    weekdays='一二三四五六日';date='%d月%d日'% (now.month,now.day);weekday='星期'+weekdays[now.weekday()]
    def wash(box,alpha=20,r=12,color=accent):
        c=QColor(color);c.setAlpha(alpha);p.setPen(Qt.NoPen);p.setBrush(c);p.drawRoundedRect(box,r,r)
    def label(box,value,size=12,color=muted,weight=QFont.Medium,align=Qt.AlignLeft|Qt.AlignVCenter):text(box,value,size,color,weight,align)
    def bar(box,ratio):
        wash(box,24,box.height()/2,ink)
        if ratio and ratio>0:
            gradient=QLinearGradient(box.topLeft(),box.topRight());gradient.setColorAt(0,accent.lighter(120));gradient.setColorAt(1,accent)
            p.setPen(Qt.NoPen);p.setBrush(gradient);p.drawRoundedRect(QRectF(box.x(),box.y(),box.width()*min(1,ratio),box.height()),box.height()/2,box.height()/2)
    def work_tile(box):
        work=work_progress(now,o['work']);wash(box,20,12)
        pad=min(12,box.height()*.13);a=box.adjusted(pad,pad,-pad,-pad);head_h=a.height()*.34
        if box.height()<55:
            value=work['title']+('  %d%%'%round(work['ratio']*100) if work['ratio'] is not None else '')
            label(QRectF(a.x(),a.y(),a.width(),max(13,a.height()-8)),value,12,ink,QFont.DemiBold)
            bar(QRectF(a.x(),a.bottom()-4,a.width(),4),work['ratio']);return
        label(QRectF(a.x(),a.y(),a.width()*.63,head_h),work['title'],min(16,head_h*.82),ink,QFont.DemiBold)
        percent='休息日' if work['ratio'] is None else '%d%%'%round(work['ratio']*100)
        label(QRectF(a.x()+a.width()*.65,a.y(),a.width()*.35,head_h),percent,min(18,head_h*.88),accent,QFont.Bold,Qt.AlignRight|Qt.AlignVCenter)
        bh=min(o['bar_width'],max(4,a.height()*.14));bar(QRectF(a.x(),a.y()+head_h+5,a.width(),bh),work['ratio'])
        detail=work['detail']+(' · 工作周计算' if not work['known'] else '')
        label(QRectF(a.x(),a.bottom()-a.height()*.27,a.width(),a.height()*.27),detail,min(13,a.height()*.23),muted)
    if compact and style=='orbit':
        d=min(h*.78,w*.45);x=m;y=(h-d)/2;ring=QRectF(x,y,d,d);values=period_progress(now);work=work_progress(now,o['work'])
        ratio=work['ratio'] if o['ring_mode']=='work' else values['day'];track=QColor(ink);track.setAlpha(30)
        p.setBrush(Qt.NoBrush);p.setPen(QPen(track,4,Qt.SolidLine,Qt.RoundCap));p.drawEllipse(ring)
        if ratio:p.setPen(QPen(accent,4,Qt.SolidLine,Qt.RoundCap));p.drawArc(ring,90*16,-round(ratio*360*16))
        label(QRectF(x+d*.06,y+d*.3,d*.88,d*.4),time_text,d*.3*scale,ink,QFont.Bold,Qt.AlignCenter)
        right=x+d+max(7,m);span=w-right-m
        label(QRectF(right,h*.19,span,h*.20),work['title'] if o['show_work'] else weekday,10,muted)
        label(QRectF(right,h*.42,span,h*.22),work['detail'].replace('还剩 ','').replace('分钟','分') if o['show_work'] else '%d%%'%round(values['day']*100),12,ink,QFont.DemiBold)
        bar(QRectF(right,h*.77,span,4),work['ratio'] if o['show_work'] else values['day']);return
    if compact and style not in ('month','calendar_card'):
        label(QRectF(m,m,w-2*m,h*.52),time_text,h*.42*scale,ink,QFont.Bold)
        if style=='orbit' and o['show_work']:work_tile(QRectF(m,h*.58,w-2*m,h*.36))
        elif o['show_date']:label(QRectF(m,h*.68,w-2*m,h*.2),date+' · '+weekday,h*.13,muted)
        return
    if style=='digital':
        if o['show_date']:label(QRectF(m,h*.12,w-2*m,h*.13),date+'  '+weekday,h*.09)
        align=Qt.AlignCenter if o['align']=='center' else Qt.AlignLeft|Qt.AlignVCenter
        label(QRectF(m,h*.29 if o['show_date'] else h*.18,w-2*m,h*.48),time_text,h*.44*scale,ink,o['font_weight'],align)
        if period:label(QRectF(m,h*.77,w-2*m,h*.12),period,h*.075,accent,QFont.DemiBold,align)
        else:
            p.setPen(QPen(QColor(accent),max(2,h*.012),Qt.SolidLine,Qt.RoundCap));p.drawLine(QPointF(m,h*.84),QPointF(m+min(42,w*.11),h*.84))
    elif style=='analog':
        diameter=min(h*.75,w*.43) if wide else min(w*.73,h*.63)
        cx=m+diameter/2 if wide else w/2;cy=h/2 if wide else m+diameter/2
        r=diameter/2;wash(QRectF(cx-r*1.05,cy-r*1.05,r*2.1,r*2.1),16,r*1.05)
        p.setBrush(Qt.NoBrush);edge=QColor(ink);edge.setAlpha(30);p.setPen(QPen(edge,max(1,r*.012)));p.drawEllipse(QPointF(cx,cy),r,r)
        for i in range(60):
            a=i*math.pi/30;major=i%5==0
            if i%15==0:continue
            c=QColor(ink if major else muted);c.setAlpha(160 if major else 65)
            p.setPen(QPen(c,max(1.5,r*.018) if major else max(1,r*.009),Qt.SolidLine,Qt.RoundCap))
            p.drawLine(QPointF(cx+math.sin(a)*r*(.81 if major else .87),cy-math.cos(a)*r*(.81 if major else .87)),QPointF(cx+math.sin(a)*r*.92,cy-math.cos(a)*r*.92))
        for number,dx,dy in [('12',0,-.76),('3',.76,0),('6',0,.76),('9',-.76,0)]:label(QRectF(cx+dx*r-r*.18,cy+dy*r-r*.14,r*.36,r*.28),number,r*.21,ink,QFont.DemiBold,Qt.AlignCenter)
        for angle,length,width,color in [((now.hour%12+now.minute/60)*math.pi/6,.48,.065,ink),(now.minute*math.pi/30,.69,.037,accent)]:
            p.setPen(QPen(color,max(2,r*width),Qt.SolidLine,Qt.RoundCap));p.drawLine(QPointF(cx,cy),QPointF(cx+math.sin(angle)*r*length,cy-math.cos(angle)*r*length))
        p.setPen(Qt.NoPen);p.setBrush(accent);p.drawEllipse(QPointF(cx,cy),max(3,r*.045),max(3,r*.045))
        x=m+diameter+m if wide else m;top=h*.26 if wide else h*.74;span=w-x-m
        label(QRectF(x,top,span,h*.22 if wide else h*.12),(period+' ' if period else '')+time_text,h*(.23 if wide else .12)*scale,ink,QFont.Bold,Qt.AlignLeft|Qt.AlignVCenter if wide else Qt.AlignCenter)
        if o['show_date']:label(QRectF(x,top+h*(.25 if wide else .13),span,h*.12 if wide else h*.08),date+' · '+weekday,h*(.075 if wide else .047),muted,align=Qt.AlignLeft|Qt.AlignVCenter if wide else Qt.AlignCenter)
    elif style=='stacked':
        gap=max(8,m*.8);horizontal=wide if o['layout']!='auto' else w>=h*.85
        if o['show_date']:label(QRectF(m,m,w-2*m,h*.13),date+'  '+weekday,h*.075)
        top=h*.27 if o['show_date'] else m;space=h-top-m
        for index,(value,name) in enumerate([(time_text.split(':')[0],'小时'+(' · '+period if period else '')),('%02d'%now.minute,'分钟')]):
            box=QRectF(m+index*(w-2*m+gap)/2,top,(w-2*m-gap)/2,space) if horizontal else QRectF(m,top+index*(space+gap)/2,w-2*m,(space-gap)/2)
            wash(box,21,16);label(QRectF(box.x()+10,box.y()+box.height()*.08,box.width()-20,box.height()*.16),name,min(13,box.height()*.12),muted)
            label(QRectF(box.x()+8,box.y()+box.height()*.28,box.width()-16,box.height()*.59),value,box.height()*.56*scale,ink,QFont.Bold,Qt.AlignCenter)
    elif style=='calendar':
        left=w*.32 if wide else w*.25;daybox=QRectF(m,m,left,h*.50 if not wide else h-2*m);wash(daybox,23,16)
        label(QRectF(daybox.x()+8,daybox.y()+daybox.height()*.10,daybox.width()-16,daybox.height()*.16),'%d 年 %d 月'%(now.year,now.month),min(14,daybox.height()*.10),muted)
        label(QRectF(daybox.x()+8,daybox.y()+daybox.height()*.30,daybox.width()-16,daybox.height()*.44),str(now.day),daybox.height()*.41*scale,ink,QFont.Bold,Qt.AlignCenter)
        label(QRectF(daybox.x()+8,daybox.bottom()-daybox.height()*.2,daybox.width()-16,daybox.height()*.12),weekday,min(14,daybox.height()*.10),accent,QFont.DemiBold,Qt.AlignCenter)
        x=daybox.right()+m;span=w-x-m
        label(QRectF(x,m,span,h*.32 if wide else h*.25),(period+' ' if period else '')+time_text,h*(.23 if wide else .17)*scale,ink,QFont.Bold)
        info=day_info(now.date(),o['work']);label(QRectF(x,h*.36 if wide else h*.27,span,h*.12),info[1],h*.065,accent)
        start=now.date()-datetime.timedelta(days=now.weekday());x=x if wide else m;span=span if wide else w-2*m;top=h*.59 if wide else h*.65;cell=span/7
        for i in range(7):
            day=start+datetime.timedelta(days=i);box=QRectF(x+i*cell,top,cell-3,h*.27)
            if day==now.date():wash(box,35,8)
            color=ink if day==now.date() else muted
            label(QRectF(box.x(),box.y(),box.width(),box.height()*.4),weekdays[i],h*.052,color,align=Qt.AlignCenter)
            label(QRectF(box.x(),box.y()+box.height()*.42,box.width(),box.height()*.5),str(day.day),h*.076,color,QFont.DemiBold,Qt.AlignCenter)
    elif style=='orbit':
        values=period_progress(now);work=work_progress(now,o['work'])
        rows=[('本周',values['week'],'show_week'),('本月',values['month'],'show_month'),('本年',values['year'],'show_year')]
        rows=[row for row in rows if o[row[2]]]
        tiles_h=h*(.24 if wide else .15) if rows else 0;tiles_top=h-m-tiles_h
        if wide:
            d=min(w*.32,tiles_top-m*1.3);x=m*1.15;y=(tiles_top-d)/2
            rx=x+d+m*1.25;rw=w-rx-m
            label(QRectF(rx,m,rw*.66,h*.11),date,h*.09,ink,QFont.DemiBold)
            label(QRectF(rx+rw*.65,m,rw*.35,h*.11),weekday,h*.055,muted,QFont.Medium,Qt.AlignRight|Qt.AlignVCenter)
            workbox=QRectF(rx,m+h*.15,rw,tiles_top-(m+h*.15)-h*.055)
        else:
            d=min(w*.62,h*.40);x=(w-d)/2;y=m*.65
            label(QRectF(m,y+d+7,w-2*m,h*.06),date+'  '+weekday,h*.04,muted,align=Qt.AlignCenter)
            workbox=QRectF(m,y+d+h*.09,w-2*m,tiles_top-(y+d+h*.09)-12)
        ring=QRectF(x,y,d,d);stroke=min(o['ring_width'],d*.065)
        track=QColor(ink);track.setAlpha(28);p.setBrush(Qt.NoBrush);p.setPen(QPen(track,stroke,Qt.SolidLine,Qt.RoundCap));p.drawEllipse(ring)
        ratio=work['ratio'] if o['ring_mode']=='work' else values['day']
        if ratio:
            g=QLinearGradient(ring.topLeft(),ring.bottomRight());g.setColorAt(0,accent.lighter(125));g.setColorAt(1,accent)
            from PyQt5.QtGui import QBrush
            p.setPen(QPen(QBrush(g),stroke,Qt.SolidLine,Qt.RoundCap));p.drawArc(ring,90*16,-round(ratio*360*16))
        label(QRectF(x+d*.055,y+d*.26,d*.89,d*.40),time_text,d*.34*scale,ink,QFont.Bold,Qt.AlignCenter)
        title=(period+' · ' if period else '')+('下班' if o['ring_mode']=='work' else '今日')+' '+('休息日' if ratio is None else '%d%%'%round(ratio*100))
        label(QRectF(x+d*.10,y+d*.67,d*.80,d*.14),title,d*.08,muted,QFont.Medium,Qt.AlignCenter)
        if o['show_work']:
            wash(workbox,28,14);pad=min(12,workbox.height()*.13);a=workbox.adjusted(pad,pad,-pad,-pad)
            if workbox.height()>=70:
                label(QRectF(a.x(),a.y(),a.width()*.65,a.height()*.22),work['title'],min(13,a.height()*.18),muted,QFont.Medium)
                pct='休息日' if work['ratio'] is None else '%d%%'%round(work['ratio']*100)
                label(QRectF(a.x()+a.width()*.65,a.y(),a.width()*.35,a.height()*.22),pct,min(19,a.height()*.23),accent,QFont.DemiBold,Qt.AlignRight|Qt.AlignVCenter)
                detail=work['detail'].replace('还剩 ','').replace('距上班 ','').replace('分钟','分').replace('小时','小时 ')
                label(QRectF(a.x(),a.y()+a.height()*.29,a.width(),a.height()*.37),detail,min(28,a.height()*.36),ink,QFont.DemiBold)
                info=o['work']['start']+' — '+o['work']['end'] if work['working'] else ('下次 '+work['next_start'].strftime('%m/%d %H:%M') if work.get('next_start') else '按工作日历')
                if not work['known']:info+=' · 按工作周'
                label(QRectF(a.x(),a.y()+a.height()*.71,a.width()*.70,a.height()*.16),info,min(11,a.height()*.15),muted)
                bar(QRectF(a.x(),a.bottom()-min(o['bar_width'],a.height()*.10),a.width(),min(o['bar_width'],a.height()*.10)),work['ratio'])
            else:work_tile(workbox)
        else:
            label(workbox,'把每一天过得从容一点',min(18,workbox.height()*.2),muted)
        gap=max(7,m*.5);tw=(w-2*m-gap*max(0,len(rows)-1))/max(1,len(rows))
        for i,(name,value,key) in enumerate(rows):
            box=QRectF(m+i*(tw+gap),tiles_top,tw,tiles_h);wash(box,18,11)
            pad=min(10,tw*.08);label(QRectF(box.x()+pad,box.y()+5,tw-pad*2,tiles_h*.24),name,min(12,tiles_h*.18),muted)
            label(QRectF(box.x()+pad,box.y()+tiles_h*.30,tw-pad*2,tiles_h*.40),'%d%%'%round(value*100),min(24,tiles_h*.38),ink,QFont.DemiBold)
            bar(QRectF(box.x()+pad,box.bottom()-max(8,tiles_h*.14),tw-pad*2,min(o['bar_width'],max(4,tiles_h*.10))),value)

    else:
        standalone=style=='calendar_card';year=o.get('_calendar_year',now.year);month=o.get('_calendar_month',now.month)
        title_h=max(30,h*.14);header_top=max(42,h*.20);footer=max(20,h*.08)
        label(QRectF(m,8,w-(140 if standalone else 2*m),title_h),'%d 年 %d 月'%(year,month),min(22,h*.075),ink,QFont.DemiBold)
        if not standalone:label(QRectF(w*.62,8,w*.38-m,title_h),(period+' ' if period else '')+time_text,min(24,h*.095)*scale,accent,QFont.Bold,Qt.AlignRight|Qt.AlignVCenter)
        cw=(w-2*m)/7;ch=(h-header_top-footer-m)/7
        for i in range(7):label(QRectF(m+i*cw,header_top,cw,ch),weekdays[i],min(13,ch*.56),accent if i>=5 else muted,align=Qt.AlignCenter)
        first=datetime.date(year,month,1);first-=datetime.timedelta(days=first.weekday())
        for i in range(42):
            day=first+datetime.timedelta(days=i);r,c=divmod(i,7);box=QRectF(m+c*cw,header_top+(r+1)*ch,cw,ch);current=day==now.date();same=day.month==month
            if standalone and not same:continue
            if current:wash(box.adjusted(cw*.12,1,-cw*.12,-1),45,8)
            color=QColor(ink if same else muted)
            if not same:color.setAlpha(100)
            label(box,str(day.day),min(20,ch*.64),color,QFont.Bold if current else QFont.Medium,Qt.AlignCenter)
            working,name,known=day_info(day,o['work'])
            if same and (name not in ('工作日','休息日','每日班次')):
                mark=QColor('#b78c45' if working else '#c17590');mark.setAlpha(220);p.setPen(Qt.NoPen);p.setBrush(mark);p.drawEllipse(QPointF(box.center().x(),box.bottom()-2),1.6,1.6)
        label(QRectF(m,h-footer,w-2*m,footer*.85),'今天 · '+date+'  '+weekday,min(12,h*.04),muted,align=Qt.AlignCenter)
