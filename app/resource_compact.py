"""Content-sized compact rows and an inexpensive perimeter-following halo."""
from functools import lru_cache
from datetime import datetime
from math import atan2, degrees, tau
import time
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QFont,QFontMetrics,QPainter,QPainterPath,QPainterPathStroker,QPen,QPixmap,QConicalGradient,QBrush,QRegion,QTransform
from resource_status import connection_labels,metric_ink,metric_number
from resource_traffic import amount
from resource_quota import capsule_reading, ring_ink
from resource_options import COMPACT_CLOCK_FORMATS,COMPACT_ROUTINES,RESOURCE_READINGS,RUNNER_SLOT,SENSOR_UNITS,almanac_categories,compact_text_height,compact_tile_height,component_location
from capsule_order import clock_turn, has_component_order
from compact_clock import capsule_clock_width, capsule_headers, draw_clock, headers, lines_at
from compact_text import draw_stacked_text, readout_fonts
from spectrum_palettes import SPECTRUM_PALETTES


MAIL_STEP=23
AI_ICON_SIZE = 16
AI_RING_SIZE = 18
AI_PADDING = 4
AI_GAP = 4
AI_TEXT_SIZE = 11
CONTENT_TEXT_LEFT = 22
CONTENT_PADDING = 4
CONTENT_MIN_TEXT = 16
STACKED_MIN_WIDTH = CONTENT_TEXT_LEFT + CONTENT_MIN_TEXT + CONTENT_PADDING
STACKED_MAX_WIDTH = 82
MUSIC_MAX_WIDTH = 96
MUSIC_WAVE_BARS = 15
MUSIC_WAVE_STEP = 3
AGENDA_MAX_WIDTH = 80
MARQUEE_SPEED = 32
MARQUEE_GAP = 20
MARQUEE_START_PAUSE = .65
MARQUEE_LOOP_PAUSE = 5
READING_SAMPLES = {'traffic':'1023.99 GB','disk_activity':'100%', '°C':'199.9 °C','W':'999.99 W',
                   'V':'9.99 V','MHz':'9999 MHz','RPM':'19999 RPM','%':'100%'}


def text(p,rect,value,color,size=11,bold=False,align=Qt.AlignLeft):
    font=QFont(p.font());font.setPixelSize(size);font.setWeight(QFont.DemiBold if bold else QFont.Normal);p.setFont(font);p.setPen(QColor(color))
    p.drawText(rect,Qt.AlignVCenter|align,p.fontMetrics().elidedText(value,Qt.ElideRight,int(rect.width())))


def ring(p,rect,value,color,track,letter='',stroke=2.5):
    p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(track),stroke));p.drawEllipse(rect)
    if value is not None:
        p.setPen(QPen(QColor(color),stroke,Qt.SolidLine,Qt.RoundCap));p.drawArc(rect,90*16,-round(min(100,max(0,value))*3.6*16))
    if letter:text(p,rect,letter,color,10,True,Qt.AlignCenter)


HALO_RAINBOW = tuple(QColor.fromHsvF(i / 6, .64, .98) for i in range(6))


def halo_default_color(cfg, light):
    return cfg.get('theme_color') or ('#297bc9' if light else '#78c9ff')


@lru_cache(maxsize=len(SPECTRUM_PALETTES) + 1)
def halo_brushes(mode='rainbow'):
    preset = SPECTRUM_PALETTES.get(mode)
    colors = tuple(map(QColor, preset[1])) if preset else HALO_RAINBOW
    layers = []
    for width, alpha in ((7, 30), (4, 65), (1.5, 230)):
        gradient = QConicalGradient(QPointF(0, 0), 0)
        for i, color in enumerate((*colors, colors[0])):
            ink = QColor(color)
            ink.setAlpha(alpha)
            gradient.setColorAt(i / len(colors), ink)
        layers.append((width, QBrush(gradient)))
    return tuple(layers)


