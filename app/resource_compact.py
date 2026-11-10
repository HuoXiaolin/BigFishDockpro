"""Content-sized compact rows and an inexpensive perimeter-following halo."""
import time
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QFont,QFontMetrics,QPainterPath,QPen,QConicalGradient,QBrush,QTransform
from resource_status import metric_ink,metric_number
from resource_traffic import amount
from resource_quota import amount_text, quota_color, remaining_percent, used_percent
from resource_options import COMPACT_CLOCK_FORMATS,COMPACT_ROUTINES,component_location


STATUS_STEP=23
CLOCK_WIDTHS={'%H:%M':38,'%H:%M:%S':53,'%Y-%m-%d':64}
AI_ICON_SIZE = 16
AI_PADDING = 4
AI_GAP = 4
AI_TEXT_SIZE = 11


def text(p,rect,value,color,size=11,bold=False,align=Qt.AlignLeft):
    font=QFont(p.font());font.setPixelSize(size);font.setWeight(QFont.DemiBold if bold else QFont.Normal);p.setFont(font);p.setPen(QColor(color))
    p.drawText(rect,Qt.AlignVCenter|align,p.fontMetrics().elidedText(value,Qt.ElideRight,int(rect.width())))


def ring(p,rect,value,color,track,letter='',stroke=2.5):
    p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(track),stroke));p.drawEllipse(rect)
    if value is not None:
        p.setPen(QPen(QColor(color),stroke,Qt.SolidLine,Qt.RoundCap));p.drawArc(rect,90*16,-round(min(100,max(0,value))*3.6*16))
    if letter:text(p,rect,letter,color,10,True,Qt.AlignCenter)


