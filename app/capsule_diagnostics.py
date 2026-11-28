"""Local, bounded observations from the capsule's actual input and color decisions."""
from collections import deque
from datetime import datetime
import json
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
import time

from PyQt5.QtCore import QStandardPaths, Qt, QTimer
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from background_contrast import majority_surface


def stamp(seconds):
    return datetime.fromtimestamp(seconds).astimezone().isoformat(timespec='milliseconds')


def hex_color(rgb):
    if rgb is not None:
        return '#' + ''.join(f'{round(channel):02X}' for channel in rgb[:3])


class CapsuleDiagnostics:
    def __init__(self):
        self.colors=None
        self.grid=None
        self.last_hit=None
        self.history=deque(maxlen=8)
        self.last_key=None

    def record_colors(self,widget,raw,app_cells,paper_source,surfaces,light,mode,needs_background,live,sources):
        from window_layers import client_frame
        frame=client_frame(int(widget.winId())) if widget.isVisible() else None
        self.grid=(frame,raw,surfaces)
        actual=[color for color in raw if color is not None] if raw else []
        self.colors={
            '采样时间':stamp(time.time()),'胶囊位置与尺寸（逻辑像素）':widget.geometry().getRect(),
            '文字模式':mode,'动态窗口取色':live,'需要背景取色':needs_background,
            '应用窗口采样点数':app_cells,'桌面来源':paper_source,'桌面采样点数':len(actual)-app_cells,
            '使用后备配色的点数':128-len(actual) if needs_background else 0,
            '背景实测代表色':hex_color(majority_surface(actual)),
            '中心附近实测色':hex_color(raw[4*16+8]) if raw else None,
            '叠加材质后的代表色':hex_color(majority_surface(surfaces)),
            '文字判定':'深色字' if light else '浅色字',
            '实际参与取色的窗口':sources,
        }

    def record_policy(self,mode,conditional,unlocked,passthrough,trace,edge_interactive):
        if unlocked:reason='按住 Alt，临时恢复交互'
        elif edge_interactive:reason='贴边收起，保留光条交互'
        elif conditional:reason=(trace or {}).get('reason','未返回命中详情')
        elif mode=='apps':reason='胶囊未置顶，允许交互'
        elif mode is True:reason='穿透设置为始终穿透'
        else:reason='穿透设置为可交互'
        inside=bool(trace and trace.get('visible'))
        windows=trace.get('windows',()) if trace else ()
        key=(mode,reason,passthrough,inside,tuple((row[0],row[5]) for row in windows))
        if key==self.last_key and not inside:return
        entry=(time.time(),reason,bool(passthrough),trace)
        if key!=self.last_key:
            self.history.append(entry)
            self.last_key=key
        else:self.history[-1]=entry
        if inside:self.last_hit=(entry,self.colors,self.grid)


