"""Layout for an explicitly ordered row of readings, controls and reminders."""
from math import lcm
from typing import NamedTuple

from PyQt5.QtCore import QRectF, Qt

from capsule_order import badge_key, device_key, display_order
from resource_options import COMPACT_CLOCK_FORMATS, RUNNER_SLOT, component_location


class Slot(NamedTuple):
    key: str
    kind: str
    width: int
    data: tuple = ()


class Placed(NamedTuple):
    slot: Slot
    x: int
    width: int
    data: tuple


GAP = 3


def make_plan(window, limit):
    from resource_compact import (CLOCK_WIDTHS, STATUS_STEP, badge_slots, cell_width, compact_badges,
                                  compact_values, status_values)
    cfg = window.service.cfg
    inner = max(1,limit-16)
    dense = cfg['resource_compact_density']=='dense' or limit<420 or window.height()<38
    items = {}
    grouped = {}
    for row in compact_values(window):
        grouped.setdefault(row[0],[]).append(row)
    for key, rows in grouped.items():
        items[key] = Slot(key,'value',max(cell_width(row,dense) for row in rows),tuple(rows))
    for row in status_values(window.service):
        items[row[0]] = Slot(row[0],'status',STATUS_STEP,row)
    if cfg['resource_face']:
        items['face'] = Slot('face','face',round((30 if dense else 40)*cfg['resource_face_scale']/100))
    if cfg['resource_mail'] and cfg['resource_mail_icon']:
        items['mail'] = Slot('mail','mail',STATUS_STEP)
    if cfg['resource_runner_enabled']:
        items['runner'] = Slot('runner','runner',RUNNER_SLOT)
    if cfg['resource_clock']:
        formats = COMPACT_CLOCK_FORMATS[cfg['resource_clock_format']][1]
        items['clock'] = Slot('clock','clock',max(CLOCK_WIDTHS[pattern] for pattern in formats),formats)

    urgent = []
    badges,active_count = compact_badges(window.service)
    for index,badge in enumerate(badges):
        active = index < active_count
        key = badge_key(badge[0],active)
        chip = badge_slots(window,[badge],max(25,inner),limit)[0][0]
        items[key] = Slot(key,'badge',chip[2],chip)
        if active:
            urgent.append(key)
            if badge[0]=='battery':items.pop('battery',None)
    indicators = window.service.indicators
    if indicators:
        for cell in indicators.cells(4096,window.height()):
            key = device_key(cell[0])
            items[key] = Slot(key,'device',cell[2],cell)
            if cell[0] in indicators.transitions:urgent.append(key)

    ordered = [items[key] for key in display_order(cfg) if key in items]
    natural = 16 + sum(s.width for s in ordered) + GAP*max(0,len(ordered)-1)
    # Keep a slot for paging through every remaining item. An active reminder
    # or a changing device may stay visible without changing its chosen position.
    fixed = set(items) if natural <= limit else set()
    room = inner
    if natural > limit:
        reserve = min(inner, max(26,min(100,inner//3)))
        for key in dict.fromkeys(['clock',*urgent,*(s.key for s in ordered)]):
            slot = items.get(key)
            if slot and room-slot.width-GAP >= reserve:
                fixed.add(key)
                room -= slot.width+GAP
    others = [s for s in ordered if s.key not in fixed]
    pages = [[]]
    used = 0
    for slot in others:
        width = min(slot.width,room)
        if pages[-1] and used+GAP+width > room:
            pages.append([])
            used = 0
        used += width+(GAP if pages[-1] else 0)
        pages[-1].append(slot.key)
    # A provider/city on an overflow page changes on the next visit to that page.
    period = len(pages)
    for slot in ordered:
        if slot.kind=='value':
            period = lcm(period,len(slot.data)*(1 if slot.key in fixed else len(pages)))
    layout = dict(width=max(1,min(limit,max(96,natural))), dense=dense, pages=range(period),
                  ordered=ordered, fixed=fixed, overflow_pages=pages, page_room=room,
                  clock=(), clock_width=0, runner_width=0, face=0, active_badges=[], routine_badges=[])
    layout['positions'] = positions(layout,window.offset,limit)
    for key,placed in layout['positions'].items():
        if key=='clock':
            layout['clock'],layout['clock_width'] = placed.data,placed.width
        elif key=='runner':layout['runner_width'] = placed.width
        elif key=='face':layout['face'] = placed.width
        elif placed.slot.kind=='badge':
            layout['active_badges' if key in urgent else 'routine_badges'].append(placed.data)
    return layout


def positions(layout,offset,width):
    pages = layout['overflow_pages']
    visible = layout['fixed'].union(pages[offset%len(pages)])
    result = {}
    left = 8
    for slot in layout['ordered']:
        if slot.key not in visible:continue
        pinned = slot.key in layout['fixed']
        size = slot.width if pinned else min(slot.width,layout['page_room'])
        data = slot.data
        if slot.kind=='value':
            turn = offset if pinned else offset//len(pages)
            data = data[turn%len(data)]
        if slot.key=='clock' and slot is layout['ordered'][-1]:
            left = width-8-size
        result[slot.key] = Placed(slot,left,size,data)
        left += size+GAP
    return result


def paint_item(window,p,placed,mid,dense,overlays,clip):
    from resource_compact import paint_badges,paint_clock,paint_mail_status,paint_status,paint_values
    slot,x,width,data = placed
    height = window.height()
    rect = QRectF(x,mid-height/2,width,height)
    if slot.kind=='value':
        window.compact_bounds.extend(paint_values(window,p,[data],x,mid,width,dense,[width],clip,overlays))
    elif slot.kind=='badge':
        kind,label,_,wanted = data
        paint_badges(window,p,[(kind,label,width,wanted)],x+width,mid,overlays)
    elif slot.kind=='device':
        kind,side,_,label = data
        window.service.indicators.paint(p,[(kind,min(side,width),width,label)],x,mid,window.colors)
    elif slot.kind=='status':
        paint_status(p,rect,data,window.colors)
        window.status_bounds[slot.key] = rect
    elif slot.kind=='mail':
        paint_mail_status(window,p,rect)
    elif slot.kind=='clock':
        paint_clock(window,p,data,x,width,mid)
    # The face and the runner have independently animated paint layers.


def paint_page(window,p,layout,scroll,overlays):
    current = layout['positions']
    mid = window.height()/2
    clip = QRectF(window.rect())
    if not scroll:
        for placed in current.values():
            paint_item(window,p,placed,mid,layout['dense'],overlays,clip)
        return
    previous,progress,direction = scroll
    before = positions(layout,previous,window.width())
    eased = progress*progress*(3-2*progress)
    distance = max(1,window.height()-4)*direction
    p.save()
    p.setClipRect(clip,Qt.IntersectClip)
    for key,placed in before.items():
        if placed != current.get(key):
            paint_item(window,p,placed,mid-distance*eased,layout['dense'],None,clip)
    for key,placed in current.items():
        y = mid if placed==before.get(key) else mid+distance*(1-eased)
        paint_item(window,p,placed,y,layout['dense'],None,clip)
    p.restore()


def ball_slots(window,limit):
    """The ball has a round main icon and a short row of optional companions."""
    from resource_compact import badge_slots
    stamp = ('ordered-ball',limit,window.height())
    cached = getattr(window,'_compact_cache',None)
    if cached and cached[0]==stamp:return cached[1]
    cfg = window.service.cfg
    reading = getattr(window.service.deck,'ball_quota',None)
    has_ring = reading and cfg['resource_ai'] and cfg['resource_compact_ai'] and component_location(cfg,'ai')=='capsule'
    core = 'face' if cfg['resource_face'] or not has_ring else 'ai'
    items = {core:Slot(core,'ball',38)}
    if has_ring:
        items['ai'] = Slot('ai','quota',38 if core=='ai' else 26,(reading,))
    if cfg['resource_mail'] and cfg['resource_mail_icon']:
        items['mail'] = Slot('mail','mail',22)
    if cfg['resource_runner_enabled']:
        items['runner'] = Slot('runner','runner',RUNNER_SLOT)
    alerts = window.service.reminders()
    for index,(kind,label) in enumerate(alerts):
        timer = kind in ('stopwatch','stopwatch_paused','alarm','alarm_due')
        if index and not timer:continue
        key = badge_key(kind,True)
        chip = badge_slots(window,[(kind,label)],max(25,limit),limit)[0][0]
        items[key] = Slot(key,'badge',chip[2]+3 if timer else 25,chip)
    indicators = window.service.indicators
    if indicators:
        for cell in indicators.cells(4096,38):
            key = device_key(cell[0])
            items[key] = Slot(key,'device',cell[2]+3,cell)
    keys = [key for key in display_order(cfg) if key in items]
    room = max(0,limit-38)
    kept = {core}
    for key in keys:
        if key!=core and items[key].width<=room:
            room-=items[key].width
            kept.add(key)
    left = 0
    result = {}
    for key in keys:
        if key in kept:
            item = items[key]
            result[key] = Placed(item,left,item.width,item.data)
            left += item.width
    window._compact_cache = (stamp,result)
    return result


def paint_ball(window,p):
    from PyQt5.QtCore import QPointF
    from PyQt5.QtGui import QColor,QPen
    from resource_charts import metric_colors
    from resource_compact import paint_quota_ring
    positions = ball_slots(window,window.width())
    mid = window.height()/2
    for placed in positions.values():
        slot,x,width,data = placed
        rect = QRectF(x+1,1,width-2,window.height()-2)
        if slot.kind=='ball':
            if window.service.cfg['resource_face']:
                window.liquid.paint_face(p,rect.center(),min(rect.width()-8,rect.height()))
            else:
                center=rect.center()
                p.setPen(QPen(QColor(metric_colors(window.service)['cpu']),2,Qt.SolidLine,Qt.RoundCap))
                for i,h in enumerate((7,14,10)):
                    start=QPointF(center.x()-5+5*i,mid+6)
                    p.drawLine(start,start-QPointF(0,h))
        elif slot.kind=='quota':
            side=min(rect.width(),rect.height())-2
            ring=QRectF(0,0,side,side);ring.moveCenter(rect.center())
            paint_quota_ring(p,ring,data[0],window.colors['light'])
            window.compact_ai_hits.append((ring,data[0]))
        elif slot.kind in ('badge','device'):
            paint_item(window,p,placed._replace(x=x+1,width=width-3),mid,True,None,rect)
        else:
            paint_item(window,p,placed,mid,True,None,rect)
    runner=window.service.runners.get('capsule')
    if runner and 'runner' in positions:runner.paint(p,window)
