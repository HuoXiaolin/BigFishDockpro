"""Shared desktop-card appearance options; geometry and contents remain local."""
KEYS=('material','theme','color','highlight','opacity','blur','locked','auto_hide','collapse_style','capsule_ratio')
CONFIG_KEYS=tuple('panel_'+key for key in KEYS)


def values(cfg):return {key:cfg['panel_'+key] for key in KEYS}


def without_overrides(models):
    return [{key:value for key,value in model.items() if key not in KEYS} for model in models]
