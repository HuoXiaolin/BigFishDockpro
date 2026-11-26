"""Layout for an explicitly ordered row of readings, controls and reminders."""
from math import lcm
from typing import NamedTuple

from PyQt5.QtCore import QRectF, Qt

from capsule_order import ZONES, badge_key, clock_turn, device_key, display_order, item_zones
from resource_options import COMPACT_CLOCK_FORMATS, RUNNER_SLOT, compact_tile_height, component_location


class Slot(NamedTuple):
    key: str
    kind: str
    width: int
    data: tuple = ()
    page_widths: tuple = ()


class Placed(NamedTuple):
    slot: Slot
    x: float
    width: int
    data: tuple


GAP = 3


class PageGroup(NamedTuple):
    slots: list
    fixed: set
    pages: list
    room: int

    def stride(self, key):
        return 1 if key in self.fixed else len(self.pages)


def span(slots, gap=GAP):
    return sum(slot.width for slot in slots) + gap * max(0, len(slots)-1)


def aligned_span(widths, gap):
    middle=widths.get('center',0)
    wing=max(widths.get('left',0),widths.get('right',0))
    if middle and wing:
        return middle+2*(wing+gap)
    return sum(widths.values())+gap*max(0,len(widths)-1)


def page_group(slots, capacity, urgent):
    if span(slots) <= capacity:
        return PageGroup(slots, {slot.key for slot in slots}, [set()], capacity)
    by_key = {slot.key:slot for slot in slots}
    widest_first = sorted(slots, key=lambda slot:slot.width, reverse=True)
    fixed = set()
    room = capacity
    for key in dict.fromkeys(['clock', *urgent, *by_key]):
        if key not in by_key:
            continue
        # A fixed item must leave enough room to read every other item on its turn.
        needed = next((slot.width for slot in widest_first if slot.key != key and slot.key not in fixed), 0)
        if room - by_key[key].width - GAP >= needed:
            fixed.add(key)
            room -= by_key[key].width + GAP
    pages = [set()]
    used = 0
    for slot in slots:
        if slot.key in fixed:
            continue
        width = min(slot.width, room)
        if pages[-1] and used + GAP + width > room:
            pages.append(set())
            used = 0
        used += width + (GAP if pages[-1] else 0)
        pages[-1].add(slot.key)
    return PageGroup(slots, fixed, pages, room)


