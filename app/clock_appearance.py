"""Independent, validated desktop clock appearance."""
import re
from appearance_presets import MATERIALS

DEFAULTS={'design':'follow','material':'liquid','theme':'light','color':'#b8d9ef','opacity':38,'blur':8,'highlight':45,
          'typography_version':2,'font':'Segoe UI','font_scale':110,'text_color':'','text_effect':'clear','show_date':True,'hour_format':'24'}
DEFAULTS.update(layout='auto',align='left',date_font='Microsoft YaHei UI',date_scale=100,font_weight=63,letter_spacing=100,
                padding=7,accent_color='',text_opacity=100,shadow='none',auto_contrast=True,bar_width=8,ring_width=9,corner_radius=22,
                show_work=True,show_week=True,show_month=True,show_year=True,ring_mode='day',work={})
FONTS=[('现代宽体（推荐）','Segoe UI'),('几何数字','Bahnschrift'),('简洁中文','Microsoft YaHei UI')]
STYLES=[('现代数字','digital'),('现代表盘','analog'),('纵向时间','stacked'),('日历周览','calendar'),('时光进度','orbit'),('月历看板','month')]
PRESETS=[('轻透天空',dict(material='liquid',theme='light',color='#d8ebf7',accent_color='#337fad',opacity=56,blur=10,highlight=30,text_color='#19384e',text_effect='clear')),
         ('玉石青绿',dict(material='liquid',theme='light',color='#d4eee5',accent_color='#298471',opacity=60,blur=10,highlight=25,text_color='#1e433c',text_effect='clear')),
         ('柔雾薰衣',dict(material='acrylic',theme='light',color='#e6e0f3',accent_color='#8261ad',opacity=66,blur=14,highlight=20,text_color='#3b3154',text_effect='clear')),
         ('奶油杏桃',dict(material='liquid',theme='light',color='#f5e6d7',accent_color='#b47a45',opacity=64,blur=10,highlight=20,text_color='#513d2b',text_effect='clear')),
         ('珍珠留白',dict(material='solid',theme='light',color='#f4f7fa',accent_color='#557e9f',opacity=100,blur=8,highlight=12,text_color='#23374a',text_effect='clear')),
         ('夜间石墨',dict(material='mica',theme='dark',color='#344453',accent_color='#8dc7df',opacity=90,blur=12,highlight=20,text_color='#f1f7fb',text_effect='clear')),
         ('纯透明',dict(material='clear',theme='auto',color='',accent_color='#b5e0f0',opacity=0,blur=2,highlight=0,text_color='#ffffff',text_effect='clear'))]



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
    for key,allowed in [('design',{'follow'}|{value for _,value in DESIGNS}),('material',{v for _,v in MATERIALS}),('theme',{'auto','light','dark'}),('hour_format',{'12','24'}),('text_effect',{'glass','clear'}),('layout',{'auto','wide','portrait'}),('align',{'left','center'}),('shadow',{'none','soft'}),('ring_mode',{'day','work'})]:
        if not isinstance(result[key],str) or result[key] not in allowed:result[key]=DEFAULTS[key]
    for key,low,high in [('opacity',0,100),('blur',2,30),('highlight',0,100),('font_scale',60,180),('date_scale',70,150),('font_weight',50,87),('letter_spacing',90,115),('padding',4,14),('text_opacity',50,100),('bar_width',4,18),('ring_width',4,18),('corner_radius',8,36)]:
        value=result[key];result[key]=max(low,min(high,value)) if type(value) is int else DEFAULTS[key]
    for key in ('color','text_color','accent_color'):
        value=result[key];result[key]=value.lower() if isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value) else ''
    for key in ('font','date_font'):
        if not isinstance(result[key],str) or not result[key].strip() or len(result[key])>100:result[key]=DEFAULTS[key]
    for key in ('show_date','show_work','show_week','show_month','show_year','auto_contrast'):
        if type(result[key]) is not bool:result[key]=DEFAULTS[key]
    from work_schedule import normalize as work_options
    result['work']=work_options(result['work'])
    return result