def snapshot(service):
    from ctypes.wintypes import POINT
    from app_version import VERSION
    from component_passthrough import individual,pointer_mode
    from resource_processes import executable_path
    from window_layers import application_under,client_frame,is_topmost,native
    cfg=service.cfg
    report={'版本':VERSION,'Windows':sys.getwindowsversion().build,'现场记录时间':stamp(time.time()),
            '设置':{key:cfg.get(key) for key in ('resource_layer','desktop_layer_mode','passthrough_mode',
                    'passthrough_alt_unlock','resource_app_fold','resource_edge_hide','resource_geometry_locked',
                    'resource_backdrop_mode','resource_content_mode','resource_idle_fade',
                    'desktop_idle_fade_mode','desktop_idle_fade_amount')}}
    report['设置'].update(胶囊穿透选项=individual(cfg,'resource'),生效穿透选项=pointer_mode(cfg,'resource'))
    w=service.window
    if w is None or not w.isVisible():
        report['胶囊']='当前未显示'
        return report

    names={}
    def format_trace(trace):
        if not trace:return None
        windows=[]
        for handle,pid,name,flags,rect,reason in trace.get('windows',()):
            if pid not in names:names[pid]=Path(executable_path(pid)).name or '无法读取'
            windows.append({'进程':names[pid],'PID':pid,'窗口类':name,'HWND':hex(handle),
                            '扩展样式':hex(flags & 0xffffffff),'窗口边界LTRB':rect,'判定':reason})
        return {'屏幕物理坐标':trace.get('point'),'在胶囊窗口内':trace.get('inside'),'在可见形态内':trace.get('visible',False),
                '结论':trace.get('reason'),'窗口（由近到远）':windows}

    def decision(entry):
        when,reason,passthrough,trace=entry
        return {'时间':stamp(when),'穿透':passthrough,'原因':reason,'鼠标命中':format_trace(trace)}

    hwnd=int(w.winId())
    frame=client_frame(hwnd)
    edge=getattr(w,'edge_reveal',None)
    screen=w.screen()
    report['胶囊']={'HWND':hex(hwnd),'实际置顶':is_topmost(hwnd),'胶囊是否收起':service.compact,
                    '显示器':screen.name() if screen else None,'缩放':w.devicePixelRatioF(),'窗口不透明度':w.windowOpacity(),
                    '窗口位置与尺寸（物理像素）':frame,'Qt 鼠标穿透':w.testAttribute(Qt.WA_TransparentForMouseEvents),
                    'Windows 鼠标穿透':bool(native().GetWindowLongW(hwnd,-20)&0x20),
                    '应用覆盖判定':edge.over_app if edge else None,
                    '显示形态':edge.hidden_shape if edge and edge.fraction<1 else w.fold_shape() if service.compact else '展开'}
    data=w.capsule_diagnostics
    if data.last_hit:
        entry,colors,grid=data.last_hit
        report['最近一次鼠标在胶囊内的条件穿透判定']=decision(entry)
        report['该次判定时最近的取色']=colors
        if grid and grid[0]:
            (x,y,width,height),raw,surfaces=grid
            px,py=entry[3]['point']
            if x<=px<x+width and y<=py<y+height:
                i=(py-y)*8//height*16+(px-x)*16//width
                report['该次鼠标所在采样格']={'实测背景色':hex_color(raw[i]) if raw else None,
                                          '叠加材质后的颜色':hex_color(surfaces[i]) if surfaces else None}
    else:report['最近一次鼠标在胶囊内的条件穿透判定']='尚无记录'
    report['最近的实际穿透判定']=[decision(entry) for entry in data.history]
    if frame:
        x,y,width,height=frame
        area=w.mask().boundingRect()
        center=(w.rect() if area.isEmpty() else area).center()
        point=POINT(x+round((center.x()+.5)*width/w.width()),y+round((center.y()+.5)*height/w.height()))
        probe={}
        application_under(hwnd,point,probe)
        probe['visible']=bool(probe.get('inside') and (area.isEmpty() or w.mask().contains(center)))
        report['菜单打开时可见形态中心的窗口探测']=format_trace(probe)
    report['最近背景取色']=data.colors
    report['当前基础文字颜色']=(w.colors or {}).get('ink')
    return report


def write_report(report,directory):
    payload=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    prefix='灵动胶囊诊断-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'
    stream=NamedTemporaryFile(mode='w',encoding='utf-8',prefix=prefix,suffix='.json',dir=directory,delete=False)
    path=Path(stream.name)
    try:
        with stream:stream.write(payload)
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return path


def export_report(report):
    title='导出灵动胶囊诊断日志'
    directory=QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    if not directory:directory=QFileDialog.getExistingDirectory(None,'选择诊断日志保存目录')
    while directory:
        try:path=write_report(report,directory)
        except OSError as error:
            QMessageBox.warning(None,title,f'无法写入所选目录。可选择其他目录重试。\n{error}')
            directory=QFileDialog.getExistingDirectory(None,'选择诊断日志保存目录')
        else:
            QMessageBox.information(None,title,'诊断日志已保存到\n'+str(path))
            return


def add_export_action(menu,service):
    captured=[]
    def capture():
        captured[:]=[snapshot(service)]
    def export():
        report=captured[0] if captured else snapshot(service)
        QTimer.singleShot(0,lambda:export_report(report))
    menu.aboutToShow.connect(capture)
    menu.addAction('导出诊断日志',export)
