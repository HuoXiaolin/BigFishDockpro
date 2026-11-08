"""Global appearance controls use the settings dialog's existing Save transaction."""
import copy
from PyQt5.QtWidgets import QComboBox,QSpinBox,QLineEdit,QHBoxLayout
from ui_style import ModernComboBox,button,label
from appearance_profiles import MODES,TOP_KEYS,snapshot,apply_snapshot,switch_profile,selected_mode

class AppearanceProfileMixin:
    def create_profile_controls(self,form):
        from settings_design import section_marker
        section_marker(form,'整体外观')
        self.overall_style=ModernComboBox();self.overall_style.setAccessibleName('整体主题样式')
        for name,key in MODES:self.overall_style.addItem(name,key)
        row=QHBoxLayout();row.addWidget(self.overall_style,1)
        self.restore_style=button('全部恢复默认',self.restore_all_styles);row.addWidget(self.restore_style)
        form.addRow(row)
        form.addRow(label('适用于 Dock 和桌面组件，会保留切换前的自定义外观。','muted'))
        self.overall_style.currentIndexChanged.connect(self.choose_overall_style)

    def connect_profile_fields(self, keys):
        for key in keys:
            if key in TOP_KEYS:
                self.change_signal(self.fields[key]).connect(self.mark_profile_custom)

    def load_profile(self,cfg):
        self._profile_loading=True
        self._profile_custom=copy.deepcopy(cfg.get('appearance_custom',{}))
        self._profile_mode=selected_mode(cfg)
        self._profile_overlay=None;self._profile_dirty=False
        self.sync_profile_selector()
        self._profile_loading=False

    def sync_profile_selector(self):
        combo = self.__dict__.get('overall_style')
        if combo is not None:
            blocked = combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(self._profile_mode))
            combo.blockSignals(blocked)

    def mark_profile_custom(self,*args):
        if self._profile_loading:return
        self._profile_dirty=True;self._profile_mode='custom'
        self.sync_profile_selector()
        self.refresh_preset_names(self.profile_candidate())

    def profile_candidate(self):
        cfg = dict(self.import_candidate if self.import_candidate is not None else self.tray.cfg)
        if self._profile_overlay:
            cfg = apply_snapshot(cfg, self._profile_overlay)
        draft = self.draft_values()
        cfg.update({key: draft[key] for key in TOP_KEYS if key in draft})
        return cfg

    def choose_overall_style(self,*args):
        if self._profile_loading:return
        target=self.overall_style.currentData();current=self.profile_candidate()
        current['appearance_custom']=self._profile_custom
        defaults=self.api.normalize_features(copy.deepcopy(self.api.DEFAULT_CONFIG)) if target=='default' else None
        candidate=switch_profile(current,target,self._profile_mode,defaults)
        self._profile_custom=candidate['appearance_custom']
        self._profile_overlay=candidate['appearance_applied'];self._profile_mode=target;self._profile_dirty=True
        self.show_profile_fields(candidate)
        self.status.setText('已载入'+self.overall_style.currentText()+'，保存后应用；位置、尺寸和内容保留。')

    def show_profile_fields(self, candidate):
        self._profile_loading = True
        self.applying_dock_preset = True
        try:
            self.set_draft_values({key: candidate[key] for key in TOP_KEYS if key in self.catalog})
            self.refresh_preset_names(candidate)
        finally:
            self.applying_dock_preset = False
            self._profile_loading = False
        preview = self.__dict__.get('dock_preview')
        if preview is not None:
            preview.update()

    def restore_all_styles(self):
        index=self.overall_style.findData('default')
        if self.overall_style.currentIndex()==index:self.choose_overall_style()
        else:self.overall_style.setCurrentIndex(index)

    def stage_profile(self,cfg):
        if not self._profile_dirty:return cfg
        if self._profile_overlay:
            edited={key:copy.deepcopy(cfg[key]) for key in TOP_KEYS if key in self.catalog}
            cfg=apply_snapshot(cfg,self._profile_overlay);cfg.update(edited)
        cfg['appearance_mode']=self._profile_mode
        cfg['appearance_custom']=snapshot(cfg) if self._profile_mode=='custom' else copy.deepcopy(self._profile_custom)
        cfg['appearance_applied']=snapshot(cfg)
        return cfg

    def refresh_preset_names(self,cfg):
        from appearance_presets import DOCK_PRESETS,PANEL_PRESETS
        for name,presets,prefix in (('dock_preset',DOCK_PRESETS,''),('panel_preset',PANEL_PRESETS,'panel_')):
            combo = self.__dict__.get(name)
            if combo is None:
                continue
            matched=next((i for i,(_,values) in enumerate(presets,1) if all(cfg.get(prefix+key)==value for key,value in values.items())),0)
            blocked=combo.blockSignals(True);combo.setCurrentIndex(matched);combo.blockSignals(blocked)

    def apply_panel_preset(self,index):
        if index<=0:return
        from appearance_presets import PANEL_PRESETS
        for key,value in PANEL_PRESETS[index-1][1].items():
            field=self.fields['panel_'+key]
            if isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
            elif isinstance(field,QLineEdit):field.setText(value)
            else:field.setValue(value)
        self.refresh_preset_names(self.profile_candidate())
