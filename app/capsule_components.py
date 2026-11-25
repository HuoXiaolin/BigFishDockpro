"""The active capsule tab mounts the same native component used on the desktop."""
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from resource_charts import DashboardCard
from resource_pages import CapsuleScrollArea
from ui_style import ModernComboBox


class CapsuleComponentView(CapsuleScrollArea):
    def __init__(self,window,key):
        super().__init__()
        self.runtime=window.service.runtime
        self.key=key
        self.selected=None
        self.active=False
        self.items=None
        body=QWidget()
        layout=QVBoxLayout(body)
        layout.setContentsMargins(3,2,3,2)
        layout.setSpacing(5)
        self.picker=None
        if key=='custom':
            self.picker=ModernComboBox()
            self.picker.setAccessibleName('选择原生卡片')
            self.picker.setProperty('glassField',True)
            self.picker.currentIndexChanged.connect(self.selection_changed)
            layout.addWidget(self.picker)
        tones={'clock':'sky','calendar':'mint','notes':'paper','picture':'lavender','custom':'ice'}
        self.host=DashboardCard(window,tones[key])
        slot=QVBoxLayout(self.host)
        inset=0 if key in ('clock','calendar') else 4
        slot.setContentsMargins(inset,inset,inset,inset)
        layout.addWidget(self.host)
        layout.addStretch()
        self.setWidget(body)

    def refresh(self):
        if self.picker is None:return
        cfg=self.runtime.dock.cfg
        rows=cfg['custom_cards']
        items=tuple((row['id'],row['title']) for row in rows if row['visible'])
        if items==self.items:return
        self.items=items
        blocked=self.picker.blockSignals(True)
        self.picker.clear()
        for identity,title in items:self.picker.addItem(title,identity)
        self.picker.setCurrentIndex(max(0,self.picker.findData(self.selected)))
        self.picker.blockSignals(blocked)
        self.picker.setVisible(len(items)>1)
        self.selection_changed()

    def select(self,identity):
        if self.picker is not None:
            index=self.picker.findData(identity)
            if index>=0:self.picker.setCurrentIndex(index)

    def selection_changed(self):
        identity=self.picker.currentData()
        if identity!=self.selected:
            self.selected=identity
            if self.active:
                before=self.runtime.resources.active_keys()
                self.runtime.sync_hosted_component(self.key)
                if self.key=='custom' and before!=self.runtime.resources.active_keys():
                    self.runtime.resources.sync()

    def showEvent(self,event):
        super().showEvent(event)
        self.refresh()
        self.active=True
        self.runtime.sync_hosted_component(self.key)

    def hideEvent(self,event):
        self.active=False
        self.runtime.sync_hosted_component(self.key)
        super().hideEvent(event)
