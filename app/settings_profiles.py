"""Global appearance controls use the settings dialog's existing Save transaction."""
import copy
from PyQt5.QtWidgets import QComboBox,QSpinBox,QLineEdit,QHBoxLayout
from ui_style import ModernComboBox,button,label
from appearance_profiles import MODES,TOP_KEYS,snapshot,apply_snapshot,apply_profile,selected_mode

class AppearanceProfileMixin:
    def create_profile_controls(self,form):
        from settings_design import section_marker
        self._profile_loading=True;self._profile_dirty=False;self._profile_overlay=None
        self._profile_custom={};self._profile_mode='custom'
        section_marker(form,'整体外观')
        self.overall_style=ModernComboBox();self.overall_style.setAccessibleName('整体主题样式')
        for name,key in MODES:self.overall_style.addItem(name,key)
        row=QHBoxLayout();row.addWidget(self.overall_style,1)
        self.restore_style=button('全部恢复默认',self.restore_all_styles);row.addWidget(self.restore_style)
        form.addRow(row)
        form.addRow(label('应用到 Dock、卡片、便签、时钟和日历；切换前的自定义外观会保留。','muted'))
        self.overall_style.currentIndexChanged.connect(self.choose_overall_style)

    def initialize_profile_controls(self):
        for key in TOP_KEYS:
            field=self.fields.get(key)
            if field is None:continue
            signal=field.currentIndexChanged if isinstance(field,QComboBox) else field.valueChanged if isinstance(field,QSpinBox) else field.textChanged if isinstance(field,QLineEdit) else field.toggled
            signal.connect(self.mark_profile_custom)
        self.load_profile(self.tray.cfg)

    def load_profile(self,cfg):
        self._profile_loading=True
        self._profile_custom=copy.deepcopy(cfg.get('appearance_custom',{}))
        self._profile_mode=selected_mode(cfg)
        self._profile_overlay=None;self._profile_dirty=False
        self.overall_style.setCurrentIndex(self.overall_style.findData(self._profile_mode))
        self._profile_loading=False

    def mark_profile_custom(self,*args):
        if self._profile_loading:return
        self._profile_dirty=True;self._profile_mode='custom'
        blocked=self.overall_style.blockSignals(True);self.overall_style.setCurrentIndex(0);self.overall_style.blockSignals(blocked)
        self.refresh_preset_names(self.profile_candidate())

    def profile_candidate(self):
        cfg=copy.deepcopy(self.import_candidate if self.import_candidate is not None else self.tray.cfg)
        if self._profile_overlay:cfg=apply_snapshot(cfg,self._profile_overlay)
        for key in TOP_KEYS:
            field=self.fields.get(key)
            if field is None:continue
            value=field.currentData() if isinstance(field,QComboBox) else field.value() if isinstance(field,QSpinBox) else field.text().strip() if isinstance(field,QLineEdit) else field.isChecked()
            cfg[key]=100-value if key=='transparency' else value
        return cfg

    def choose_overall_style(self,*args):
        if self._profile_loading:return
        target=self.overall_style.currentData();current=self.profile_candidate()
        if self._profile_mode=='custom' and target!='custom':self._profile_custom=snapshot(current)
        current['appearance_custom']=copy.deepcopy(self._profile_custom)
        defaults=self.api.normalize_features(copy.deepcopy(self.api.DEFAULT_CONFIG))
        candidate=apply_profile(current,target,defaults)
        self._profile_overlay=snapshot(candidate);self._profile_mode=target;self._profile_dirty=True
        self._profile_loading=True;self.applying_dock_preset=True
        for key in TOP_KEYS:
            field=self.fields.get(key)
            if field is None:continue
            value=candidate[key];blocked=field.blockSignals(True)
            if key in ('dock_material','panel_material'):
                from appearance_presets import select_material
                select_material(field,value)
            elif isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
            elif isinstance(field,QSpinBox):field.setValue(100-value if key=='transparency' else value)
            elif isinstance(field,QLineEdit):field.setText(value)
            else:field.setChecked(value)
            field.blockSignals(blocked)
        # Spin signals were blocked to avoid intermediate preset/custom states.
        from settings_design import NumericControl
        for control in self.findChildren(NumericControl):control.slider.setValue(control.spin.value())
        self.refresh_preset_names(candidate)
        self.applying_dock_preset=False;self._profile_loading=False
        self.dock_preview.update()
        self.status.setText('已载入'+self.overall_style.currentText()+'，保存后应用；位置、尺寸和内容保留。')

    def restore_all_styles(self):
        index=self.overall_style.findData('default')
        if self.overall_style.currentIndex()==index:self.choose_overall_style()
        else:self.overall_style.setCurrentIndex(index)

    def stage_profile(self,cfg):
        if not self._profile_dirty:return cfg
        if self._profile_overlay:
            edited={key:copy.deepcopy(cfg[key]) for key in TOP_KEYS if key in self.fields}
            cfg=apply_snapshot(cfg,self._profile_overlay);cfg.update(edited)
        cfg['appearance_mode']=self._profile_mode
        cfg['appearance_custom']=snapshot(cfg) if self._profile_mode=='custom' else copy.deepcopy(self._profile_custom)
        cfg['appearance_applied']=snapshot(cfg)
        return cfg

    def refresh_preset_names(self,cfg):
        from appearance_presets import DOCK_PRESETS,PANEL_PRESETS
        for combo,presets,prefix in ((self.dock_preset,DOCK_PRESETS,''),(self.panel_preset,PANEL_PRESETS,'panel_')):
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
