"""Reset-card quantities are independent of quota percentages and usage dates."""
from collections import Counter
from datetime import datetime
from functools import lru_cache


def applicable(provider):
    return provider.get('id','').lower()=='codex' or isinstance(provider.get('resetCredits'),dict)


def credit_count(provider):
    data=provider.get('resetCredits') or {}
    count=data.get('available')
    return count if isinstance(count,int) and not isinstance(count,bool) and count>=0 else None


def expiry_rows(provider):
    rows=[]
    for value in (provider.get('resetCredits') or {}).get('expiries',[])[:128]:
        try:rows.append(datetime.fromisoformat(value.replace('Z','+00:00')).astimezone().strftime('%Y-%m-%d %H:%M'))
        except (ValueError,TypeError,AttributeError):pass
    return sorted(Counter(rows).items())


def summary(provider):
    count=credit_count(provider)
    if count is None:
        status=(provider.get('resetCredits') or {}).get('status')
        return '重置卡 · '+({'signin':'需要重新登录','not_provided':'账户未提供','unavailable':'暂不可用'}.get(status,'等待读取'))
    return f'重置卡 {count} 张可用'


def expiry_note(provider):
    rows=expiry_rows(provider)
    if rows:return '最近到期 '+rows[0][0][5:]
    return '有效期未提供' if (credit_count(provider) or 0)>0 else ''


def badge_text(provider):
    count=credit_count(provider)
    if count is None:return summary(provider).split(' · ',1)[-1]
    rows=expiry_rows(provider)
    return f'{count} 张'+(' · '+rows[0][0][5:]+' 到期' if rows else ' · 有效期未提供' if count else '')


@lru_cache(maxsize=8)
def card_icon(ink):
    from PyQt5.QtCore import Qt,QRectF,QPointF
    from PyQt5.QtGui import QPixmap,QIcon,QPainter,QPen,QColor
    pix=QPixmap(40,40);pix.setDevicePixelRatio(2);pix.fill(Qt.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ink),1.3,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(2.5,6,14,10),2,2)
    p.drawLine(QPointF(5,3.5),QPointF(16,3.5));p.drawLine(QPointF(16,3.5),QPointF(18.5,6))
    p.drawLine(QPointF(3,9.5),QPointF(16,9.5));p.drawLine(QPointF(5.5,13),QPointF(8,13));p.end()
    return QIcon(pix)


def show_details(parent,provider):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView
    from ui_style import button,exec_dialog
    from popup_style import prepare_popup
    dialog=QDialog(parent);dialog.setWindowTitle(provider.get('name','AI')+' · 重置卡')
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    dialog.resize(390,280);lay=QVBoxLayout(dialog);lay.setContentsMargins(16,12,16,12);lay.setSpacing(10)
    title=QLabel(summary(provider));title.setProperty('role','title');lay.addWidget(title)
    rows=expiry_rows(provider)
    if rows:
        table=QTableWidget(len(rows),2);table.setHorizontalHeaderLabels(['到期时间','数量'])
        table.verticalHeader().hide();table.setShowGrid(False);table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        table.verticalHeader().setDefaultSectionSize(32)
        for i,(expiry,count) in enumerate(rows):
            table.setItem(i,0,QTableWidgetItem(expiry));item=QTableWidgetItem(f'{count} 张');item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter);table.setItem(i,1,item)
        lay.addWidget(table,1)
    else:
        note=QLabel('当前没有可用重置卡。' if credit_count(provider)==0 else '服务暂未提供有效期明细。')
        note.setWordWrap(True);lay.addWidget(note,1)
    close=button('关闭',dialog.accept);lay.addWidget(close,0,Qt.AlignRight)
    prepare_popup(dialog);exec_dialog(dialog)
