"""On-demand charts and rankings for the local usage counters."""
import datetime as dt
import weakref

from PyQt5.QtCore import QEvent, QLineF, QRectF, Qt
from PyQt5.QtGui import QPainter, QPalette
from PyQt5.QtWidgets import (QBoxLayout, QGridLayout, QHBoxLayout, QLayout, QMessageBox, QSizePolicy, QTabBar, QToolTip,
                             QVBoxLayout, QWidget)

from ui_style import ModernComboBox, button, label, widget_px
from usage_stats import EVENTS, daily_counts

RANGES = (7, 30, 90)


class DailyChart(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(105)
        self.series = []

    def set_series(self, series):
        self.series = series
        self.setAccessibleName('每日操作次数')
        self.setAccessibleDescription('；'.join(self.describe(day, count) for day, count in series))
        self.update()

    @staticmethod
    def describe(day, count):
        return f'{day:%Y-%m-%d} · ' + ('统计开始前' if count is None else f'{count:,} 次')

    def plot(self):
        maximum = max((count or 0 for _, count in self.series), default=0)
        step = 1
        if maximum >= 3:
            unit = 10 ** (len(str(maximum//3))-1)
            step = next(i*unit for i in (1, 2, 5, 10) if i*unit*3 > maximum)
        ticks = [f'{i*step:,}' for i in range(4)]
        left = self.fontMetrics().horizontalAdvance(ticks[-1]) + 10
        return QRectF(left, 9, max(1, self.width()-left-4), max(1, self.height()-29)), step, ticks

    def paintEvent(self, event):
        if not self.series:
            return
        p = QPainter(self)
        palette = self.palette()
        plot, step, ticks = self.plot()
        muted = palette.color(QPalette.PlaceholderText)
        line = palette.color(QPalette.Midlight)
        line.setAlpha(145)
        for i, tick in enumerate(ticks):
            y = plot.bottom()-plot.height()*i/3
            p.setPen(line)
            p.drawLine(QLineF(plot.left(), y, plot.right(), y))
            p.setPen(muted)
            p.drawText(QRectF(0, y-9, plot.left()-6, 18), Qt.AlignRight | Qt.AlignVCenter, tick)
        slot = plot.width()/len(self.series)
        width = min(20., slot*.72)
        accent = palette.color(QPalette.Link)
        for i, (_, count) in enumerate(self.series):
            if count:
                height = plot.height()*(count/(step*3))
                p.fillRect(QRectF(plot.left()+(i+.5)*slot-width/2, plot.bottom()-height, width, height), accent)
        p.setPen(muted)
        last = len(self.series)-1
        for i in range(4):
            index = round(i*last/3)
            day = self.series[index][0]
            x = plot.left()+slot*(index+.5)
            tick = f'{day.month}/{day.day}'
            half = self.fontMetrics().horizontalAdvance(tick)/2+2
            x = max(half, min(self.width()-half, x))
            p.drawText(QRectF(x-half, plot.bottom()+4, 2*half, 17), Qt.AlignCenter, tick)

    def event(self, event):
        if event.type() == QEvent.ToolTip and getattr(self, 'series', None):
            plot, _, _ = self.plot()
            if plot.contains(event.pos()):
                index = min(len(self.series)-1, int((event.pos().x()-plot.left())*len(self.series)/plot.width()))
                QToolTip.showText(event.globalPos(), self.describe(*self.series[index]), self)
                return True
            QToolTip.hideText()
        return super().event(event)


class RankBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.share = 0

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().color(QPalette.Midlight))
        p.fillRect(QRectF(0, 0, self.width()*self.share, self.height()), self.palette().color(QPalette.Link))


class UsagePage(QWidget):
    def __init__(self, dialog, form, view_state):
        super().__init__(form.parentWidget())
        self._dialog = weakref.ref(dialog)
        self.store = dialog.tray.runtime.usage
        self.fields = {}
        self.status = label('', 'muted')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.build(*view_state)
        form.addRow(self)

    def build(self, days, scope):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)
        page_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.overview = self.panel('本机使用概览')
        self.overview.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.overview_grid = QGridLayout()
        self.overview_grid.setHorizontalSpacing(16)
        self.overview_grid.setVerticalSpacing(6)
        self.overview.layout().addLayout(self.overview_grid)
        self.tiles = []
        for key, caption in (('today','今日操作'), ('total','累计操作'), ('starts','软件启动'), ('duration','累计运行时长')):
            tile = QWidget()
            cell = QVBoxLayout(tile)
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setSpacing(2)
            cell.addWidget(label(caption, 'muted'))
            field = self.fields[key] = label('—', 'usage-value')
            field.setAccessibleName(caption)
            cell.addWidget(field)
            self.tiles.append(tile)
        page_layout.addWidget(self.overview)
        self.overview_columns = 0
        self.layout_overview(2)

        analysis = QWidget(self)
        self.analysis_layout = QBoxLayout(QBoxLayout.TopToBottom, analysis)
        self.analysis_layout.setContentsMargins(0, 0, 0, 0)
        self.analysis_layout.setSpacing(10)
        page_layout.addWidget(analysis)

        trend_box = self.panel('每日操作趋势', parent=analysis)
        trend = trend_box.layout()
        controls = QHBoxLayout()
        controls.setSpacing(5)
        self.range_tabs = QTabBar()
        self.range_tabs.setObjectName('UsageRange')
        self.range_tabs.setAccessibleName('统计时间范围')
        self.range_tabs.setDrawBase(False)
        self.range_tabs.setExpanding(False)
        for period in RANGES:
            self.range_tabs.addTab(f'{period} 天')
        self.range_tabs.setCurrentIndex(RANGES.index(days))
        controls.addWidget(self.range_tabs)
        controls.addStretch()
        controls.addWidget(button('刷新', self.refresh))
        trend.addLayout(controls)
        self.range_summary = label('', 'muted')
        trend.addWidget(self.range_summary)
        self.chart = DailyChart()
        trend.addWidget(self.chart)

        ranking_heading = label('功能排行', 'group-title')
        ranking_heading.setWordWrap(False)
        ranking_box = self.panel(parent=analysis)
        ranking = ranking_box.layout()
        self.ranking_scope = ModernComboBox()
        self.ranking_scope.setObjectName('UsageRankingScope')
        self.ranking_scope.setFixedWidth(122)
        self.ranking_scope.setAccessibleName('功能排行统计范围')
        self.ranking_scope.addItem('所选时段', 'period')
        self.ranking_scope.addItem('全部累计', 'total')
        self.ranking_scope.setCurrentIndex(self.ranking_scope.findData(scope))
        filter_row = QHBoxLayout()
        filter_row.addWidget(ranking_heading, 1)
        filter_row.addWidget(self.ranking_scope)
        ranking.addLayout(filter_row)
        self.empty_ranking = label('所选范围暂无操作记录。', 'muted')
        ranking.addWidget(self.empty_ranking)
        self.ranking = QWidget()
        self.rank_layout = QVBoxLayout(self.ranking)
        self.rank_layout.setContentsMargins(0, 0, 0, 0)
        self.rank_layout.setSpacing(8)
        self.rank_rows = {}
        for key, caption in EVENTS.items():
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)
            line = QHBoxLayout()
            line.addWidget(label(caption), 1)
            amount = label('', 'setting-value')
            amount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            line.addWidget(amount)
            row_layout.addLayout(line)
            bar = RankBar()
            row_layout.addWidget(bar)
            self.rank_rows[key] = (row, amount, bar)
            self.rank_layout.addWidget(row)
        ranking.addWidget(self.ranking)
        self.analysis_layout.addWidget(trend_box, 3, Qt.AlignTop)
        self.analysis_layout.addWidget(ranking_box, 2, Qt.AlignTop)

        self.management = self.panel()
        management = self.management.layout()
        reset_row = QHBoxLayout()
        reset_row.addWidget(label('统计管理', 'group-title'), 1)
        reset_row.addWidget(button('重置统计…', self.reset, 'danger'))
        management.addLayout(reset_row)
        self.since = label('', 'muted')
        management.addWidget(self.since)
        management.addWidget(label('统计仅保存在本机，独立于配置备份。累计运行时长为 Dock 程序运行时间。', 'muted'))
        management.addWidget(self.status)
        page_layout.addWidget(self.management)
        page_layout.addStretch()
        self.refresh()
        self.range_tabs.currentChanged.connect(self.show_range)
        self.ranking_scope.currentIndexChanged.connect(self.show_ranking)

    def panel(self, title='', parent=None):
        box = QWidget(parent or self)
        box.setObjectName('SettingsGroup')
        box.setAttribute(Qt.WA_StyledBackground)
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(6)
        if title:
            layout.addWidget(label(title, 'group-title'))
        return box

    def resizeEvent(self, event):
        wide = self.width() >= widget_px(self, 560)
        direction = QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom
        if direction != self.analysis_layout.direction():
            self.analysis_layout.setDirection(direction)
            for index, stretch in enumerate((3, 2)):
                self.analysis_layout.setStretch(index, stretch if direction == QBoxLayout.LeftToRight else 0)
        super().resizeEvent(event)
        columns = 4 if wide else 2
        if columns != self.overview_columns:
            self.layout_overview(columns)
            self.layout().activate()

    def layout_overview(self, columns):
        if self.overview_columns == columns:
            return
        self.overview_columns = columns
        while self.overview_grid.count():
            self.overview_grid.takeAt(0)
        for index, tile in enumerate(self.tiles):
            self.overview_grid.addWidget(tile, index//columns, index%columns, Qt.AlignTop)
        for index in range(len(self.tiles)):
            self.overview_grid.setColumnStretch(index, 1 if index < columns else 0)

    def view_state(self):
        return (RANGES[self.range_tabs.currentIndex()], self.ranking_scope.currentData())

    def refresh(self, persist=True):
        if persist:
            self.store.flush()
        self.data = self.store.snapshot()
        self.today = dt.date.today()
        hours, remainder = divmod(self.data['seconds'], 3600)
        values = {
            'today': f"{sum(self.data['days'].get(self.today.isoformat(), {}).values()):,} 次",
            'total': f"{sum(self.data['counts'].values()):,} 次",
            'starts': f"{self.data['starts']:,} 次",
            'duration': f'{hours:,} 小时 {remainder//60} 分钟' if hours else f'{remainder//60} 分钟',
        }
        for key, value in values.items():
            self.fields[key].setText(value)
        self.since.setText('开始统计于 '+self.data['since'].replace('T', ' '))
        self.status.setText(self.store.error or '')
        self.status.setVisible(bool(self.store.error))
        self.show_range()

    def show_range(self):
        daily = daily_counts(self.data, self.today, self.view_state()[0])
        series = [(day, None if counts is None else sum(counts.values())) for day, counts in daily]
        self.period_counts = {key: 0 for key in EVENTS}
        for _, counts in daily:
            for key, count in (counts or {}).items():
                self.period_counts[key] += count
        total = sum(self.period_counts.values())
        peak_day, peak = max(reversed(series), key=lambda entry: entry[1] or 0)
        summary = f'共 {total:,} 次 · {sum(bool(count) for _, count in series)} 天有操作'
        if peak:
            summary += f' · {peak_day.month}/{peak_day.day} 峰值 {peak:,} 次'
        self.range_summary.setText(summary)
        self.chart.set_series(series)
        self.show_ranking()

    def show_ranking(self):
        counts = self.data['counts'] if self.ranking_scope.currentData()=='total' else self.period_counts
        total = sum(counts.values())
        self.empty_ranking.setVisible(not total)
        self.ranking.setVisible(bool(total))
        for index, key in enumerate(sorted(EVENTS, key=counts.__getitem__, reverse=True)):
            row, amount, bar = self.rank_rows[key]
            self.rank_layout.removeWidget(row)
            self.rank_layout.insertWidget(index, row)
            count = counts[key]
            row.setVisible(bool(count))
            share = count/total if total else 0
            amount.setText(f'{count:,} 次  ·  {share:.1%}')
            bar.share = share
            bar.update()

    def reset(self):
        box = QMessageBox(QMessageBox.Question, '重置使用统计',
                          '清空本机的使用次数、运行时长和历史记录，从现在重新统计？',
                          QMessageBox.Yes | QMessageBox.Cancel, self._dialog())
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec_()!=QMessageBox.Yes:
            return
        if self.store.reset():
            self.refresh(persist=False)
            self.status.setText('使用统计已重置。')
        else:
            self.status.setText('重置失败，原统计数据已保留。')
        self.status.show()
