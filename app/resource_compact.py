"""Content-sized compact rows and an inexpensive perimeter-following halo."""
import time
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QFont,QFontMetrics,QPainterPath,QPen,QConicalGradient,QBrush,QTransform
from resource_status import metric_ink,metric_number
from resource_traffic import amount
from resource_quota import amount_text, quota_color, remaining_percent, used_percent
from resource_options import component_location


def text(p,rect,value,color,size=11,bold=False,align=Qt.AlignLeft):
    font=QFont(p.font());font.setPixelSize(size);font.setWeight(QFont.DemiBold if bold else QFont.Normal);p.setFont(font);p.setPen(QColor(color))
    p.drawText(rect,Qt.AlignVCenter|align,p.fontMetrics().elidedText(value,Qt.ElideRight,int(rect.width())))


def ring(p,rect,value,color,track,letter=''):
    p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(track),2.5));p.drawEllipse(rect)
    if value is not None:
        p.setPen(QPen(QColor(color),2.5,Qt.SolidLine,Qt.RoundCap));p.drawArc(rect,90*16,-round(min(100,max(0,value))*3.6*16))
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


def compact_values(window):
    cfg=window.service.cfg;bridge=window.service.deck
    values=list(getattr(window,'values',[])) if component_location(cfg,'resources')=='capsule' else []
    if cfg['resource_traffic'] and component_location(cfg,'traffic')=='capsule' and 'traffic' in cfg['resource_compact_metrics']:
        data=window.service.latest.get('traffic') or {}
        for key,label in [('day','今日流量'),('month','本月流量'),('year','本年流量')]:
            v=data.get(key);values.append(('traffic',label,amount(sum(v)) if v is not None else '—',''))
    if bridge and cfg['resource_ai'] and component_location(cfg,'ai')=='capsule':
        for row in bridge.providers:
            metrics = row.get('quotas', [])
            quotas = [level for q in metrics if (level := used_percent(q)) is not None]
            remaining = remaining_percent(max(quotas, default=None))
            money = next((value for q in metrics if q.get('kind')!='spend' and (value := amount_text(q)) not in (None, '—')), None)
            value = money or (f'{remaining:.0f}%' if remaining is not None else '—')
            values.append(('ai',row['name'],value,dict(provider=row,remaining=remaining,money=bool(money))))
    track=(bridge.media.get('track') or {}) if bridge and cfg['resource_music'] and component_location(cfg,'music')=='capsule' else {}
    if track:values.append(('music','音乐',track.get('lyric') or track.get('title','') if cfg['resource_music_text']=='lyrics' else track.get('title',''),track))
    extra=window.service.extras
    if extra and cfg['resource_weather'] and cfg['resource_weather_compact'] and component_location(cfg,'weather')=='capsule':
        for row in extra.weather:
            if 'temperature' in row:values.append(('weather',row['name'],f"{row['temperature']:.0f}° {row['condition']}",''))
    return values


def cell_width(row,dense=False):
    key=row[0]
    if key == 'ai' and len(row) > 3 and row[3].get('money'):
        return min(76, max(42, len(row[2])*6+3))
    if dense:
        return {'cpu':28,'gpu':28,'memory':30,'network':48,'ai':38,'music':54,'weather':54}.get(key,50)
    if key in ('cpu','gpu','memory'):return 52
    if key=='network':return 104
    if key=='weather':return 84
    if key=='ai':return 44
    if key=='music':return 96
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