def paint_halo(window,p):
    if not window.service.cfg['resource_halo']:return
    r=QRectF(window.rect()).adjusted(4.5,4.5,-4.5,-4.5)
    radius=(12 if window.service.cfg['resource_fold']=='bar' else r.height()/2) if window.service.compact else 17
    # Transform the colour field with the capsule's aspect ratio. Three path
    # strokes produce the full luminous ring, without hundreds of draw calls.
    key=(r.width(),r.height(),radius,window.liquid.radii(radius))
    if getattr(window,'halo_key',None)!=key:
        window.halo_path=window.liquid.shape(r,radius)
        window.halo_key=key
    p.setBrush(Qt.NoBrush);transform=QTransform();transform.translate(r.center().x(),r.center().y());transform.scale(r.width()/2,r.height()/2)
    for width,alpha in ((7,30),(4,65),(1.5,230)):
        gradient=QConicalGradient(QPointF(0,0),window.halo_phase*360)
        for i in range(7):gradient.setColorAt(i/6,QColor.fromHsvF((i/6)%1,.64,.98,alpha/255))
        brush=QBrush(gradient);brush.setTransform(transform);p.setPen(QPen(brush,width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.drawPath(window.halo_path)


def status_values(service):
    cfg=service.cfg
    if component_location(cfg,'resources')!='capsule':return []
    selected=cfg['resource_compact_metrics']
    latest=service.latest
    status=latest.get('system_status') or {}
    level,state=latest.get('battery',status.get('battery',(None,'unknown')))
    volume=latest.get('volume',status.get('volume'))
    connection=latest.get('connection',status.get('connection'))
    reading=service.sensors.values.get('brightness',{}) if service.sensors else {}
    brightness=reading.get('value')
    rows=(
        ('battery','充电中' if state=='charging' else '电池',f'{level}%' if level is not None else 'AC' if state=='ac' else '—',(level,state)),
        ('connection','网卡','—' if connection is None else connection or '未连接',connection),
        ('volume','音量','—' if volume is None else '静音' if volume[1] else f'{volume[0]}%',volume),
        ('brightness','亮度','—' if brightness is None else f'{brightness:.0f}%',brightness),
    )
    values=[row for row in rows if row[0] in selected and (row[2]!='—' or not cfg['resource_hide_unavailable'])] if cfg['resource_system_status'] else []
    if service.bluetooth and cfg['resource_bluetooth'] and 'bluetooth' in selected:
        group=service.bluetooth.group()
        label=' · '.join(row['name']+' '+('未报告' if row['level'] is None else f"{row['level']}%") for row in group)
        values.append(('bluetooth','蓝牙电量',label or service.bluetooth.status,group))
    return values


def compact_badges(service):
    cfg=service.cfg
    active=service.reminders()
    badges=list(active)
    seen={kind if kind in ('battery','water','agenda') else 'pomodoro' for kind,_ in active}
    selected=cfg['resource_compact_metrics']
    routine={}
    model=service.pomodoro
    if model and cfg['resource_pomodoro'] and component_location(cfg,'pomodoro')=='capsule':
        from resource_pomodoro import duration_text,water_amount
        if 'pomodoro' in selected and 'pomodoro' not in seen:
            phase,status,left,_=model.focus()
            kind=phase+'_done' if status=='done' else 'paused' if status=='paused' else phase
            routine['pomodoro']=(kind,'完成' if status=='done' else duration_text(left))
        if 'water' in selected and 'water' not in seen:
            _,ml,_,_,_=model.water()
            routine['water']=('water',water_amount(ml))
    if 'agenda' in selected and 'agenda' not in seen and cfg['resource_agenda'] and component_location(cfg,'agenda')=='capsule':
        agenda=service.agenda
        now=agenda.clock() if agenda else 0
        event=agenda.next_event(now) if agenda else None
        if event:
            from datetime import datetime
            starts=datetime.fromtimestamp(event['start'])
            stamp=starts.strftime('%H:%M' if starts.date()==datetime.fromtimestamp(now).date() else '%m/%d')
            when='进行中' if event['start']<=now else stamp
            routine['agenda']=('agenda',f"{when} · {event['title']}")
        else:routine['agenda']=('agenda','暂无日程')
    order=dict.fromkeys([*cfg['resource_compact_order'],*COMPACT_ROUTINES])
    badges.extend(routine[key] for key in order if key in routine)
    return badges,len(active)


def compact_values(window):
    cfg=window.service.cfg;bridge=window.service.deck
    resources=component_location(cfg,'resources')=='capsule'
    selected=cfg['resource_compact_metrics']
    values=list(getattr(window,'values',[])) if resources else []
    if cfg['resource_traffic'] and component_location(cfg,'traffic')=='capsule' and 'traffic' in selected:
        data=window.service.latest.get('traffic') or {}
        for key,label in [('day','今日流量'),('month','本月流量'),('year','本年流量')]:
            v=data.get(key);values.append(('traffic',label,amount(sum(v)) if v is not None else '—',''))
    if bridge and cfg['resource_ai'] and cfg['resource_compact_ai'] and component_location(cfg,'ai')=='capsule':
        for row in bridge.providers:
            metrics = row.get('quotas', [])
            quotas = [level for q in metrics if (level := used_percent(q)) is not None]
            remaining = remaining_percent(max(quotas, default=None))
            money = next((value for q in metrics if q.get('kind')!='spend' and (value := amount_text(q)) not in (None, '—')), None)
            value = money or (f'{remaining:.0f}%' if remaining is not None else '—')
            values.append(('ai',row['name'],value,dict(provider=row,remaining=remaining,money=bool(money))))
    track=(bridge.media.get('track') or {}) if bridge and cfg['resource_music'] and cfg['resource_compact_music'] and component_location(cfg,'music')=='capsule' else {}
    if track:values.append(('music','音乐',track.get('lyric') or track.get('title','') if cfg['resource_music_text']=='lyrics' else track.get('title',''),track))
    extra=window.service.extras
    if extra and cfg['resource_weather'] and cfg['resource_weather_compact'] and component_location(cfg,'weather')=='capsule':
        for row in extra.weather:
            if 'temperature' in row:values.append(('weather',row['name'],f"{row['temperature']:.0f}℃",row))
    return values


def cell_width(row,dense=False):
    key=row[0]
    if key=='ai':
        value_width = QFontMetrics(ai_value_font()).horizontalAdvance(row[2])
        return max(44, AI_ICON_SIZE + AI_PADDING * 2 + AI_GAP + value_width + 1)
    if key=='music':return 68 if dense else 96
    if key=='weather':return 60 if dense else 82
    if dense:
        return {'cpu':28,'gpu':28,'memory':30,'network':48}.get(key,50)
    if key in ('cpu','gpu','memory'):return 52
    if key=='network':return 104
    label=row[1] if len(row)>1 else ''
    font=QFont();font.setPixelSize(9);label_width=QFontMetrics(font).horizontalAdvance(label)
    template='999.99 W' if 'power' in key else '999 °C' if 'temp' in key else '9999 MHz' if 'freq' in key else '9999 RPM' if key.endswith(('fan','pump')) else '999.9 GB' if key in ('traffic','vram') else '999.99'
    font.setPixelSize(11);value_width=QFontMetrics(font).horizontalAdvance(template)
    return min(98,max(44,label_width,value_width)+2)


def cell_gap(dense):
    return 1.5 if dense else 3


def packed(values,available,dense=False):
    pages=[];row=[];used=0;gap=cell_gap(dense)
    for value in values:
        size=min(cell_width(value,dense),available)+(gap if row else 0)
        if row and used+size>available:pages.append(row);row=[];used=0;size=min(cell_width(value,dense),available)
        row.append(value);used+=size
    if row:pages.append(row)
    return pages


def plan(window,limit=None):
    key=(limit,window.width(),window.height(),window.offset)
    cached=getattr(window,'_compact_cache',None)
    if cached and cached[0]==key:return cached[1]
    result=_make_plan(window,limit);window._compact_cache=(key,result);return result


def badge_slots(window,items,capacity,limit,priority=False):
    font=QFont(window.font());font.setPixelSize(10);font.setWeight(QFont.DemiBold)
    metrics=QFontMetrics(font)
    slots=[]
    for index,(kind,label) in enumerate(items):
        if capacity<25:break
        text_width=metrics.horizontalAdvance(label)
        cap=int(limit*.20) if kind=='agenda' else 72
        budget=capacity-3
        if priority:
            others=(len(items)-index-1)*25
            budget=max(22,budget-others)
        width=min(budget,cap,max(44,text_width+25))
        slots.append((kind,label,width,text_width))
        capacity-=width+3
    return slots,capacity


def _make_plan(window,limit=None):
    cfg=window.service.cfg;max_width=limit or cfg['resource_compact_width']
    badges,active_count=compact_badges(window.service)
    values=compact_values(window)
    pinned_keys = cfg['resource_compact_pinned']
    order = cfg.get('resource_compact_order', [])
    if order:
        priority = {key: i for i, key in enumerate(order)}
        values.sort(key=lambda row: priority.get(row[0], len(priority)))
        pinned_keys = sorted(pinned_keys, key=lambda key: priority.get(key, len(priority)))
    requested=[row for key in pinned_keys for row in values if row[0]==key]
    # A city/provider group may rotate within its own pinned slot, while the
    # selected hardware readings remain stationary on every page.
    groups=[]
    for key in pinned_keys:
        rows=[row for row in requested if row[0]==key]
        if rows:groups.append(rows)
    extras=[row for row in values if row not in requested]
    dense=cfg['resource_compact_density']=='dense' or max_width<420 or window.height()<38
    wanted=lambda dense:sum(cell_width(g[0],dense) for g in groups)+cell_gap(dense)*max(0,len(groups)-1)
    if not dense and wanted(False)+16+(60 if extras else 0)>max_width:dense=True
    gap=cell_gap(dense)
    face_gap=4 if cfg['resource_face'] else 0
    face=min(round((30 if dense else 40)*cfg['resource_face_scale']/100),max_width-48-face_gap) if cfg['resource_face'] else 0
    capacity=max(0,max_width-16-face-face_gap)
    available=capacity
    active,capacity=badge_slots(window,badges[:active_count],capacity,max_width,priority=True)
    ordinary_floor=26 if values and not active else 0
    clock=COMPACT_CLOCK_FORMATS[cfg['resource_clock_format']][1] if cfg['resource_clock'] else ()
    clock_width=max((CLOCK_WIDTHS[pattern] for pattern in clock),default=0)
    if clock_width>capacity-ordinary_floor:clock=();clock_width=0
    capacity-=clock_width
    battery_alert=any(kind=='battery' for kind,_,_,_ in active)
    status=[row for row in status_values(window.service) if row[0]!='battery' or not battery_alert]
    status=status[:max(0,capacity-ordinary_floor)//STATUS_STEP]
    capacity-=len(status)*STATUS_STEP
    routine,spare=badge_slots(window,badges[active_count:],max(0,capacity-ordinary_floor),max_width)
    capacity=min(capacity,spare+ordinary_floor)
    tail=available-capacity
    pinned_groups=[];used=0
    # Leave one reachable supplemental slot. Never demote the entire core.
    for index,group in enumerate(groups):
        width=max(cell_width(row,dense) for row in group);cost=width+(gap if pinned_groups else 0)
        remainder=groups[index+1:]
        reserve=40+gap if extras or remainder else 0
        if used+cost+reserve<=capacity:
            pinned_groups.append(group);used+=cost
        else:extras.extend(group)
    room=capacity-used-(gap if used and extras else 0)
    pages=[('values',rows) for rows in packed(extras,room,dense)] if extras and room>=26 else [('values',[])]
    # LCM lets independent city/provider slots visit every combination of pages.
    from math import lcm
    count=lcm(len(pages),*(len(g) for g in pinned_groups)) if pinned_groups else len(pages)
    pages=(pages*((count+len(pages)-1)//len(pages)))[:count]
    pinned=[g[window.offset%len(g)] for g in pinned_groups]
    prefix=max((sum(min(cell_width(r,dense),room) for r in rows)+gap*max(0,len(rows)-1) for _,rows in pages),default=0)
    natural=16+face+face_gap+tail+used+(gap if used and prefix else 0)+min(prefix,room)
    from math import ceil
    return dict(width=min(max_width,max(96,ceil(natural))),pinned=pinned,pinned_widths=[max(cell_width(row,dense) for row in group) for group in pinned_groups],pages=pages,clock=clock,clock_width=clock_width,
                face=face,face_gap=face_gap,core=used,dense=dense,gap=gap,overflow=len(pinned_groups)<len(groups),
                active_badges=active,routine_badges=routine,status=status)


def natural_width(window,limit):
    return plan(window,limit)['width'] if window.service.cfg['resource_compact_auto_width'] else min(limit,window.service.cfg['resource_compact_width'])


def chip(p,rect,ink,light):
    tint=QColor(ink);tint.setAlpha(28 if light else 47)
    p.setPen(Qt.NoPen);p.setBrush(tint);p.drawRoundedRect(rect,7,7)


def ai_value_font():
    font = QFont()
    font.setPixelSize(AI_TEXT_SIZE)
    font.setWeight(QFont.DemiBold)
    return font


def paint_ai_quota(p, rect, value, meta, colors):
    from resource_provider_icons import paint_provider_mark

    chip(p, rect, colors['ink'], colors['light'])
    icon_size = min(AI_ICON_SIZE, rect.height() - 2)
    area = rect.adjusted(AI_PADDING + icon_size + AI_GAP, 0, -AI_PADDING, 0)
    font = ai_value_font()
    width = QFontMetrics(font).horizontalAdvance(value)
    if width > area.width():
        font.setPixelSize(max(8, int(AI_TEXT_SIZE * area.width() / width)))
    show_value = QFontMetrics(font).horizontalAdvance(value) <= area.width()
    x = rect.x() + AI_PADDING if show_value else rect.center().x() - icon_size / 2
    icon = QRectF(x, rect.center().y() - icon_size / 2, icon_size, icon_size)
    paint_provider_mark(p, icon, meta['provider'], colors['ink'])
    if show_value:
        ink = colors['ink'] if meta['money'] else quota_color(meta['remaining'], colors['light'])
        p.setFont(font)
        text(p, area, value, ink, font.pixelSize(), True)


def paint_content(window,p,rect,key,label,value,meta):
    c=window.colors;cfg=window.service.cfg;mid=rect.center().y()
    if key=='ai':
        paint_ai_quota(p,rect,value,meta,c)
        window.compact_providers.append(meta['provider']['id'])
        return
    mark=QRectF(rect.x()+4,mid-7,14,14)
    area=rect.adjusted(22,0,-4,0)
    if key=='weather':
        from resource_weather_style import compact_temperature_ink,paint_weather_icon
        ink=compact_temperature_ink(meta['temperature'],c['light'],cfg['resource_weather_thresholds'])
        chip(p,rect,ink,c['light']);paint_weather_icon(p,mark,meta,c['light'])
        if area.width()>=16:
            line=rect.height()/2
            text(p,QRectF(area.x(),rect.y(),area.width(),line),label,c['muted'],8)
            text(p,QRectF(area.x(),mid,area.width(),line),value,ink,10,True)
    else:
        ink='#285e85' if c['light'] else '#a2d7ff'
        chip(p,rect,ink,c['light'])
        playing=meta.get('state')=='Playing'
        x=mark.center().x()
        p.setPen(Qt.NoPen);p.setBrush(QColor(ink))
        if playing:
            for offset in (-3,1):p.drawRoundedRect(QRectF(x+offset,mid-4,2,8),.7,.7)
        else:
            symbol=QPainterPath(QPointF(x-3,mid-4));symbol.lineTo(x+4,mid);symbol.lineTo(x-3,mid+4);symbol.closeSubpath()
            p.drawPath(symbol)
        if cfg['resource_music_text']=='wave':
            levels=window.service.deck.levels if playing else ()
            count=min(15,max(0,int(area.width()/3)))
            p.setPen(QPen(QColor(ink),1.5,Qt.SolidLine,Qt.RoundCap))
            for i in range(count):
                level=levels[i*len(levels)//count] if levels else 0
                height=1+max(0,min(1,level))*5
                x=area.x()+1+i*3
                p.drawLine(QPointF(x,mid-height),QPointF(x,mid+height))
        elif area.width()>=16:text(p,area,value,c['ink'],10,True)
        window.compact_media=True


def paint_values(window,p,rows,x,mid,available,dense=False,widths=None):
    cfg=window.service.cfg;c=window.colors;bounds=[];gap=cell_gap(dense)
    short=window.height()<38;font_size=10 if dense else 11;label_y=mid-11 if short else mid-15;value_y=mid if short else mid-1
    label_height=12 if short else 14;value_height=12 if short else 17;label_font=8 if short else 9
    row_height=12;network_y=mid-11
    if window.height()<30:
        # A thin taskbar can leave less room than the desktop capsule minimum.
        row_height=max(5,(window.height()-8)//2)
        label_height=value_height=row_height;label_y=network_y=mid-row_height
        font_size=min(font_size,row_height);label_font=min(label_font,row_height)
    for index,(key,label,value,meta) in enumerate(rows):
        width=min(widths[index] if widths else cell_width((key,label,value,meta),dense),max(0,available))
        if width<26:break
        ink=c['ink'] if key in ('ai','music','weather','traffic') else metric_ink(window.service,key,c['light'],c['ink'])
        if key in ('ai','music','weather'):
            height=min(24,window.height()-6)
            paint_content(window,p,QRectF(x,mid-height/2,width,height),key,label,value,meta)
        elif key in ('cpu','gpu','memory') and not dense:
            if cfg['resource_compact_rings']:
                ring(p,QRectF(x,mid-8,16,16),metric_number(window.service,key),ink,c['hover'],{'cpu':'C','memory':'M','gpu':'G'}[key]);left=21
            else:text(p,QRectF(x,mid-8,20,16),{'cpu':'C','memory':'M','gpu':'G'}[key],c['muted'],9);left=15
            text(p,QRectF(x+left,mid-10,width-left,20),value,ink,11)
        elif key=='network':
            net=window.service.latest.get('network')
            from resource_charts import rate
            for i,arrow in enumerate(('↓','↑')):
                value=rate(net[i]).replace(' KB/s','K').replace(' MB/s','M').replace(' B/s','B') if net else '—'
                rect=QRectF(x,network_y+i*row_height,width,row_height) if dense else QRectF(x+i*width/2,mid-10,width/2-3,20)
                text(p,rect,arrow+' '+value,c['ink'],font_size)
        else:
            text(p,QRectF(x,label_y,width,label_height),label,c['muted'],label_font)
            text(p,QRectF(x,value_y,width,value_height),value,ink,font_size)
        bounds.append(QRectF(x,mid-(12 if short else 17),width,24 if short else 34));window.compact_shown.append(key)
        x+=width+gap;available-=width+gap
    return bounds


def paint_status(p,rect,row,colors):
    key,_,_,value=row
    center=rect.center()
    size=min(20,rect.height()-7)
    circle=QRectF(center.x()-size/2,center.y()-size/2,size,size)
    if key=='bluetooth':
        from bluetooth_gauge import draw_rings
        draw_rings(p,circle,value,not colors['light'])
        return
    if key=='battery':
        from resource_system_view import battery_icon,battery_ink
        level,state=value;ink=battery_ink(level,state,colors['light'],colors['muted'])
        track=ink if level==0 else colors['hover']
        ring(p,circle.adjusted(1,1,-1,-1),level,ink,track,stroke=1.65)
        battery_icon(p,center,state,ink)
        return
    light=colors['light']
    if key=='connection':
        ink=('#12796e' if light else '#83dece') if value else colors['muted']
        level=None
    elif key=='volume':
        ink=('#356899' if light else '#a1caff') if value and not value[1] else colors['muted']
        level=value[0] if value and not value[1] else None
    else:
        ink=('#986820' if light else '#ffd18b') if value is not None else colors['muted']
        level=value
    ring(p,circle.adjusted(1,1,-1,-1),level,ink,colors['hover'],stroke=1.65)
    p.save();p.translate(center)
    p.setPen(QPen(QColor(ink),1.2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    if key=='connection':
        p.drawArc(QRectF(-5.5,-4,11,8),43*16,94*16)
        p.drawArc(QRectF(-3.5,-1.5,7,5.5),43*16,94*16)
        p.drawPoint(QPointF(0,3))
        if value=='':p.drawLine(QPointF(-4,4),QPointF(4,-4))
    elif key=='volume':
        speaker=QPainterPath(QPointF(-5,-1.5));speaker.lineTo(-3,-1.5)
        speaker.lineTo(.5,-4.3);speaker.lineTo(.5,4.3);speaker.lineTo(-3,1.5)
        speaker.lineTo(-5,1.5);speaker.closeSubpath();p.drawPath(speaker)
        if value and value[1]:
            p.drawLine(QPointF(2.3,-1.7),QPointF(5.5,1.7));p.drawLine(QPointF(2.3,1.7),QPointF(5.5,-1.7))
        elif level:p.drawArc(QRectF(-2,-4,8,8),-47*16,94*16)
    else:
        p.drawEllipse(QPointF(),2.4,2.4)
        for ray in (QPointF(1,0),QPointF(0,1),QPointF(-1,0),QPointF(0,-1)):
            p.drawLine(ray*3.8,ray*5.4)
    p.restore()


def agenda_marquee(window):
    layout=plan(window,window.width())
    return next((label for kind,label,width,wanted in (*layout['active_badges'],*layout['routine_badges'])
                 if kind=='agenda' and width>=37 and wanted>width-23),'')


def paint_badges(window,p,slots,right,mid):
    from resource_pomodoro_view import reminder_icon,reminder_ink
    c=window.colors
    for kind,label,width,wanted in slots:
        rect=QRectF(right-width,mid-10,width,20)
        ink=reminder_ink(kind,c['light'])
        chip(p,rect,ink,c['light'])
        if width>=37:
            reminder_icon(p,QRectF(rect.left()+4,mid-6.5,13,13),kind,ink)
            area=rect.adjusted(20,1,-3,-1)
            if kind=='agenda' and label==window.marquee_title and wanted>area.width():
                font=QFont(window.font());font.setPixelSize(10);font.setWeight(QFont.DemiBold)
                metrics=QFontMetrics(font)
                span=wanted+20
                shift=(max(0.,time.monotonic()-window.marquee_since-.65)*32)%span
                baseline=mid+(metrics.ascent()-metrics.descent())/2
                p.save();p.setClipRect(area);p.setFont(font);p.setPen(QColor(ink))
                x=area.x()-shift
                p.drawText(QPointF(x,baseline),label);p.drawText(QPointF(x+span,baseline),label)
                p.restore()
            else:text(p,area,label,ink,10,True,Qt.AlignLeft if kind=='agenda' else Qt.AlignCenter)
        else:reminder_icon(p,QRectF(rect.center().x()-6.5,mid-6.5,13,13),kind,ink)
        window.reminder_bounds.append(rect);window.reminder_kinds.append(kind)
        right-=width+3
    return right


def paint_compact(window,p):
    cfg=window.service.cfg;c=window.colors;bridge=window.service.deck;mid=window.height()/2
    layout=plan(window,window.width());pages=layout['pages'];window.compact_pages=len(pages)
    _,rows=pages[window.offset%len(pages)];window.compact_shown=[];window.compact_providers=[];window.compact_media=False
    right=window.width()-8;left=8.;window.compact_bounds=[]
    if layout['face']:
        window.liquid.paint_face(p,QPointF(left+layout['face']/2,mid),layout['face']);left+=layout['face']+layout['face_gap']
    window.reminder_bounds=[];window.reminder_kinds=[];window.status_bounds={}
    if layout['active_badges']:right=paint_badges(window,p,layout['active_badges'],right,mid)
    clock=layout['clock'];width=layout['clock_width']
    if clock:
        now=time.localtime();line=min(20 if len(clock)==1 else 12,(window.height()-4)/len(clock))
        for i,pattern in enumerate(clock):
            date=pattern=='%Y-%m-%d' and len(clock)>1
            rect=QRectF(right-width+4,mid-line*len(clock)/2+i*line,width-4,line)
            text(p,rect,time.strftime(pattern,now),c['muted'] if date else c['ink'],min(9 if date else 11,int(line)),False,Qt.AlignRight)
        right-=width
    for row in reversed(layout['status']):
        right-=STATUS_STEP;rect=QRectF(right,0,STATUS_STEP,window.height())
        paint_status(p,rect,row,c);window.status_bounds[row[0]]=rect
    if layout['routine_badges']:right=paint_badges(window,p,layout['routine_badges'],right,mid)
    # Pins are anchored at the leading edge, so supplemental pages never move them.
    core=layout['core'];window.compact_bounds+=paint_values(window,p,layout['pinned'],left,mid,core,layout['dense'],layout['pinned_widths'])
    left+=core+(layout['gap'] if core and rows else 0)
    window.compact_bounds+=paint_values(window,p,rows,left,mid,max(0,right-left),layout['dense'])
    if bridge and bridge.alert_until>time.monotonic() and cfg['resource_quota_alert']:
        window.setAccessibleName(window.accessibleName().split('\n额度提示：')[0]+'\n额度提示：'+bridge.alert)


def paint_ball_reminder(window,p,rect):
    badges=window.service.reminders()
    if not badges:return
    from resource_pomodoro_view import reminder_icon,reminder_ink
    kind,_=badges[0]
    ink=QColor(reminder_ink(kind,window.colors['light']))
    p.setBrush(Qt.NoBrush);p.setPen(QPen(ink,2,Qt.SolidLine,Qt.RoundCap))
    p.drawArc(rect.adjusted(3.5,3.5,-3.5,-3.5),-9*16,77*16)
    if rect.width()>=36:
        mark=QRectF(rect.center().x()+4,rect.top()+3,13,13)
        p.setPen(Qt.NoPen);p.setBrush(QColor(window.colors['surface']));p.drawEllipse(mark)
        reminder_icon(p,mark.adjusted(1.5,1.5,-1.5,-1.5),kind,ink)
