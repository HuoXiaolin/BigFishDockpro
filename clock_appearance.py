"""Independent, validated desktop clock appearance."""
import re
from appearance_presets import MATERIALS

DEFAULTS={'design':'follow','material':'liquid','theme':'light','color':'#b8d9ef','opacity':38,'blur':8,'highlight':45,
          'typography_version':2,'font':'Segoe UI','font_scale':110,'text_color':'','text_effect':'glass','show_date':True,'hour_format':'24'}
FONTS=[('现代宽体（推荐）','Segoe UI'),('几何数字','Bahnschrift'),('简洁中文','Microsoft YaHei UI')]
STYLES=[('现代数字','digital'),('现代表盘','analog'),('纵向时间','stacked'),('日历周览','calendar'),('时光进度','orbit'),('月历看板','month')]
PRESETS=[('轻透天空',dict(material='liquid',theme='light',color='#b8d9ef',opacity=38,blur=8,highlight=45,text_color='')),
         ('柔雾晨光',dict(material='acrylic',theme='light',color='#e3ddf6',opacity=64,blur=16,highlight=35,text_color='')),
         ('深海夜色',dict(material='mica',theme='dark',color='#71869b',opacity=86,blur=12,highlight=25,text_color='')),
         ('全透明',dict(material='clear',theme='auto',color='',opacity=0,blur=2,highlight=0,text_color=''))]


def normalize(value, cfg=None):
    result=dict(DEFAULTS)
    if not value and cfg:
        for key in ('material','theme','color','opacity','blur','highlight'):
            result[key]=cfg.get('panel_'+key,result[key])
    if isinstance(value,dict):
        for key in result:
            if key in value:result[key]=value[key]
    if isinstance(value,dict):
        if 'typography_version' not in value and value.get('font','Segoe UI')=='Segoe UI':
            if value.get('font_scale',100)==100:result['font_scale']=110
        elif value.get('typography_version')==1 and value.get('font')=='Bahnschrift' and value.get('font_scale')==110:
            result['font']='Segoe UI'
    result['typography_version']=2
    from card_design import DESIGNS
    for key,allowed in [('design',{'follow'}|{value for _,value in DESIGNS}),('material',{v for _,v in MATERIALS}),('theme',{'auto','light','dark'}),('font',{v for _,v in FONTS}),('hour_format',{'12','24'}),('text_effect',{'glass','clear'})]:
        if not isinstance(result[key],str) or result[key] not in allowed:result[key]=DEFAULTS[key]
    for key,low,high in [('opacity',0,100),('blur',2,30),('highlight',0,100),('font_scale',60,150)]:
        value=result[key];result[key]=max(low,min(high,value)) if type(value) is int else DEFAULTS[key]
    for key in ('color','text_color'):
        value=result[key];result[key]=value.lower() if isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value) else ''
    if type(result['show_date']) is not bool:result['show_date']=True
    return result