def _make_plan(window,limit=None):
    cfg=window.service.cfg;values=compact_values(window);max_width=limit or cfg['resource_compact_width']
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
    capacity=max(32,max_width-16-face-face_gap)
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
    reserve=min(room,max([min(cell_width(r,dense),60) for r in extras]+[0]))
    spare=max(0,room-reserve);clock=False;bt=None;tail=0
    if cfg['resource_clock'] and 38<=spare:clock=True;tail+=38;spare-=38
    gauge=window.service.bluetooth if cfg['resource_bluetooth'] and component_location(cfg,'resources')=='capsule' and 'bluetooth' in cfg['resource_compact_metrics'] else None
    if gauge and 28<=spare:bt=gauge;tail+=28;spare-=28
    room=max(0,room-tail)
    pages=[('values',rows) for rows in packed(extras,room,dense)] if extras else [('values',[])]
    # LCM lets independent city/provider slots visit every combination of pages.
    from math import lcm
    count=lcm(len(pages),*(len(g) for g in pinned_groups)) if pinned_groups else len(pages)
    pages=(pages*((count+len(pages)-1)//len(pages)))[:count]
    pinned=[g[window.offset%len(g)] for g in pinned_groups]
    prefix=max((sum(min(cell_width(r,dense),room) for r in rows)+gap*max(0,len(rows)-1) for _,rows in pages),default=0)
    natural=16+face+face_gap+tail+used+(gap if used and prefix else 0)+min(prefix,room)
    from math import ceil
    return dict(width=min(max_width,max(96,ceil(natural))),pinned=pinned,pinned_widths=[max(cell_width(row,dense) for row in group) for group in pinned_groups],pages=pages,bt=bt,clock=clock,face=face,face_gap=face_gap,tail=tail,
                core=used,dense=dense,gap=gap,overflow=len(pinned_groups)<len(groups))


def natural_width(window,limit):
    return plan(window,limit)['width'] if window.service.cfg['resource_compact_auto_width'] else min(limit,window.service.cfg['resource_compact_width'])


def paint_values(window,p,rows,x,mid,available,dense=False,widths=None):
    cfg=window.service.cfg;c=window.colors;bounds=[];gap=cell_gap(dense)
    short=window.height()<38;font_size=10 if dense else 11;label_y=mid-11 if short else mid-15;value_y=mid if short else mid-1
    for index,(key,label,value,meta) in enumerate(rows):
        width=min(widths[index] if widths else cell_width((key,label,value,meta),dense),max(0,available))
        if width<26:break
        ink=metric_ink(window.service,key,c['light'],c['ink']) if key not in ('ai','music','weather','traffic') else c['ink']
        if key in ('cpu','gpu','memory') and not dense:
            if cfg['resource_compact_rings']:
                ring(p,QRectF(x,mid-8,16,16),metric_number(window.service,key),ink,c['hover'],{'cpu':'C','memory':'M','gpu':'G'}[key]);left=21
            else:text(p,QRectF(x,mid-8,20,16),{'cpu':'C','memory':'M','gpu':'G'}[key],c['muted'],9);left=15
            text(p,QRectF(x+left,mid-10,width-left,20),value,ink,11)
        elif key=='network':
            net=window.service.latest.get('network')
            from resource_charts import rate
            for i,arrow in enumerate(('↓','↑')):
                value=rate(net[i]).replace(' KB/s','K').replace(' MB/s','M').replace(' B/s','B') if net else '—'
                rect=QRectF(x,mid-11+i*12,width,12) if dense else QRectF(x+i*width/2,mid-10,width/2-3,20)
                text(p,rect,arrow+' '+value,c['ink'],font_size)
        elif key=='ai':
            remaining = meta['remaining']
            ink = c['ink'] if meta['money'] else quota_color(remaining, c['light'])
            text(p,QRectF(x,label_y,width,12),label,c['muted'],8 if short else 9)
            left=0
            if not dense and cfg['resource_compact_rings'] and not meta.get('money'):
                ring(p,QRectF(x+1,mid,13,13),remaining,ink,c['hover'],label[:1] if cfg['resource_ring_letters'] else '');left=18
            text(p,QRectF(x+left,value_y,width-left,12 if short else 17),value,ink,font_size if dense else 9)
            window.compact_providers.append(meta['provider']['id'])
        elif key=='music' and cfg['resource_music_text']=='wave':
            bridge=window.service.deck;levels=bridge.levels if meta.get('state')=='Playing' else [0]*8
            p.setPen(QPen(QColor(cfg.get('theme_color') or c['muted']),2,Qt.SolidLine,Qt.FlatCap))
            n=max(2,min(16,int(width/3.5)))
            for i in range(n):
                level=levels[i*len(levels)//n] if levels else 0;h=2+max(0,min(1,level))*min(17,window.height()-14)
                p.drawLine(QPointF(x+i*3.5,mid+8),QPointF(x+i*3.5,mid+8-h))
            window.compact_media=True
        else:
            if key=='music':window.compact_media=True
            text(p,QRectF(x,label_y,width,12 if short else 14),label,c['muted'],8 if short else 9)
            text(p,QRectF(x,value_y,width,12 if short else 17),value,ink,font_size)
        bounds.append(QRectF(x,mid-(12 if short else 17),width,24 if short else 34));window.compact_shown.append(key)
        x+=width+gap;available-=width+gap
    return bounds


def paint_compact(window,p):
    cfg=window.service.cfg;c=window.colors;bridge=window.service.deck;mid=window.height()/2
    layout=plan(window,window.width());pages=layout['pages'];window.compact_pages=len(pages)
    _,rows=pages[window.offset%len(pages)];window.compact_shown=[];window.compact_providers=[];window.compact_media=False
    right=window.width()-8;left=8.;window.compact_bounds=[]
    if layout['face']:
        window.liquid.paint_face(p,QPointF(left+layout['face']/2,mid),layout['face']);left+=layout['face']+layout['face_gap']
    if layout['clock']:
        text(p,QRectF(right-34,mid-10,34,20),time.strftime('%H:%M'),c['ink'],11,False,Qt.AlignRight);right-=38
    if layout['bt']:
        from bluetooth_gauge import draw_rings
        draw_rings(p,QRectF(right-23,mid-11.5,23,23),layout['bt'].group(),not c['light']);right-=28
    # Pins are anchored at the leading edge, so supplemental pages never move them.
    core=layout['core'];window.compact_bounds+=paint_values(window,p,layout['pinned'],left,mid,core,layout['dense'],layout['pinned_widths'])
    left+=core+(layout['gap'] if core and rows else 0)
    window.compact_bounds+=paint_values(window,p,rows,left,mid,max(0,right-left),layout['dense'])
    if bridge and bridge.alert_until>time.monotonic() and cfg['resource_quota_alert']:
        window.setAccessibleName(window.accessibleName().split('\n额度提示：')[0]+'\n额度提示：'+bridge.alert)