def edge_bands(groups, capacity):
    widths = {zone: min(capacity,max(s.width for s in slots)) for zone, slots in groups.items()}
    bands = [[]]
    used = 0
    for zone, width in widths.items():
        if bands[-1] and used + GAP + width > capacity:
            bands.append([])
            used = 0
        used += width + (GAP if bands[-1] else 0)
        bands[-1].append(zone)
    needs = {zone: span(slots)-widths[zone] for zone, slots in groups.items()}
    for band in bands:
        spare = capacity - sum(widths[z] for z in band) - GAP*max(0,len(band)-1)
        for index, zone in enumerate(sorted(band, key=needs.get)):
            extra = min(needs[zone], spare // (len(band)-index))
            widths[zone] += extra
            spare -= extra
    return widths,bands


def zone_pages(ordered, zones, capacity, urgent):
    groups={zone:[s for s in ordered if zones[s.key]==zone] for zone in ZONES}
    groups={zone:slots for zone,slots in groups.items() if slots}
    totals={zone:span(slots) for zone,slots in groups.items()}
    middle=groups.get('center')
    if not middle:
        widths,bands=edge_bands(groups,capacity)
    else:
        sides={zone:slots for zone,slots in groups.items() if zone!='center'}
        middle_min=min(capacity,max(s.width for s in middle))
        widest_side=max((s.width for slots in sides.values() for s in slots),default=0)
        # Keep the center visible while either side can still display a usable tile.
        # On smaller rows share pages instead of putting another item across the center.
        if sides and middle_min+2*(min(26,widest_side)+GAP)>capacity:
            widths,other_bands=edge_bands(sides,capacity)
            widths['center']=min(capacity,totals['center'])
            bands=[['center'],*other_bands]
        else:
            center_room=capacity-2*(widest_side+GAP) if sides else capacity
            center_width=min(totals['center'],max(middle_min,center_room))
            side_room=(capacity-center_width)//2-GAP
            widths={zone:center_width if zone=='center' else min(total,side_room) for zone,total in totals.items()}
            bands=[list(groups)]
    pages={zone:page_group(slots,widths[zone],urgent) for zone,slots in groups.items()}
    return pages,widths,bands,aligned_span(totals,GAP)


def make_plan(window, limit):
    from compact_clock import capsule_clock_width, capsule_headers
    from resource_compact import (MAIL_STEP, badge_slots, cell_width, compact_badges, compact_face_width,
                                  compact_values, status_values)
    cfg = window.service.cfg
    inner = max(1,limit-16)
    dense = cfg['resource_compact_density']=='dense' or limit<420 or window.height()<38
    items = {}
    grouped = {}
    for row in compact_values(window):
        grouped.setdefault(row[0],[]).append(row)
    for key, rows in grouped.items():
        row_widths=tuple(cell_width(row,dense,window) for row in rows)
        items[key] = Slot(key,'value',max(row_widths),tuple(rows),row_widths)
    for row in status_values(window.service):
        items[row[0]] = Slot(row[0],'status',compact_tile_height(cfg,window.height())+3,row)
    if cfg['resource_face']:
        items['face'] = Slot('face','face',compact_face_width(cfg,window.height()))
    if cfg['resource_mail'] and cfg['resource_mail_icon']:
        items['mail'] = Slot('mail','mail',MAIL_STEP)
    if cfg['resource_runner_enabled']:
        items['runner'] = Slot('runner','runner',RUNNER_SLOT)
    if cfg['resource_clock']:
        formats = COMPACT_CLOCK_FORMATS[cfg['resource_clock_format']][1]
        items['clock'] = Slot('clock','clock',capsule_clock_width(cfg, formats, window.height()),formats)

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

    order = display_order(cfg)
    ordered = [items[key] for key in order if key in items]
    zones = item_zones(cfg, order)
    groups, widths, bands, natural = zone_pages(ordered, zones, inner, urgent)
    periods = {}
    clock_stride = 1
    for zone, group in groups.items():
        period = len(group.pages)
        for slot in group.slots:
            if slot.kind == 'value':
                period = lcm(period, len(slot.data) * group.stride(slot.key))
            elif slot.kind == 'clock':
                clock_stride = group.stride(slot.key)
                period = lcm(period, len(capsule_headers(cfg, slot.data)) * clock_stride)
        periods[zone] = period
    layout = dict(width=max(1,min(limit,max(96,16+natural))), dense=dense, pages=range(len(bands)*lcm(*periods.values())),
                  groups=groups, zones=zones, zone_widths=widths, clock_stride=clock_stride, clock_zone=zones['clock'],
                  bands=bands, zone_periods=periods,
                  clock=(), clock_width=0, runner_width=0, face=0, active_badges=[], routine_badges=[])
    layout['positions'] = positions(layout,window.page_turns,limit)
    for key,placed in layout['positions'].items():
        if key=='clock':
            layout['clock'],layout['clock_width'] = placed.data,placed.width
        elif key=='runner':layout['runner_width'] = placed.width
        elif key=='face':layout['face'] = placed.width
        elif placed.slot.kind=='badge':
            layout['active_badges' if key in urgent else 'routine_badges'].append(placed.data)
    return layout


def align_slots(slots, zones, width, margin, gap):
    groups = {zone:[] for zone in ZONES}
    for placed in slots:
        groups[zones[placed.slot.key]].append(placed)
    left, middle, right = groups.values()
    right_x = width - margin - span(right,gap)
    middle_x = (width-span(middle,gap))/2
    result = {}
    for group, x in ((left,margin),(middle,middle_x),(right,right_x)):
        for placed in group:
            result[placed.slot.key] = placed._replace(x=x)
            x += placed.width + gap
    return result


def positions(layout,turns,width):
    slots = []
    bands = layout['bands']
    for zone in bands[turns.shared % len(bands)]:
        group = layout['groups'][zone]
        offset = getattr(turns,zone) // len(bands)
        visible = group.fixed | group.pages[offset % len(group.pages)]
        for slot in group.slots:
            if slot.key not in visible:continue
            size = slot.width if slot.key in group.fixed else min(slot.width,group.room)
            data = slot.data
            if slot.kind=='value':
                page = offset // group.stride(slot.key) % len(data)
                data = data[page]
                if zone=='center':
                    size=min(size,slot.page_widths[page])
            slots.append(Placed(slot,0,size,data))
    return align_slots(slots,layout['zones'],width,8,GAP)


def paint_item(window,p,placed,mid,dense,overlays,clip,clock_turn=0):
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
        paint_status(window,p,data,x,width,mid)
    elif slot.kind=='mail':
        paint_mail_status(window,p,rect)
    elif slot.kind=='clock':
        paint_clock(window,p,data,x,width,mid,clock_turn)
    # The face and the runner have independently animated paint layers.


def paint_page(window,p,layout,scroll,overlays):
    current = layout['positions']
    calendar_page = clock_turn(layout,window.page_turns)
    mid = window.height()/2
    clip = QRectF(window.rect())
    if not scroll:
        for placed in current.values():
            paint_item(window,p,placed,mid,layout['dense'],overlays,clip,calendar_page)
        return
    previous,progress,direction = scroll
    before = positions(layout,previous,window.width())
    eased = progress*progress*(3-2*progress)
    distance = max(1,window.height()-4)*direction
    p.save()
    p.setClipRect(clip,Qt.IntersectClip)
    for key,placed in before.items():
        if placed != current.get(key):
            paint_item(window,p,placed,mid-distance*eased,layout['dense'],None,clip,clock_turn(layout,previous))
    for key,placed in current.items():
        y = mid if placed==before.get(key) else mid+distance*(1-eased)
        paint_item(window,p,placed,y,layout['dense'],None,clip,calendar_page)
    p.restore()


def ball_layout(window,limit,height=None):
    """The ball has a round main icon and a short row of optional companions."""
    from resource_compact import badge_slots
    height = window.height() if height is None else height
    stamp = ('ordered-ball',limit,height)
    cached = getattr(window,'_compact_cache',None)
    if cached and cached[0]==stamp:return cached[1]
    cfg = window.service.cfg
    reading = getattr(window.service.deck,'ball_quota',None)
    has_ring = reading and cfg['resource_ai'] and cfg['resource_compact_ai'] and component_location(cfg,'ai')=='capsule'
    core = 'face' if cfg['resource_face'] or not has_ring else 'ai'
    diameter=min(38,height,limit)
    items = {core:Slot(core,'ball',diameter)}
    if has_ring:
        items['ai'] = Slot('ai','quota',diameter if core=='ai' else 26,(reading,))
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
        for cell in indicators.cells(4096,height):
            key = device_key(cell[0])
            items[key] = Slot(key,'device',cell[2]+3,cell)
    order = display_order(cfg)
    keys = [key for key in order if key in items]
    zones=item_zones(cfg,order)
    widths={zones[core]:diameter}
    kept = {core}
    for key in keys:
        if key==core:continue
        zone=zones[key]
        candidate={**widths,zone:widths.get(zone,0)+items[key].width}
        if aligned_span(candidate,0)<=limit:
            widths=candidate
            kept.add(key)
    slots = [Placed(items[key],0,items[key].width,items[key].data) for key in keys if key in kept]
    result = align_slots(slots,zones,limit,0,0),aligned_span(widths,0)
    window._compact_cache = (stamp,result)
    return result


def ball_slots(window,limit,height=None):
    return ball_layout(window,limit,height)[0]


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
