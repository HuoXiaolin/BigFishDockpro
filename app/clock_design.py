"""All clock faces share clear typography, accent roles and responsive spacing."""
import math,calendar,datetime
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QPen,QFont,QLinearGradient
from clock_faces import next_countdown,orbit_items
from work_schedule import day_info


def draw(style,p,w,h,now,o,ink,muted,accent,text,time_text,period):
    scale=o['font_scale']/100;m=min(w,h)*o['padding']/100
    wide=o['layout']=='wide' or (o['layout']=='auto' and w>=h*1.4)
    compact=w<230 or h<145
    weekdays='一二三四五六日';date='%d月%d日'% (now.month,now.day);weekday='星期'+weekdays[now.weekday()]
    from appearance_presets import THEME_RINGS,THEME_ACCENTS,PROGRESS_COLORS,VIVID_BLUE,VIVID_GREEN,VIVID_RED
    family=o.get('material') if o.get('material') in THEME_RINGS else o.get('design')
    dopamine=family in THEME_RINGS and o.get('accent_color','') in ('',THEME_ACCENTS.get(family))
    progress_colors=((VIVID_BLUE,'#416fca'),(VIVID_GREEN,'#35b56a'),(VIVID_RED,'#e35260')) if family=='vivid' else PROGRESS_COLORS
    ring_colors=tuple(QColor(value) for value in THEME_RINGS[family]) if dopamine else (accent.lighter(120),accent)
    def wash(box,alpha=20,r=12,color=accent):
        c=QColor(color);c.setAlpha(alpha);p.setPen(Qt.NoPen);p.setBrush(c);p.drawRoundedRect(box,r,r)
    def label(box,value,size=12,color=muted,weight=QFont.Medium,align=Qt.AlignLeft|Qt.AlignVCenter):
        # Keep the header action inline, with a reserved slot outside text bounds.
        box=QRectF(box)
        if o.get('_header_controls') and box.top()<36 and box.right()>w-42:box.setRight(w-42)
        # Secondary information grows with the component instead of staying at
        # 10-12 px while the main time fills the entire card.
        size=max(size,12*min(1.35,max(.8,min(w/420,h/260))))
        return text(box,value,size,color,weight,align)
    def bar(box,ratio,period_index=None):
        pair=tuple(QColor(v) for v in progress_colors[period_index%3]) if dopamine and period_index is not None else ring_colors
        wash(box,48,box.height()/2,pair[1])
        if ratio and ratio>0:
            gradient=QLinearGradient(box.topLeft(),box.topRight());gradient.setColorAt(0,pair[0]);gradient.setColorAt(1,pair[1])
            p.setPen(Qt.NoPen);p.setBrush(gradient);p.drawRoundedRect(QRectF(box.x(),box.y(),box.width()*min(1,ratio),box.height()),box.height()/2,box.height()/2)
    if compact and style not in ('digital','calendar','orbit','month','calendar_card'):
        label(QRectF(m,m,w-2*m,h*.52),time_text,h*.42*scale,ink,QFont.Bold)
        if o['show_date']:label(QRectF(m,h*.68,w-2*m,h*.2),date+' · '+weekday,h*.13,muted)
        return
    if style=='digital':
        span=w-2*m
        if o['show_date']:label(QRectF(m,h*.12,span,h*.13),'周'+weekdays[now.weekday()]+' '+date,h*.08,muted)
        if period:label(QRectF(m,h*.12,span,h*.13),period,h*.07,muted,align=Qt.AlignRight)
        align=Qt.AlignCenter if o['align']=='center' else Qt.AlignLeft
        digits=label(QRectF(m,h*.27,span*.80,h*.36),time_text,min(span*.24,h*.40*scale),ink,QFont.DemiBold,align)
        second_width=max(16,min(span*.18,h*.23))
        label(QRectF(digits.right()+max(3,m*.3),digits.bottom()-h*.13,second_width,h*.14),
              f'{now.second:02d}',h*.14,muted,QFont.Medium)
        step=span/24;baseline=h*.76
        for i in range(24):
            tone=QColor(accent if i<=now.hour else ink)
            tone.setAlpha(255 if i==now.hour else 108 if i<now.hour else 33)
            height=h*(.14 if i==now.hour else .06)
            wash(QRectF(m+i*step,baseline-height,step*.76,height),tone.alpha(),min(3,step*.19),tone)
        for mark in (0,6,12,18,24):
            label(QRectF(m+span*mark/24-span*.045,h*.81,span*.09,h*.12),str(mark),h*.064,muted,
                  align=Qt.AlignCenter)
    elif style=='analog':
        diameter=min(h*.75,w*.43) if wide else min(w*.73,h*.63)
        cx=m+diameter/2 if wide else w/2;cy=h/2 if wide else m+diameter/2
        r=diameter/2;wash(QRectF(cx-r*1.05,cy-r*1.05,r*2.1,r*2.1),16,r*1.05)
        p.setBrush(Qt.NoBrush);edge=QColor(ink);edge.setAlpha(30);p.setPen(QPen(edge,max(1,r*.012)));p.drawEllipse(QPointF(cx,cy),r,r)
        for i in range(60):
            a=i*math.pi/30;major=i%5==0
            if i%15==0:continue
            c=QColor(ink if major else muted);c.setAlpha(220 if major else 115)
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
            wash(box,16,16);label(QRectF(box.x()+14,box.y()+box.height()*.10,box.width()-28,box.height()*.16),name,min(16,box.height()*.14),muted)
            label(QRectF(box.x()+8,box.y()+box.height()*.28,box.width()-16,box.height()*.59),value,box.height()*.56*scale,ink,QFont.Bold,Qt.AlignCenter)
    elif style=='calendar':
        from calendar_details import info as calendar_info
        today=now.date()
        span=w-2*m;head=min(46,h*.24)
        label(QRectF(m,m,span*.56,head),'%d 年 %d 月'%(now.year,now.month),min(23,head*.60),ink,QFont.DemiBold)
        label(QRectF(m+span*.58,m,span*.42,head),(period+' ' if period else '')+time_text,min(27,head*.66)*scale,ink,QFont.DemiBold,Qt.AlignRight)
        countdown=next_countdown(o['progress'],today)
        foot=max(15,min(24,h*.13)) if countdown else 0
        top=m+head+2
        height=max(1,h-top-m-foot)
        cell=span/7
        start=today-datetime.timedelta(days=today.weekday())
        for i in range(7):
            day=start+datetime.timedelta(days=i)
            box=QRectF(m+i*cell,top,cell-2,height)
            if day==today:wash(box,35,8)
            details=calendar_info(day,o['work'])
            color=accent if day==today else ink
            label(QRectF(box.x(),top,box.width(),height*.21),'周'+weekdays[i],min(13,cell*.31),muted,align=Qt.AlignCenter)
            label(QRectF(box.x(),top+height*.22,box.width(),height*.31),str(day.day),min(23,cell*.52),color,QFont.DemiBold,Qt.AlignCenter)
            lunar=details['lunar'] if o['show_lunar'] else ''
            holiday=details['name'] if o['show_holidays'] else ''
            if o['show_holidays']:
                _,schedule,_=day_info(day,o['work'])
                if details['makeup'] or schedule in ('调休上班','自定义上班'):holiday='调休班' if details['makeup'] else '上班'
                elif schedule=='自定义休息' and not holiday:holiday='休'
            if lunar:
                label(QRectF(box.x(),top+height*.54,box.width(),height*.20),lunar[:3],min(12,cell*.29),muted,align=Qt.AlignCenter)
            if holiday:
                label(QRectF(box.x(),top+height*(.75 if lunar else .57),box.width(),height*.21),holiday[:3],min(12,cell*.29),accent,align=Qt.AlignCenter)
        if countdown:
            label(QRectF(m,h-m-foot,span,foot),countdown,min(14,foot*.78),muted,QFont.DemiBold)
    elif style=='orbit':
        data,day_ratio,work_ratio=orbit_items(now,o)
        primary=data.get(o['progress']['primary'])
        rows=[data[key] for key in o['progress']['secondary']]
        tiles_h=max(29,h*(.23 if wide else .16)) if rows else 0
        tiles_top=h-m-tiles_h
        gap=max(4,m*.55)
        wide=wide or compact
        if wide:
            d=min(w*.37,tiles_top-2*m)
            x=m;y=(tiles_top-d)/2
            rx=x+d+gap*1.5;rw=w-rx-m
            date_h=0 if compact else min(28,h*.12)
            if date_h:
                label(QRectF(rx,m,rw*.58,date_h),date,h*.062,ink,QFont.DemiBold)
                label(QRectF(rx+rw*.59,m,rw*.41,date_h),weekday,h*.05,muted,align=Qt.AlignRight)
            top=m+date_h
            mainbox=QRectF(rx,top,rw,tiles_top-top-gap)
        else:
            d=min(w*.62,tiles_top*(.52 if primary else .82))
            x=(w-d)/2;y=m
            top=y+d+gap
            mainbox=QRectF(m,top,w-2*m,tiles_top-top-gap)
        ring=QRectF(x,y,d,d);stroke=min(o['ring_width'],d*.065)
        track=QColor(ring_colors[0]);track.setAlpha(55);p.setBrush(Qt.NoBrush);p.setPen(QPen(track,stroke,Qt.SolidLine,Qt.RoundCap));p.drawEllipse(ring)
        ratio=work_ratio if o['ring_mode']=='work' else day_ratio
        if ratio:
            g=QLinearGradient(ring.topLeft(),ring.bottomRight());g.setColorAt(0,ring_colors[0]);g.setColorAt(1,ring_colors[1])
            from PyQt5.QtGui import QBrush
            p.setPen(QPen(QBrush(g),stroke,Qt.SolidLine,Qt.RoundCap));p.drawArc(ring,90*16,-round(ratio*360*16))
        label(QRectF(x+d*.055,y+d*.26,d*.89,d*.40),time_text,d*.34*scale,ink,QFont.Bold,Qt.AlignCenter)
        title=(period+' · ' if period else '')+('下班' if o['ring_mode']=='work' else '今日')+' '+('休息日' if ratio is None else '%d%%'%round(ratio*100))
        if d>=68:label(QRectF(x+d*.10,y+d*.67,d*.80,d*.14),title,d*.08,muted,QFont.Medium,Qt.AlignCenter)
        if primary and not mainbox.isEmpty():
            name,value,detail,ratio=primary
            wash(mainbox,20,11)
            pad=min(11,mainbox.height()*.11);a=mainbox.adjusted(pad,pad,-pad,-pad)
            bh=min(o['bar_width'],max(2,a.height()*.07)) if ratio is not None else 0
            head=min(24,a.height()*.35);tail=min(17,a.height()*.21) if detail and a.height()>=57 else 0
            label(QRectF(a.x(),a.y(),a.width(),head),name,min(16,head*.9),muted,QFont.DemiBold)
            label(QRectF(a.x(),a.y()+head,a.width(),a.height()-head-tail-bh),value,
                  min(30,max(12,(a.height()-head-tail-bh)*.77)),ink,QFont.DemiBold)
            if tail:label(QRectF(a.x(),a.bottom()-tail-bh,a.width(),tail),detail,11,muted)
            if bh:bar(QRectF(a.x(),a.bottom()-bh,a.width(),bh),ratio)
        elif not mainbox.isEmpty() and (not wide or not date_h):
            label(mainbox,date+'  '+weekday,11,muted)
        tw=(w-2*m-gap*max(0,len(rows)-1))/max(1,len(rows))
        for i,(name,value,_,ratio) in enumerate(rows):
            box=QRectF(m+i*(tw+gap),tiles_top,tw,tiles_h);wash(box,14,11)
            pad=min(8,tw*.09)
            label(QRectF(box.x()+pad,box.y()+1,tw-pad*2,tiles_h*.34),name,min(14,tiles_h*.31),muted)
            label(QRectF(box.x()+pad,box.y()+tiles_h*.40,tw-pad*2,tiles_h*.41),value,min(22,tiles_h*.37),ink,QFont.DemiBold)
            if ratio is not None:
                bar(QRectF(box.x()+pad,box.bottom()-tiles_h*.13,tw-pad*2,min(o['bar_width'],max(2,tiles_h*.08))),ratio,i)

    else:
        standalone=style=='calendar_card';year=o.get('_calendar_year',now.year);month=o.get('_calendar_month',now.month)
        title_top=6;title_h=max(22,min(34,h*.10))
        m = min(m, w*.12)
        title_width = w - m - 122 if standalone else w*.60 - m
        title = '%d年%d月' % (year, month)
        label(QRectF(m,title_top,max(1,title_width),title_h),title,min(22,h*.075,w*.064),ink,QFont.DemiBold)
        if not standalone:label(QRectF(w*.62,title_top,w*.38-m,title_h),(period+' ' if period else '')+time_text,min(24,h*.095)*scale,accent,QFont.Bold,Qt.AlignRight|Qt.AlignVCenter)
        from calendar_details import info as calendar_info
        weeks=len(calendar.monthcalendar(year,month));weekday_h=min(22,max(15,h*.06));footer=max(14,min(22,h*.06));header_top=title_top+title_h+4
        cw=(w-2*m)/7;ch=(h-footer-m*.25-header_top-weekday_h)/weeks
        # Reserve a second line in ordinary compact cards, even in six-week
        # months. Only genuinely tiny clock faces fall back to day numbers.
        detail_row = (o['show_lunar'] or o['show_holidays']) and ch >= 25 and cw >= 26
        detail_height=max(10,min(14,ch*.36))
        marker_space=4 if o['show_holidays'] else 1
        for i in range(7):label(QRectF(m+i*cw,header_top,cw,weekday_h),weekdays[i],min(13,weekday_h*.65),accent if i>=5 else muted,align=Qt.AlignCenter)
        first=datetime.date(year,month,1);first-=datetime.timedelta(days=first.weekday())
        for i in range(weeks*7):
            try:day=first+datetime.timedelta(days=i)
            except OverflowError:continue
            r,c=divmod(i,7);box=QRectF(m+c*cw,header_top+weekday_h+r*ch,cw,ch);current=day==now.date();same=day.month==month
            if standalone and not same:continue
            if current:wash(box.adjusted(cw*.12,1,-cw*.12,-1),45,8)
            color=QColor(ink if same else muted)
            if not same:color.setAlpha(100)
            details=calendar_info(day,o['work']);marked=same and o['show_holidays'] and details['marker']
            subtitle=(details['name'] if o['show_holidays'] else '') or (details['lunar'] if o['show_lunar'] else '')
            if len(subtitle)>3:subtitle=subtitle[:2]+'…'
            p.save();p.setClipRect(box)
            day_height = ch-detail_height-marker_space if detail_row else max(1, ch - (6 if marked else 1))
            day_size = min(28, cw*.48, day_height*.9*scale)
            label(QRectF(box.x(),box.y(),cw,day_height),str(day.day),day_size,color,
                  QFont.Bold if current else o['font_weight'],Qt.AlignCenter)
            if detail_row and subtitle:
                label(QRectF(box.x()+2,box.y()+day_height,cw-4,detail_height),
                      subtitle,min(12,detail_height*.95),accent if marked else muted,QFont.Medium,Qt.AlignCenter)
            if marked:
                mark=QColor(accent);mark.setAlpha(230);p.setPen(Qt.NoPen);p.setBrush(mark);p.drawEllipse(QPointF(box.center().x(),box.bottom()-2),1.35,1.35)
            p.restore()
        known=calendar_info(datetime.date(year,month,1),o['work'])['known']
        footer_text='今天 · '+date+'  '+weekday
        if w >= 300 and o['show_holidays'] and not known:footer_text+=' · 本年假期未收录'
        label(QRectF(m,h-footer,w-2*m,footer*.85),footer_text,min(12,h*.04),muted,align=Qt.AlignCenter)