@lru_cache(maxsize=24)
def mono_halo_inks(value, light):
    from clock_legibility import blend, contrast
    color = QColor(value)
    surface = QColor('#eaf0f4' if light else '#24313b')
    low_contrast = contrast(color, surface) < 2.8
    relief = blend(color, QColor('black' if light else 'white'), .58) if low_contrast else color
    tip = blend(color, QColor('white'), .24)

    def opacity(ink, alpha):
        ink = QColor(ink)
        ink.setAlpha(alpha)
        return ink

    track = QPen(opacity(relief, 80), 1.25, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    layers = []
    strengths = (0., .36, 1., .97, .72, .39, .13, 0., 0.)
    for width, ink, highlight, alpha in ((7., relief, relief, 48), (3.8, relief, relief, 168 if low_contrast else 96),
                                          (1.8, color, tip, 248)):
        colors = tuple(opacity(blend(ink, highlight, strength**3), round(alpha * strength)) for strength in strengths)
        layers.append((width, colors))
    return track, tuple(layers)


def paint_mono_halo(window, painter, rect, transform, color, light):
    path, length = window.halo_path, window.halo_length
    if length <= 0 or rect.isEmpty():return
    track, layers = mono_halo_inks(color, light)
    painter.setPen(track)
    painter.drawPath(path)
    # Locate the head and falloff by distance along the actual rounded outline.
    # Map those points into one continuous gradient, including across the seam.
    lead, tail = min(7., length*.025), min(170., length*.32)
    head = (window.halo_phase % 1.) * length
    center = rect.center()
    angles = []
    for offset in (lead, lead*.45, 0., -tail*.08, -tail*.23, -tail*.45, -tail*.72, -tail):
        point = path.pointAtPercent(path.percentAtLength((head + offset) % length))
        angles.append(atan2((center.y()-point.y())/rect.height(), (point.x()-center.x())/rect.width()))
    start = angles[0]
    positions = [0., *((angle-start) % tau / tau for angle in angles[1:]), 1.]
    for width, colors in layers:
        gradient = QConicalGradient(QPointF(0,0), degrees(start) % 360.)
        gradient.setStops(list(zip(positions, colors)))
        brush = QBrush(gradient)
        brush.setTransform(transform)
        painter.setPen(QPen(brush, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)


def paint_halo(window,p,damage=None,fold=None):
    cfg = window.service.cfg
    if not cfg['resource_halo']:return
    r=QRectF(window.rect()).adjusted(4.5,4.5,-4.5,-4.5)
    radius=(12 if (fold or cfg['resource_fold'])=='bar' else r.height()/2) if window.service.compact else 17
    # Transform the colour field with the capsule's aspect ratio. Three path
    # strokes produce the full luminous ring, without hundreds of draw calls.
    key=(r.width(),r.height(),radius,window.liquid.radii(radius))
    if getattr(window,'halo_key',None)!=key:
        window.halo_path=window.liquid.shape(r,radius)
        window.halo_length=window.halo_path.length()
        window.halo_key=key
        stroke=QPainterPathStroker();stroke.setWidth(10);stroke.setJoinStyle(Qt.RoundJoin)
        window.halo_region=QRegion(stroke.createStroke(window.halo_path).toFillPolygon().toPolygon())
    if damage is not None and not damage.intersects(window.halo_region):return
    p.setBrush(Qt.NoBrush)
    transform = QTransform.fromTranslate(r.center().x(), r.center().y())
    transform.scale(r.width() / 2, r.height() / 2)
    mode = cfg.get('resource_halo_color_mode', 'rainbow')
    if mode == 'mono':
        light = window.colors['light']
        color = cfg.get('resource_halo_mono_color') or halo_default_color(cfg, light)
        paint_mono_halo(window,p,r,transform,color,light)
        return
    transform.rotate(-window.halo_phase * 360)
    for width, base in halo_brushes(mode):
        brush = QBrush(base)
        brush.setTransform(transform)
        p.setPen(QPen(brush, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(window.halo_path)


def halo_damage(window):
    """The animated stroke never needs to invalidate the cards inside it."""
    return getattr(window,'halo_region',QRegion(window.rect()))


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
        ('connection',*connection_labels(connection),connection),
        ('volume','音量','—' if volume is None else '静音' if volume[1] else f'{volume[0]}%',volume),
        ('brightness','亮度','—' if brightness is None else f'{brightness:.0f}%',brightness),
    )
    values=[row for row in rows if row[0] in selected and (row[2]!='—' or not cfg['resource_hide_unavailable'])] if cfg['resource_system_status'] else []
    if 'bluetooth' in selected and (cfg['resource_bluetooth'] or cfg.get('resource_peripheral_profiles')):
        from bluetooth_gauge import GROUP
        rows=service.battery_rows()
        label=' · '.join(f"{row['name']} {row['display_value']}" for row in rows)
        values.append(('bluetooth','外设电量',label or service.battery_status(),rows[:GROUP]))
    return values


def almanac_badge_lines(cfg):
    categories = almanac_categories(cfg)
    if not categories:
        return {}
    from datetime import date
    from calendar_almanac import almanac
    day = almanac(date.today())
    return day.badge_lines(categories) if day else {}


def compact_badges(service, almanac_page=0):
    cfg=service.cfg
    active=service.reminders()
    badges=list(active)
    focus_kinds={'focus','rest','focus_done','rest_done','paused'}
    seen={'pomodoro' if kind in focus_kinds else kind for kind,_ in active}
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
    if cfg['resource_alert_almanac']:
        labels = tuple(almanac_badge_lines(cfg))
        if labels:
            badge = ('almanac', labels[almanac_page % len(labels)])
            if 'almanac' in seen:
                badges = [badge if kind == 'almanac' else (kind, label) for kind, label in badges]
            else:
                badges.append(badge)
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
            reading=capsule_reading(row)
            value=(reading.amount or f'{reading.remaining:.0f}%') if reading else '—'
            values.append(('ai',row['name'],value,dict(provider=row,reading=reading)))
    track=(bridge.media.get('track') or {}) if bridge and cfg['resource_music'] and cfg['resource_compact_music'] and component_location(cfg,'music')=='capsule' else {}
    if track:values.append(('music','音乐',track.get('lyric') or track.get('title','') if cfg['resource_music_text']=='lyrics' else track.get('title',''),track))
    extra=window.service.extras
    if extra and cfg['resource_weather'] and cfg['resource_weather_compact'] and component_location(cfg,'weather')=='capsule':
        from resource_weather import compact_place_name
        for row in extra.weather:
            if 'temperature' in row:values.append(('weather',compact_place_name(row),f"{row['temperature']:.0f}℃",row))
    return values


def grouped_values(window):
    groups = {}
    for row in compact_values(window):
        key = 'resources' if row[0] in RESOURCE_READINGS else row[0]
        groups.setdefault(key, []).append(row)
    return groups


def visible_component_count(layout, key):
    if not layout:
        return 0
    if 'positions' in layout:
        placed = layout['positions'].get(key)
        if not placed or placed.width < (STACKED_MIN_WIDTH if key=='alert_almanac' else 26):
            return 0
    return layout['component_counts'].get(key,0)


@lru_cache(maxsize=256)
def reading_width(key,label,dense,panel_height,side):
    caption, value = readout_fonts(panel_height,dense)
    names, numbers = QFontMetrics(caption), QFontMetrics(value)
    if key=='network':
        column = numbers.horizontalAdvance('↑ 1023.9M') + 2
        return max(26,column if dense else 2*column+3)
    if key in ('cpu','gpu','memory'):
        if dense:
            # Keep the same slot when a percentage crosses 10 or reaches 100.
            return max(26,numbers.horizontalAdvance('100%')+1,names.horizontalAdvance(label)+1)
        return side+4+numbers.horizontalAdvance('100%')
    sample = READING_SAMPLES.get(SENSOR_UNITS.get(key,key),'999')
    return max(26,min(names.horizontalAdvance(label),caption.pixelSize()*9)+2,numbers.horizontalAdvance(sample)+2)


@lru_cache(maxsize=256)
def stacked_badge_width(title,value):
    font=QFont()
    font.setWeight(QFont.Normal);font.setPixelSize(8)
    title_width=QFontMetrics(font).horizontalAdvance(title)
    font.setWeight(QFont.DemiBold);font.setPixelSize(10)
    text_width=max(CONTENT_MIN_TEXT,title_width,QFontMetrics(font).horizontalAdvance(value))
    return min(STACKED_MAX_WIDTH,CONTENT_TEXT_LEFT+text_width+1+CONTENT_PADDING)


@lru_cache(maxsize=128)
def music_badge_width(value):
    # None is the fixed wave viewport; song and lyric excerpts fit their text.
    if value is None:
        return CONTENT_TEXT_LEFT+MUSIC_WAVE_BARS*MUSIC_WAVE_STEP+CONTENT_PADDING
    font=QFont();font.setPixelSize(10);font.setWeight(QFont.DemiBold)
    text_width=max(CONTENT_MIN_TEXT,QFontMetrics(font).horizontalAdvance(value))
    return min(MUSIC_MAX_WIDTH,CONTENT_TEXT_LEFT+text_width+1+CONTENT_PADDING)


def content_badge_width(row,cfg):
    key,place,value,meta=row
    if key=='ai':
        value_width = QFontMetrics(ai_value_font()).horizontalAdvance(value)
        reading=meta['reading']
        icon_size=AI_RING_SIZE if reading and reading.remaining is not None else AI_ICON_SIZE
        return max(44, icon_size + AI_PADDING * 2 + AI_GAP + value_width + 1)
    if key=='music':return music_badge_width(None if cfg['resource_music_text']=='wave' else value)
    return stacked_badge_width(place,value)


def cell_width(row,dense,window):
    key=row[0]
    if key in ('ai','weather','music'):return content_badge_width(row,window.service.cfg)
    width=reading_width(key,row[1],dense,window.height(),badge_height(window))
    if key not in ('cpu','gpu','memory','network'):
        actual=QFontMetrics(readout_fonts(window.height(),dense)[1]).horizontalAdvance(row[2])
        width=max(width,actual+2)
    return width


def cell_gap(dense):
    return 1.5 if dense else 3


def compact_face_width(cfg,height):
    base=min(30 if cfg['resource_compact_density']=='dense' else 40,max(16,height-5))
    return round(base*cfg['resource_face_scale']/100)


def packed(values,available,dense,window):
    pages=[];row=[];used=0;gap=cell_gap(dense)
    for value in values:
        width=min(cell_width(value,dense,window),available)
        size=width+(gap if row else 0)
        if row and used+size>available:pages.append(row);row=[];used=0;size=width
        row.append(value);used+=size
    if row:pages.append(row)
    return pages


def plan(window,limit=None):
    from datetime import date
    key=(limit,window.width(),window.height(),window.page_turns,window.service.cfg['resource_runner_enabled'],badge_height(window),
         date.today() if window.service.cfg['resource_alert_almanac'] or window.service.cfg['resource_clock'] else None)
    cached=getattr(window,'_compact_cache',None)
    if cached and cached[0]==key:return cached[1]
    result=_make_plan(window,limit);window._compact_cache=(key,result);return result


def readouts_changed(layout, previous, current, width):
    if 'positions' in layout:
        from capsule_order_layout import positions
        return layout['positions'] != positions(layout,current,width)
    pages = layout['pages']
    return (pages[previous.left % len(pages)] != pages[current.left % len(pages)]
            or any(group[previous.left % len(group)] != group[current.left % len(group)] for group in layout['pinned_groups']))


def badge_slots(window,items,capacity,limit,priority=False):
    font=QFont(window.font());font.setPixelSize(10);font.setWeight(QFont.DemiBold)
    metrics=QFontMetrics(font)
    slots=[]
    for index,(kind,label) in enumerate(items):
        if capacity<25:break
        if kind=='almanac':
            rows=almanac_badge_lines(window.service.cfg)
            natural=max((stacked_badge_width(*row) for row in rows.values()),default=stacked_badge_width(label,'今天'))
            text_width=natural-CONTENT_TEXT_LEFT-CONTENT_PADDING
        else:
            text_width=metrics.horizontalAdvance(label)
            cap=min(AGENDA_MAX_WIDTH,limit//5) if kind=='agenda' else 144 if kind in ('mail_new','quota_notice') else 110 if kind=='weather_notice' else 72
            natural=min(cap,max(44,text_width+25))
        budget=capacity-3
        if priority:
            others=(len(items)-index-1)*25
            budget=max(22,budget-others)
        width=min(budget,natural)
        slots.append((kind,label,width,text_width))
        capacity-=width+3
    return slots,capacity


def _make_plan(window,limit=None):
    cfg=window.service.cfg;max_width=limit or cfg['resource_compact_width']
    if has_component_order(cfg):
        from capsule_order_layout import make_plan
        return make_plan(window,max_width)
    badges,active_count=compact_badges(window.service,window.component_pages['alert_almanac'])
    values=grouped_values(window)
    hardware=values.get('resources', [])
    pinned_keys = list(dict.fromkeys('resources' if k in RESOURCE_READINGS else k for k in cfg['resource_compact_pinned']))
    if hardware and 'resources' not in pinned_keys:
        pinned_keys.append('resources')
    if 'traffic' in values and 'traffic' not in pinned_keys:
        pinned_keys.append('traffic')
    order = cfg.get('resource_compact_order', [])
    if order:
        priority = {key:i for i,key in enumerate(dict.fromkeys('resources' if k in RESOURCE_READINGS else k for k in order))}
        pinned_keys = sorted(pinned_keys, key=lambda key: priority.get(key, len(priority)))
    groups=[values[key] for key in pinned_keys if key in values]
    extras=[row for key,rows in values.items() if key not in pinned_keys for row in rows]
    dense=cfg['resource_compact_density']=='dense' or max_width<420 or window.height()<38
    if not dense:
        wanted=sum(max(cell_width(row,False,window) for row in group) for group in groups)
        wanted+=cell_gap(False)*max(0,len(groups)-1)
        if wanted+16+(60 if extras else 0)>max_width:dense=True
    gap=cell_gap(dense)
    clock=COMPACT_CLOCK_FORMATS[cfg['resource_clock_format']][1] if cfg['resource_clock'] else ()
    clock_width=capsule_clock_width(cfg,clock,window.height()) if clock else 0
    # Keep one readable supplemental slot even when a large bold date has to
    # share the minimum capsule width with a pinned reading.
    clock_room=max_width-16
    if values:clock_room-=26+(8 if cfg['resource_face'] else 0)
    if clock_room<20:clock=();clock_width=0
    else:clock_width=min(clock_width,clock_room)
    room=max(0,max_width-16-clock_width)
    value_floor=26 if values and room>=26 else 0
    runner_width=RUNNER_SLOT if cfg['resource_runner_enabled'] and room-value_floor>=RUNNER_SLOT else 0
    room-=runner_width
    mail_width=MAIL_STEP if cfg['resource_mail'] and cfg['resource_mail_icon'] and room-value_floor>=MAIL_STEP else 0
    room-=mail_width
    face=min(compact_face_width(cfg,window.height()),max(0,room-value_floor-4)) if cfg['resource_face'] else 0
    face_gap=4 if face else 0
    capacity=room-face-face_gap
    available=capacity+clock_width
    indicators=getattr(window.service,'indicators',None)
    # Changed devices get first use of spare space; leave room for a due reminder.
    budget=max(0,capacity-min(active_count*44,capacity//2))
    devices=indicators.cells(budget,window.height()) if indicators else []
    capacity-=sum(width+3 for _,_,width,_ in devices)
    active,capacity=badge_slots(window,badges[:active_count],capacity,max_width,priority=True)
    ordinary_floor=26 if values and not active else 0
    battery_alert=any(kind=='battery' for kind,_,_,_ in active)
    device_keys={key for key,_,_,_ in devices}
    status=[row for row in status_values(window.service) if row[0] not in device_keys and (row[0]!='battery' or not battery_alert)]
    status_width=badge_height(window)+3
    status=status[:max(0,capacity-ordinary_floor)//status_width]
    capacity-=len(status)*status_width
    routine,spare=badge_slots(window,badges[active_count:],max(0,capacity-ordinary_floor),max_width)
    if any(key=='almanac' for key,_ in badges) and not any(key=='almanac' and width>=STACKED_MIN_WIDTH for key,_,width,_ in (*active,*routine)):
        from capsule_order_layout import make_plan
        return make_plan(window,max_width)
    capacity=min(capacity,spare+ordinary_floor)
    tail=available-capacity
    pinned_groups=[];pinned_widths=[];used=0
    # Leave one reachable supplemental slot. Never demote the entire core.
    for index,group in enumerate(groups):
        width=max(cell_width(row,dense,window) for row in group);cost=width+(gap if pinned_groups else 0)
        remainder=groups[index+1:]
        reserve=40+gap if extras or remainder else 0
        if used+cost+reserve<=capacity:
            if group is hardware:
                group = [hardware[window.component_pages['resources'] % len(hardware)]]
            pinned_groups.append(group);pinned_widths.append(width);used+=cost
        elif group is hardware or group[0][0]=='traffic':
            # Use the component overflow layout so a narrow row can still reach
            # this card without putting its individual readings into other slots.
            from capsule_order_layout import make_plan
            return make_plan(window,max_width)
        else:extras.extend(group)
    room=capacity-used-(gap if used and extras else 0)
    pages=[('values',rows) for rows in packed(extras,room,dense,window)] if extras and room>=26 else [('values',[])]
    # Each slot gets to show every city, provider or calendar line before repeating.
    from math import lcm
    component_counts = {'resources':len(hardware)}
    if any(kind == 'almanac' and width >= STACKED_MIN_WIDTH for kind, _, width, _ in (*active, *routine)):
        component_counts['alert_almanac'] = len(almanac_badge_lines(cfg))
    periods = {'left':lcm(len(pages),*(len(g) for g in pinned_groups)), 'right':len(capsule_headers(cfg,clock)) if clock else 1}
    count=lcm(*periods.values())
    pages=(pages*((count+len(pages)-1)//len(pages)))[:count]
    pinned=[g[window.page_turns.left%len(g)] for g in pinned_groups]
    prefix=max((sum(min(cell_width(r,dense,window),room) for r in rows)+gap*max(0,len(rows)-1) for _,rows in pages),default=0)
    natural=16+face+face_gap+tail+runner_width+mail_width+used+(gap if used and prefix else 0)+min(prefix,room)
    from math import ceil
    return dict(width=min(max_width,max(96,ceil(natural))),pinned=pinned,pinned_groups=pinned_groups,
                pinned_widths=pinned_widths,pages=pages,clock=clock,clock_width=clock_width,
                bands=(('left','right'),),zone_periods=periods,component_counts=component_counts,
                face=face,face_gap=face_gap,core=used,dense=dense,gap=gap,overflow=len(pinned_groups)<len(groups),
                active_badges=active,routine_badges=routine,status=status,status_width=status_width,devices=devices,runner_width=runner_width,mail_width=mail_width)


def natural_width(window,limit):
    return plan(window,limit)['width'] if window.service.cfg['resource_compact_auto_width'] else min(limit,window.service.cfg['resource_compact_width'])


def notice_font(window):
    font=QFont(window.font())
    font.setPixelSize(12);font.setWeight(QFont.DemiBold)
    return font


def notice_width(window,notice,limit,height):
    if notice[0]=='almanac':
        rows=almanac_badge_lines(window.service.cfg).get(notice[1],(notice[1],'今天'))
        text_width=stacked_badge_width(*rows)-CONTENT_TEXT_LEFT-CONTENT_PADDING
    else:
        text_width=QFontMetrics(notice_font(window)).horizontalAdvance(notice[1])
    side = compact_tile_height(window.service.cfg,height)
    return min(limit,280,max(76,28+side+text_width))


def paint_notice(window,p,notice):
    from resource_pomodoro_view import reminder_icon,reminder_ink
    kind,label=notice
    colors=window.colors
    ink=reminder_ink(kind,colors['light'],window.service.low_battery() if kind=='battery' else None)
    side=badge_height(window)
    tile=QRectF(8,(window.height()-side)/2,side,side)
    chip(p,tile,ink,colors['light'])
    icon=QRectF(0,0,min(15,side),min(15,side));icon.moveCenter(tile.center())
    reminder_icon(p,icon,kind,ink)
    area=QRectF(window.rect()).adjusted(tile.right()+6,0,-9,0)
    if kind=='almanac':
        rows=almanac_badge_lines(window.service.cfg).get(label,(label,'今天'))
        paint_badge_lines(p,QRectF(area.x(),tile.y(),area.width(),side),*rows,colors['muted'],ink)
    else:
        p.setFont(notice_font(window));p.setPen(QColor(colors['ink']))
        p.drawText(area,Qt.AlignLeft|Qt.AlignVCenter,p.fontMetrics().elidedText(label,Qt.ElideRight,max(0,int(area.width()))))
    window.reminder_kinds=[kind];window.reminder_bounds=[QRectF(window.rect())]
    window.status_bounds={};window.compact_ai_hits=[];window.compact_bounds=[];window.compact_shown=[]


def chip(p,rect,ink,light):
    tint=QColor(ink);tint.setAlpha(28 if light else 47)
    p.setPen(Qt.NoPen);p.setBrush(tint);p.drawRoundedRect(rect,7,7)


def badge_height(window):
    return compact_tile_height(window.service.cfg,window.height())


def ai_value_font():
    font = QFont()
    font.setPixelSize(AI_TEXT_SIZE)
    font.setWeight(QFont.DemiBold)
    return font


@lru_cache(maxsize=128)
def fitted_ai_font(value,room):
    if room<=0 or not value:return None
    font=ai_value_font()
    width=QFontMetrics(font).horizontalAdvance(value)
    if width>room:
        font.setPixelSize(max(8,int(AI_TEXT_SIZE*room/width)))
        if QFontMetrics(font).horizontalAdvance(value)>room:return None
    return font


def paint_quota_ring(p, rect, reading, light):
    from resource_status import draw_tray_rings
    ink=ring_ink(reading.remaining,reading.stale,light)
    portions=(reading.daily.in_window,) if reading.daily else ()
    draw_tray_rings(p,rect,[(reading.remaining,ink,reading.stale)],dark=not light,used_today=portions,compact=True)
    return ink


def paint_ai_quota(p, rect, value, meta, colors):
    from resource_provider_icons import paint_provider_mark

    chip(p, rect, colors['ink'], colors['light'])
    reading=meta['reading']
    has_ring=reading is not None and reading.remaining is not None
    icon_size = min(AI_RING_SIZE if has_ring else AI_ICON_SIZE,rect.width(),rect.height()-2)
    area = rect.adjusted(AI_PADDING + icon_size + AI_GAP, 0, -AI_PADDING, 0)
    font = fitted_ai_font(value,area.width())
    x = rect.x() + AI_PADDING if font is not None else rect.center().x() - icon_size / 2
    icon = QRectF(x, rect.center().y() - icon_size / 2, icon_size, icon_size)
    ink=colors['ink']
    if has_ring:
        ink=paint_quota_ring(p,icon,reading,colors['light'])
        inset=icon_size*.175
        icon=icon.adjusted(inset,inset,-inset,-inset)
    paint_provider_mark(p, icon, meta['provider'], colors['ink'])
    if font is not None:
        p.setFont(font)
        text(p, area, value, ink, font.pixelSize(), True)


def paint_music_wave(window,p,area,ink,playing):
    levels=window.service.deck.levels if playing and window.service.deck else ()
    count=min(MUSIC_WAVE_BARS,max(0,int(area.width()/MUSIC_WAVE_STEP)))
    p.setPen(QPen(QColor(ink),1.5,Qt.SolidLine,Qt.RoundCap))
    for i in range(count):
        level=levels[i*len(levels)//count] if levels else 0
        height=1+max(0,min(1,level))*5
        x=area.x()+1+i*MUSIC_WAVE_STEP;mid=area.center().y()
        p.drawLine(QPointF(x,mid-height),QPointF(x,mid+height))


def content_badge_rect(slot,row,cfg):
    # The slot reserves the longest page; only paint and activate the current badge.
    key=row[0]
    natural=content_badge_width(row,cfg)
    width=min(slot.width(),natural)
    height=slot.height()
    if key=='ai':
        reading=row[3]['reading']
        icon_size=min(AI_RING_SIZE if reading and reading.remaining is not None else AI_ICON_SIZE,height-2)
        show_text=width>=natural or fitted_ai_font(row[2],width-icon_size-2*AI_PADDING-AI_GAP) is not None
    else:
        show_text=width>=CONTENT_TEXT_LEFT+CONTENT_MIN_TEXT+CONTENT_PADDING
    if not show_text:
        width=height=min(width,height)
    zone=cfg.get('resource_compact_zones',{}).get(key,'left')
    spare=slot.width()-width
    offset=spare if zone=='right' else spare/2 if zone=='center' else 0
    return QRectF(slot.x()+offset,slot.center().y()-height/2,width,height)


def paint_badge_lines(p,area,title,value,muted,ink):
    if area.width()<CONTENT_MIN_TEXT:return
    p.setFont(QFont())
    line=area.height()/2
    text(p,QRectF(area.x(),area.y(),area.width(),line),title,muted,max(1,min(8,int(line))))
    text(p,QRectF(area.x(),area.center().y(),area.width(),line),value,ink,max(1,min(10,int(line))),True)


def paint_content(window,p,rect,key,label,value,meta,overlays=None):
    c=window.colors;cfg=window.service.cfg;mid=rect.center().y()
    if key=='ai':
        paint_ai_quota(p,rect,value,meta,c)
        return
    if key=='weather':
        from resource_weather_style import compact_temperature_ink,paint_weather_icon
        area=rect.adjusted(CONTENT_TEXT_LEFT,0,-CONTENT_PADDING,0)
        size=min(14,rect.width(),rect.height())
        mark=QRectF(rect.x()+CONTENT_PADDING,mid-size/2,size,size)
        if area.width()<CONTENT_MIN_TEXT:
            mark.moveCenter(rect.center())
        ink=compact_temperature_ink(meta['temperature'],c['light'],cfg['resource_weather_thresholds'])
        chip(p,rect,ink,c['light']);paint_weather_icon(p,mark,meta,c['light'])
        paint_badge_lines(p,area,label,value,c['muted'],ink)
    else:
        area=rect.adjusted(CONTENT_TEXT_LEFT,0,-CONTENT_PADDING,0)
        ink='#285e85' if c['light'] else '#a2d7ff'
        chip(p,rect,ink,c['light'])
        playing=meta.get('state')=='Playing'
        x=rect.x()+11 if area.width()>=CONTENT_MIN_TEXT else rect.center().x()
        p.setPen(Qt.NoPen);p.setBrush(QColor(ink))
        if playing:
            for offset in (-3,1):p.drawRoundedRect(QRectF(x+offset,mid-4,2,8),.7,.7)
        else:
            symbol=QPainterPath(QPointF(x-3,mid-4));symbol.lineTo(x+4,mid);symbol.lineTo(x-3,mid+4);symbol.closeSubpath()
            p.drawPath(symbol)
        if area.width()<CONTENT_MIN_TEXT:return
        if cfg['resource_music_text']=='wave':
            if overlays is None:paint_music_wave(window,p,area,ink,playing)
            else:overlays.append(('wave',area,ink,playing))
        else:
            p.setFont(QFont())
            text(p,area,value,c['ink'],10,True)


def paint_values(window,p,rows,x,mid,available,dense=False,widths=None,clip=None,overlays=None):
    cfg=window.service.cfg;c=window.colors;bounds=[];gap=cell_gap(dense)
    side=badge_height(window)
    height=compact_text_height(cfg,window.height())
    caption,primary=readout_fonts(window.height(),dense)
    for index,row in enumerate(rows):
        key,label,value,meta=row
        width=min(widths[index] if widths else cell_width(row,dense,window),max(0,available))
        if width<26:break
        ink=c['ink'] if key in ('ai','music','weather','traffic') else metric_ink(window.service,key,c['light'],c['ink'])
        hit=QRectF(x,mid-height/2,width,height)
        if key in ('ai','music','weather'):
            hit=content_badge_rect(QRectF(x,mid-side/2,width,side),row,cfg)
            paint_content(window,p,hit,key,label,value,meta,overlays)
        elif key in ('cpu','gpu','memory') and not dense and width>=side+2+QFontMetrics(primary).horizontalAdvance(value):
            letter={'cpu':'C','memory':'M','gpu':'G'}[key]
            if cfg['resource_compact_rings']:
                p.save()
                p.translate(x+side/2,mid);p.scale(side/20,side/20)
                ring(p,QRectF(-8,-8,16,16),metric_number(window.service,key),ink,c['hover'],letter)
                p.restore()
                left=side+2
            else:
                left=QFontMetrics(caption).horizontalAdvance(letter)+3
                p.setFont(caption)
                text(p,QRectF(x,hit.top(),left,height),letter,c['muted'],caption.pixelSize())
            p.setFont(primary)
            text(p,hit.adjusted(left,0,0,0),value,ink,primary.pixelSize())
        elif key=='network':
            net=window.service.latest.get('network')
            from resource_charts import rate
            rates=[]
            for arrow,direction in (('↑',1),('↓',0)):
                speed=rate(net[direction]).replace(' KB/s','K').replace(' MB/s','M').replace(' B/s','B') if net else '—'
                rates.append(arrow+' '+speed)
            if dense or width<2*max(QFontMetrics(primary).horizontalAdvance(s) for s in rates)+3:
                draw_stacked_text(p,hit,rates,(ink,ink),'rates',(primary,primary))
            else:
                p.setFont(primary)
                for i,speed in enumerate(rates):
                    text(p,QRectF(x+i*(width+3)/2,hit.top(),(width-3)/2,height),speed,ink,primary.pixelSize())
        else:
            draw_stacked_text(p,hit,(label,value),(c['muted'],ink),'reading',(caption,primary))
        if clip is not None:
            hit = hit.intersected(clip)
        if not hit.isEmpty():
            bounds.append(hit)
            window.compact_shown.append(key)
            if key=='ai':
                window.compact_providers.append(meta['provider']['id'])
                if meta['reading'] is not None:window.compact_ai_hits.append((hit,meta['reading']))
            elif key=='music':
                window.compact_media=True
        x+=width+gap;available-=width+gap
    return bounds


def paint_status(window,p,row,x,width,mid):
    side=badge_height(window)
    rect=QRectF(x,mid-side/2,width,side)
    hit=rect.intersected(QRectF(window.rect()))
    if hit.isEmpty():return
    scale=min(width,side)/20
    p.save()
    p.translate(rect.center())
    p.scale(scale,scale)
    draw_status_icon(p,row,window.colors)
    p.restore()
    window.status_bounds[row[0]]=hit


def draw_status_icon(p,row,colors):
    key,_,_,value=row
    center=QPointF()
    circle=QRectF(-10,-10,20,20)
    if key=='bluetooth':
        from bluetooth_gauge import draw_peripheral_rings
        draw_peripheral_rings(p,circle,value,not colors['light'])
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
        from capsule_indicators import draw_volume_speaker
        draw_volume_speaker(p,value,2.4)
    else:
        from capsule_indicators import draw_brightness_sun
        draw_brightness_sun(p,level,2.4)
    p.restore()


def agenda_marquee(window):
    layout=plan(window,window.width())
    return next(((label, wanted + MARQUEE_GAP)
                 for kind,label,width,wanted in (*layout['active_badges'],*layout['routine_badges'])
                 if kind=='agenda' and width>=37 and wanted>width-23), ('', 0))


def marquee_frame(elapsed, span):
    """Return the fractional position and the time until motion resumes."""
    elapsed -= MARQUEE_START_PAUSE
    if elapsed < 0:
        return 0., -elapsed
    travel = span / MARQUEE_SPEED
    cycle = travel + MARQUEE_LOOP_PAUSE
    phase = elapsed % cycle
    if phase >= travel:
        return 0., cycle - phase
    return phase * MARQUEE_SPEED, 0.


def paint_marquee(window,p,area,label,ink,span):
    font=QFont(window.font());font.setPixelSize(10);font.setWeight(QFont.DemiBold)
    metrics=QFontMetrics(font)
    shift,_=marquee_frame(time.monotonic()-window.marquee_since,span)
    baseline=area.center().y()+(metrics.ascent()-metrics.descent())/2
    p.save();p.setClipRect(area,Qt.IntersectClip);p.setFont(font);p.setPen(QColor(ink))
    x=area.x()-shift
    p.drawText(QPointF(x,baseline),label)
    if x+span<area.right():p.drawText(QPointF(x+span,baseline),label)
    p.restore()


def paint_badges(window,p,slots,right,mid,overlays=None):
    from resource_pomodoro_view import reminder_icon,reminder_ink
    c=window.colors;height=badge_height(window)
    for kind,label,width,wanted in slots:
        rect=QRectF(right-width,mid-height/2,width,height)
        show_text=width>=(STACKED_MIN_WIDTH if kind=='almanac' else 37)
        if not show_text:
            side=min(width,height)
            rect=QRectF(rect.center().x()-side/2,mid-side/2,side,side)
        level=window.service.low_battery() if kind=='battery' else None
        ink=reminder_ink(kind,c['light'],level)
        chip(p,rect,ink,c['light'])
        if kind=='almanac' and show_text:
            size=min(14,rect.height())
            reminder_icon(p,QRectF(rect.x()+CONTENT_PADDING,mid-size/2,size,size),kind,ink)
            rows=almanac_badge_lines(window.service.cfg).get(label,(label,'今天'))
            paint_badge_lines(p,rect.adjusted(CONTENT_TEXT_LEFT,0,-CONTENT_PADDING,0),*rows,c['muted'],ink)
        elif show_text:
            reminder_icon(p,QRectF(rect.left()+4,mid-6.5,13,13),kind,ink)
            area=rect.adjusted(20,1,-3,-1)
            if kind=='agenda' and label==window.marquee_title and wanted>area.width():
                if overlays is None:paint_marquee(window,p,area,label,ink,wanted+MARQUEE_GAP)
                else:overlays.append(('marquee',area,label,ink,wanted+MARQUEE_GAP))
            else:text(p,area,label,ink,10,True,Qt.AlignLeft if kind=='agenda' else Qt.AlignCenter)
        else:
            size=min(13,rect.width())
            reminder_icon(p,QRectF(rect.center().x()-size/2,mid-size/2,size,size),kind,ink)
        window.reminder_bounds.append(rect);window.reminder_kinds.append(kind)
        right-=width+3
    return right


def paint_rolling_values(window,p,layout,rows,left,right,mid,scroll):
    previous, progress, direction = scroll
    previous = previous.left
    clip = QRectF(left,2,max(0,right-left),window.height()-4)
    distance = clip.height() * direction
    eased = progress * progress * (3 - 2 * progress)
    outgoing, incoming = mid - distance * eased, mid + distance * (1 - eased)
    dense = layout['dense']

    def draw(current, before, x, space, widths=None):
        if before == current:
            window.compact_bounds.extend(paint_values(window,p,current,x,mid,space,dense,widths))
        else:
            window.compact_bounds.extend(paint_values(window,p,before,x,outgoing,space,dense,widths,clip))
            window.compact_bounds.extend(paint_values(window,p,current,x,incoming,space,dense,widths,clip))

    p.save()
    p.setClipRect(clip,Qt.IntersectClip)
    try:
        for group, row, width in zip(layout['pinned_groups'], layout['pinned'], layout['pinned_widths']):
            draw((row,), (group[previous % len(group)],), left, width, (width,))
            left += width + layout['gap']
        pages = layout['pages']
        draw(rows, pages[previous % len(pages)][1], left, max(0,right-left))
    finally:
        p.restore()


def paint_compact_body(window,p,layout,scroll=None,overlays=None):
    cfg=window.service.cfg;c=window.colors;bridge=window.service.deck;mid=window.height()/2
    pages=layout['pages'];window.compact_pages=len(pages)
    window.compact_shown=[];window.compact_providers=[];window.compact_ai_hits=[];window.compact_media=False
    window.compact_bounds=[];window.reminder_bounds=[];window.reminder_kinds=[];window.status_bounds={}
    if bridge and bridge.alert_until>time.monotonic() and cfg['resource_quota_alert']:
        window.setAccessibleName(window.accessibleName().split('\n额度提示：')[0]+'\n额度提示：'+bridge.alert)
    if 'positions' in layout:
        from capsule_order_layout import paint_page
        paint_page(window,p,layout,scroll,overlays)
        return
    _,rows=pages[window.page_turns.left%len(pages)]
    right=window.width()-8;left=8.+layout['face']+layout['face_gap']
    clock=layout['clock'];width=layout['clock_width']
    if clock:
        right-=width
        paint_clock(window,p,clock,right,width,mid,window.page_turns.right)
    right-=layout['runner_width']
    if layout['active_badges']:right=paint_badges(window,p,layout['active_badges'],right,mid,overlays)
    if layout['devices']:
        right-=sum(width+3 for _,_,width,_ in layout['devices'])
        window.service.indicators.paint(p,layout['devices'],right,mid,c)
    if layout['mail_width']:
        right-=layout['mail_width']
        paint_mail_status(window,p,QRectF(right,0,layout['mail_width'],window.height()))
    for row in reversed(layout['status']):
        right-=layout['status_width']
        paint_status(window,p,row,right,layout['status_width'],mid)
    if layout['routine_badges']:right=paint_badges(window,p,layout['routine_badges'],right,mid,overlays)
    if scroll:
        if overlays is None:paint_rolling_values(window,p,layout,rows,left,right,mid,scroll)
        else:overlays.append(('scroll',QRectF(left,2,max(0,right-left),window.height()-4),rows))
    else:
        core=layout['core'];window.compact_bounds+=paint_values(window,p,layout['pinned'],left,mid,core,layout['dense'],layout['pinned_widths'],overlays=overlays)
        left+=core+(layout['gap'] if core and rows else 0)
        window.compact_bounds+=paint_values(window,p,rows,left,mid,max(0,right-left),layout['dense'],overlays=overlays)


def paint_clock(window,p,clock,x,width,mid,turn=None):
    height = compact_text_height(window.service.cfg,window.height())
    draw_clock(p,QRectF(x,mid-height/2,width,height),clock_rows(window,clock,turn),window.colors['muted'],window.colors['ink'])


def clock_rows(window, clock, turn=None):
    now = datetime.now()
    if turn is None:turn=clock_turn(plan(window,window.width()),window.page_turns)
    return lines_at(now,headers(window.service.cfg,'resource_clock_',clock,now.date()),clock[1],turn)


def paint_compact(window,p,scroll=None,damage=None):
    """Keep one bounded layer of stationary labels, with live motion above it."""
    cached=getattr(window,'_compact_surface',None)
    plan_cache=getattr(window,'_compact_cache',None)
    if (cached and plan_cache and cached[0] is plan_cache[1] and not scroll and damage is not None
            and cached[0]['runner_width'] and window.service.runners.get('capsule')):
        from resource_runner import capsule_rect
        if capsule_rect(window).contains(damage.boundingRect()):
            # The runner has its own slot. Restore its background without advancing other animations.
            p.drawPixmap(QPointF(),cached[2])
            return
    layout=plan(window,window.width())
    dpr=window.devicePixelRatioF()
    stamp=clock_rows(window,layout['clock'],clock_turn(layout,window.page_turns)) if layout['clock'] else ()
    key=(window.size(),dpr,window.font().key(),tuple(window.colors.items()),
         badge_height(window),stamp,window.marquee_title,bool(scroll))
    if not cached or cached[0] is not layout or cached[1]!=key:
        overlays=[]
        # A huge user-resized/DPI-scaled capsule should not retain a huge bitmap.
        if window.width()*window.height()*dpr*dpr>512*1024 or scroll and 'positions' in layout:
            window._compact_surface=None
            paint_compact_body(window,p,layout,scroll,overlays)
        else:
            image=QPixmap(max(1,round(window.width()*dpr)),max(1,round(window.height()*dpr)))
            image.setDevicePixelRatio(dpr);image.fill(Qt.transparent)
            painter=QPainter(image);painter.setRenderHints(p.renderHints());painter.setFont(window.font())
            try:paint_compact_body(window,painter,layout,scroll,overlays)
            finally:painter.end()
            window._compact_surface=cached=(layout,key,image,overlays)
    else:overlays=cached[3]
    if window._compact_surface:
        p.drawPixmap(QPointF(),cached[2])
    for kind,area,*args in overlays:
        if kind=='wave':paint_music_wave(window,p,area,*args)
        elif kind=='marquee':paint_marquee(window,p,area,*args)
        elif kind=='scroll':
            window.compact_bounds=[];window.compact_shown=[];window.compact_providers=[];window.compact_ai_hits=[];window.compact_media=False
            paint_rolling_values(window,p,layout,args[0],area.left(),area.right(),window.height()/2,scroll)
    if layout['face']:
        x = layout['positions']['face'].x if 'positions' in layout else 8
        window.liquid.paint_face(p,QPointF(x+layout['face']/2,window.height()/2),layout['face'])


def ball_details(window,limit,height=None):
    room=max(0,limit-38-(RUNNER_SLOT if window.service.cfg['resource_runner_enabled'] else 0))
    timers=[item for item in window.service.reminders() if item[0] in ('stopwatch','stopwatch_paused','alarm','alarm_due')]
    badges,left=badge_slots(window,timers,room,limit,priority=True)
    indicators=getattr(window.service,'indicators',None)
    cells=indicators.cells(left,window.height() if height is None else height) if indicators else []
    return cells,badges,room-left+sum(width+3 for _,_,width,_ in cells)


def paint_ball_reminder(window,p,rect):
    badges=window.service.reminders()
    if not badges:return
    from resource_pomodoro_view import reminder_icon,reminder_ink
    kind,_=badges[0]
    level=window.service.low_battery() if kind=='battery' else None
    ink=QColor(reminder_ink(kind,window.colors['light'],level))
    p.setBrush(Qt.NoBrush);p.setPen(QPen(ink,2,Qt.SolidLine,Qt.RoundCap))
    p.drawArc(rect.adjusted(3.5,3.5,-3.5,-3.5),-9*16,77*16)
    if rect.width()>=36 or kind in ('mail_code','weather_notice'):
        if kind in ('mail_code','weather_notice'):
            size=min(13,max(8,rect.width()*.36))
            mark=QRectF(rect.right()-size-3,rect.top()+3,size,size)
        else:
            mark=QRectF(rect.center().x()+4,rect.top()+3,13,13)
        p.setPen(Qt.NoPen);p.setBrush(QColor(window.colors['surface']));p.drawEllipse(mark)
        reminder_icon(p,mark.adjusted(1.5,1.5,-1.5,-1.5),kind,ink)
        window.reminder_bounds.append(mark);window.reminder_kinds.append(kind)


def paint_mail_status(window,p,rect):
    from resource_pomodoro_view import reminder_icon,reminder_ink
    has_mail=bool(window.service.mail and window.service.mail.unseen)
    size=min(16,rect.width()-2,rect.height()-2)
    if size<=0:return
    center=rect.center()
    ink=reminder_ink('mail_code',window.colors['light']) if has_mail else window.colors['muted']
    reminder_icon(p,QRectF(center.x()-size/2,center.y()-size/2,size,size),'mail_new' if has_mail else 'mail',ink)
    window.status_bounds['mail']=rect
