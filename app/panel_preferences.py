"""Shared desktop-card appearance options; geometry and contents remain local."""
FOLD_SIZE_RANGE = (24, 120)
CARD_FOLD_SIZE = 44
NOTE_FOLD_SIZE = 42
ICON_ALIGNMENTS = (('左对齐','left'), ('居中','center'), ('右对齐','right'))

KEYS=('appearance_source','backdrop_mode','material','theme','color','highlight','opacity','blur','layer','locked','auto_hide','collapse_style','capsule_ratio','ball_diameter','fold_height',
      'face','face_interactive','face_mood','face_role','face_scale','face_auto_switch','face_switch_minutes','expand_mode')
CONFIG_KEYS=tuple('panel_'+key for key in KEYS)


def values(cfg):return {key:cfg['panel_'+key] for key in KEYS}


def without_overrides(models):
    return [{key:value for key,value in model.items() if key not in KEYS} for model in models]
