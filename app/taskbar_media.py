"""Small native media controls; shares the existing bridge, no extra player process."""
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QPainterPath,QPen,QLinearGradient,QBrush
from resource_compact import text


def scale(cfg):return min(1.,max(2,cfg.get('resource_task_font',11))/11.)


def spacing(cfg,base):return max(1,round(base*scale(cfg)))


def natural_width(parts,factor=1.):
    sizes={'cover':24,'title':45,'controls':54,'wave':36}
    values=[size*factor for key,size in sizes.items() if key in parts]
    return sum(values)+max(1,3*factor)*max(0,len(values)-1)


def layout(strip):
    bridge=strip.service.deck
    if not strip.music_requested() or not bridge or not bridge.media.get('track'):return dict(active=False,items=[],width=0,progress=False)
    cfg=strip.service.cfg;factor=scale(cfg);gap=max(1,3*factor)
    parts=cfg['resource_task_media_parts'];sizes={key:size*factor for key,size in {'cover':24,'title':45,'controls':54,'wave':36}.items()}
    # In a narrow verified gap reserve room for at least one resource reading.
    room=max(0,strip.width()-2*spacing(cfg,4)-(96*factor if cfg['resource_task_metrics'] else 0))
    items=[(key,size) for key,size in sizes.items() if key in parts]
    def total():return sum(size for _,size in items)+gap*max(0,len(items)-1)
    if total()>room and len(items)>1:items=[item for item in items if item[0]!='title']
    if total()>room:items=[(key,18*factor if key=='controls' else size) for key,size in items]
    for discard in ('wave','cover'):
        if total()>room and len(items)>1:items=[item for item in items if item[0]!=discard]
    if len(items)==1:
        key,size=items[0];minimum=(32 if key=='title' else 20 if key=='wave' else 18)*factor
        items=[(key,min(size,room))] if room>=minimum else []
    return dict(active=True,items=items,width=total(),progress='progress' in parts,scale=factor,gap=gap)


def width(strip):return layout(strip)['width']


def paint(strip,p,area,ink,plan):
    bridge=strip.service.deck;track=bridge.media.get('track') or {};mid=area.center().y();left=area.left();s=plan['scale']
    colorful=strip.service.cfg.get('resource_task_music_colorful',False)
    palette=('#087eab','#2464cf','#704acc','#b32687','#bd4c25') if getattr(strip,'system_mode',1)!=0 else ('#54e7ee','#6aa9ff','#b893ff','#ff8bd3','#ffc875')
    strip.media_actions={};strip.media_bounds=[];strip.media_parts_shown=[];p.setRenderHint(p.SmoothPixmapTransform)
    for key,size in plan['items']:
        strip.media_parts_shown.append(key)
        if key=='cover':
            side=min(size,area.height()-4*s);cover=QRectF(left+(size-side)/2,mid-side/2,side,side);path=QPainterPath();path.addRoundedRect(cover,3*s,3*s)
            p.save();p.setClipPath(path)
            if not bridge.cover.isNull():
                pix=bridge.cover;crop=min(pix.width(),pix.height());p.drawPixmap(cover,pix,QRectF((pix.width()-crop)/2,(pix.height()-crop)/2,crop,crop))
            else:
                color=QColor(ink);color.setAlpha(30);p.fillRect(cover,color);text(p,cover,'♪',ink.name(),max(2,round(13*s)),False,Qt.AlignCenter)
            p.restore();strip.media_bounds.append(cover)
        elif key=='title':
            text(p,QRectF(left,mid-13*s,size,14*s),track.get('title',''),ink.name(),max(2,round(9*s)))
            muted=QColor(ink);muted.setAlpha(170)
            text(p,QRectF(left,mid,size,13*s),track.get('artist') or ('正在播放' if track.get('state')=='Playing' else '已暂停'),muted.name(),max(2,round(8*s)))
            strip.media_bounds.append(QRectF(left,mid-13*s,size,26*s))
        elif key=='controls':
            ops=[('Previous','canPrevious'),('PlayPause','canToggle'),('Next','canNext')] if size>=54*s-.01 else [('PlayPause','canToggle')]
            for i,(op,flag) in enumerate(ops):
                rect=QRectF(left+i*18*s,mid-11*s,18*s,22*s);enabled=bool(track.get(flag));color=QColor(ink);color.setAlpha(255 if enabled else 75)
                p.save();p.translate(rect.center());p.scale(s,s);p.setPen(Qt.NoPen);p.setBrush(color);cx,cy=0,0
                if op=='PlayPause' and track.get('state')=='Playing':
                    for x in (cx-4,cx+1):p.drawRoundedRect(QRectF(x,cy-4.5,3,9),.6,.6)
                else:
                    sign=-1 if op=='Previous' else 1;path=QPainterPath();path.moveTo(cx-sign*3,cy-5);path.lineTo(cx+sign*4,cy);path.lineTo(cx-sign*3,cy+5);path.closeSubpath();p.drawPath(path)
                    if op!='PlayPause':p.drawRect(QRectF(cx+sign*4-(1 if sign<0 else 0),cy-5,1.5,10))
                p.restore()
                if enabled:strip.media_actions[op]=rect
                strip.media_bounds.append(rect)
        elif key=='wave':
            levels=bridge.levels if track.get('state')=='Playing' else [0]*8
            p.setPen(QPen(ink,2*s,Qt.SolidLine,Qt.FlatCap));n=max(2,min(12,int(size/(3*s))))
            for i in range(n):
                if colorful:p.setPen(QPen(QColor(palette[min(len(palette)-1,i*len(palette)//n)]),2*s,Qt.SolidLine,Qt.FlatCap))
                value=levels[i*len(levels)//n] if levels else 0;h=2*s+max(0,min(1,value))*min(19*s,area.height()-6*s)
                p.drawLine(QPointF(left+i*3*s,mid+h/2),QPointF(left+i*3*s,mid-h/2))
            strip.media_bounds.append(QRectF(left,mid-11*s,size,22*s))
        left+=size+plan['gap']
    # The progress hairline sits outside the vertically centered content row.
    if plan['progress'] and track.get('duration',0)>0:
        from PyQt5.QtGui import QFontMetrics
        font,single=strip.readout_font()
        content=max(26*s if plan['items'] else 0,QFontMetrics(font).height()*(1 if single else 2) if strip.cells else 0)
        strip.media_parts_shown.append('progress');y=min(strip.height()-1.5,mid+content/2+max(.8,2*s)) if content else mid
        pad=spacing(strip.service.cfg,4);progress=QRectF(pad,y,strip.width()-2*pad,max(.5,s))
        color=QColor(ink);color.setAlpha(45);p.fillRect(progress,color)
        progress.setWidth(progress.width()*max(0,min(1,track.get('position',0)/track['duration'])))
        if colorful:
            gradient=QLinearGradient(progress.left(),0,progress.right(),0)
            for i,color in enumerate(palette):gradient.setColorAt(i/(len(palette)-1),QColor(color))
            p.fillRect(progress,QBrush(gradient))
        else:p.fillRect(progress,ink)
        if track.get('canSeek'):strip.media_actions['seek']=QRectF(pad,max(0,y-3),strip.width()-2*pad,4)
