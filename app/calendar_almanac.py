"""Offline illustrations, verses and Chinese civil dates for the desktop almanac."""
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
import json
from pathlib import Path
import sys

from calendar_details import lunar_details

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'almanac'
FIRST_DAY, LAST_DAY = date(1901, 1, 1), date(2099, 12, 31)

# The six term illustrations in each season follow the agricultural year.
SEASONS = {
    'spring': [('立春','春冬移律吕，天地换星霜。'), ('雨水','雨水洗春容，平田已见龙。'),
               ('惊蛰','阳气初惊蛰，韶光大地周。'), ('春分','二气莫交争，春分雨处行。'),
               ('清明','清明来向晚，山渌正光华。'), ('谷雨','谷雨春光晓，山川黛色青。')],
    'summer': [('立夏','欲知春与夏，仲吕启朱明。'), ('小满','小满气全时，如何靡草衰。'),
               ('芒种','芒种看今日，螗螂应节生。'), ('夏至','处处闻蝉响，须知五月中。'),
               ('小暑','倏忽温风至，因循小暑来。'), ('大暑','大暑三秋近，林钟九夏移。')],
    'autumn': [('立秋','不期朱夏尽，凉吹暗迎秋。'), ('处暑','向来鹰祭鸟，渐觉白藏深。'),
               ('白露','露沾蔬草白，天气转青高。'), ('秋分','琴弹南吕调，风色已高清。'),
               ('寒露','寒露惊秋晚，朝看菊渐黄。'), ('霜降','风卷清云尽，空天万里霜。')],
    'winter': [('立冬','霜降向人寒，轻冰渌水漫。'), ('小雪','莫怪虹无影，如今小雪时。'),
               ('大雪','积阴成大雪，看处乱霏霏。'), ('冬至','二气俱生处，周家正立年。'),
               ('小寒','小寒连大吕，欢鹊垒新巢。'), ('大寒','腊酒自盈樽，金炉兽炭温。')],
}
FESTIVALS = {
    'festivals-a': [('春节','爆竹声中一岁除，春风送暖入屠苏。'), ('元宵节','月上柳梢头，人约黄昏后。'),
                    ('龙抬头','二月二日新雨晴，草芽菜甲一时生。'), ('端午节','彩线轻缠红玉臂。'),
                    ('七夕','金风玉露一相逢，便胜却人间无数。'), ('中元节','今夕知何夕，白露涵秋空。')],
    'festivals-b': [('中秋节','但愿人长久，千里共婵娟。'), ('重阳节','遥知兄弟登高处，遍插茱萸少一人。'),
                    ('腊八节','小孩小孩你别馋，过了腊八就是年。'), ('北方小年','二十三，糖瓜粘。'),
                    ('南方小年','二十四，扫房子。'), ('除夕','故乡今夜思千里，霜鬓明朝又一年。')],
}

# Each row adds three independent lines to the opening verse above. Traditional
# poetry and common sayings are interspersed with short verses for the artwork.
OTHER_VERSES = {
    '立春': ('春到人间草木知。','一犁翻软土，双燕认新泥。','柳梢初染绿，水面已生纹。'),
    '雨水': ('好雨知时节，当春乃发生。','一夜青溪涨，山田听水声。','檐前初滴水，柳外又归鸿。'),
    '惊蛰': ('微雨众卉新，一雷惊蛰始。','桃枝才动色，石罅已闻虫。','蛙醒池边草，春雷隔岸来。'),
    '春分': ('春分麦起身，一刻值千金。','半池春水绿，一线纸鸢高。','昼夜平分日，新燕啄春泥。'),
    '清明': ('清明时节雨纷纷。','燕子来时新社，梨花落后清明。','一伞穿村雨，青团带草香。'),
    '谷雨': ('谷雨前后，种瓜点豆。','山家新摘雨前茶。','细雨催新笋，青筐盛嫩芽。'),
    '立夏': ('绿阴铺野换新光。','樱熟红盈盏，梅青半掩枝。','荷钱初出水，蜻影过桥西。'),
    '小满': ('小满小满，麦粒渐满。','风来青麦俯，雀起一畦晴。','未黄先饱穗，轻露压芒尖。'),
    '芒种': ('芒种忙，麦上场。','稻田新水绿，麦垄晚风黄。','秧针分浅水，白鹭立田塍。'),
    '夏至': ('东边日出西边雨。','日长篱影短，荷动一池风。','榴火临阶照，蝉声绕树来。'),
    '小暑': ('小暑过，一日热三分。','竹扇摇青影，莲蓬带晚凉。','蝉鸣高柳外，风过小池东。'),
    '大暑': ('接天莲叶无穷碧，映日荷花别样红。','瓜瓤红似火，井水送清凉。','小院蒲扇慢，疏星到竹床。'),
    '立秋': ('一叶落而知天下秋。','梧叶无声落，庭阶先得秋。','昨夜风过竹，今朝露满篱。'),
    '处暑': ('处暑禾田连夜变。','暑退荷塘静，舟归一水秋。','雁字初排远，芦花未肯白。'),
    '白露': ('蒹葭苍苍，白露为霜。','露从今夜白，月是故乡明。','蛛丝悬玉粒，日出一时明。'),
    '秋分': ('秋分秋分，昼夜平分。','稻香浮水面，雁影过山梁。','一筐新摘果，半是晚霞红。'),
    '寒露': ('袅袅凉风动，凄凄寒露零。','岸菊经寒瘦，汀芦带露明。','一行秋雁过，双影落寒塘。'),
    '霜降': ('霜叶红于二月花。','一树灯笼柿，半坡霜后红。','霜白枫犹赤，山空鸟自闲。'),
    '立冬': ('北风潜入悄无声。','野水芦花白，疏林夕照低。','一窗冬日暖，盘里饺儿香。'),
    '小雪': ('晚来天欲雪，能饮一杯无。','桥边初着雪，溪上尚闻流。','几粒朱红果，一枝新雪轻。'),
    '大雪': ('千树万树梨花开。','门前深雪里，昨夜一枝开。','松枝擎白玉，屋脊戴银冠。'),
    '冬至': ('冬至阳生春又来。','天时人事日相催。','一碗团圆子，长宵分外甜。'),
    '小寒': ('小寒时处二三九，天寒地冻冷到抖。','鹊筑枝间暖，冰凝水底青。','冻苇摇晴雪，孤禽落夕阳。'),
    '大寒': ('大寒年年有，不在三九在四九。','不经一番寒彻骨，怎得梅花扑鼻香。','残冰封曲岸，红萼报新春。'),
    '春节': ('千门万户曈曈日，总把新桃换旧符。','春帖宜春字，屠苏献寿杯。','门前春帖赤，座上笑声长。'),
    '元宵节': ('东风夜放花千树。','火树银花合，星桥铁锁开。','鱼灯游巷口，碗底白珠圆。'),
    '龙抬头': ('二月二，龙抬头。','一线东风起，青龙上纸鸢。','春畦生嫩甲，早雨过溪头。'),
    '端午节': ('端午临中夏，时清日复长。','五色新丝缠角粽。','艾叶青盈户，龙舟鼓过江。'),
    '七夕': ('七夕今宵看碧霄，牵牛织女渡河桥。','纤云弄巧，飞星传恨。','银汉低垂处，一针穿月明。'),
    '中元节': ('坛滴槐花露，香飘柏子风。','纸莲随水去，一点一乡思。','灯影过秋岸，星河落水中。'),
    '中秋节': ('海上生明月，天涯共此时。','今夜月明人尽望，不知秋思落谁家。','桂影浮金盏，清辉照满庭。'),
    '重阳节': ('待到重阳日，还来就菊花。','尘世难逢开口笑，菊花须插满头归。','一径茱萸赤，登高望故乡。'),
    '腊八节': ('腊七腊八，冻掉下巴。','枣红莲子白，文火煮寒香。','一勺分新粥，晨窗起白烟。'),
    '北方小年': ('糖瓜祭灶，新年来到。','灶上糖瓜脆，窗前剪纸红。','糖香黏指尖，笑语候新年。'),
    '南方小年': ('掸尘扫旧岁，蒸糕迎新年。','笼开年糕白，灶暖橘灯红。','庭前尘扫尽，新岁自门来。'),
    '除夕': ('共欢新故岁，迎送一宵中。','寒辞去冬雪，暖带入春风。','岁晚围炉坐，灯红待晓钟。'),
}


@dataclass(frozen=True)
class Illustration:
    name: str
    key: str
    verses: tuple


ART = {name: Illustration(name, f'{group}-{index}', (verse,*OTHER_VERSES[name]))
       for group, entries in (SEASONS | FESTIVALS).items()
       for index, (name, verse) in enumerate(entries, 1)}

CIVIL_HOLIDAYS = {
    (1, 1): Illustration('元旦', 'civil-new-year', (
        '万象从新起，一晨迎岁光。', '昨宵星未落，今朝日更新。',
        '翻开新一页，且把春光候。', '一缕晨光入，万家新岁来。')),
    (3, 8): Illustration('妇女节', 'civil-womens-day', (
        '她向春风里，坚定自成光。', '各有花开处，同怀向远心。',
        '春光终有意，献与每一程。', '自有风华在，何须借月明。')),
    (3, 12): Illustration('植树节', 'civil-arbor-day', (
        '今日栽新绿，他年纳晚凉。', '一锹春土柔，半尺小芽新。',
        '前人栽树，后人乘凉。', '且种庭前木，听风过满枝。')),
    (5, 1): Illustration('劳动节', 'civil-labour-day', (
        '一双勤作手，百业有新声。', '汗随春日落，万物自成形。',
        '铸就寻常事，方知寸寸功。', '一分耕耘，一分收获。')),
    (5, 4): Illustration('青年节', 'civil-youth-day', (
        '趁此春风好，携书走远方。', '少年心事当拏云。',
        '青衿逢旭日，行路有回声。', '前路多山水，一步一晴明。')),
    (6, 1): Illustration('儿童节', 'civil-childrens-day', (
        '儿童散学归来早，忙趁东风放纸鸢。', '小手牵风去，笑声落草间。',
        '泡泡飞过篱笆，童心追着云霞。', '纸鸢牵细线，一路到晴空。')),
    (9, 10): Illustration('教师节', 'civil-teachers-day', (
        '随风潜入夜，润物细无声。', '一灯照书页，两鬓染秋霜。',
        '春风化雨，桃李成蹊。', '拾笔传微火，清光在此间。')),
    (10, 1): Illustration('国庆节', 'civil-national-day', (
        '秋色铺山海，灯明照万家。', '金风吹广陌，街巷共良辰。',
        '山河入画卷，烟火在人间。', '长街灯似昼，共赏此秋光。')),
}
ART.update((art.name, art) for art in CIVIL_HOLIDAYS.values())
_names = tuple(name for entries in SEASONS.values() for name, verse in entries)
JANUARY_ORDER = _names[-2:] + _names[:-2]


@lru_cache(maxsize=1)
def _table():
    payload = json.loads((ASSETS / 'solar-terms.json').read_text(encoding='utf-8'))
    return payload['first_year'], payload['years']


@lru_cache(maxsize=4)
def term_dates(year):
    first, years = _table()
    if not 0 <= year-first < len(years):
        return ()
    digits = years[year-first]
    return tuple((date(year, i//2+1, int(digits[2*i:2*i+2])), name)
                 for i, name in enumerate(JANUARY_ORDER))


@lru_cache(maxsize=16)
def next_festival(day):
    for i in range(1, min(366, (LAST_DAY-day).days)+1):
        on = day + timedelta(days=i)
        name = lunar_details(on)[2]
        if name:
            return name, i
    return '', 0


def next_civil_holiday(day):
    for (month, number), art in CIVIL_HOLIDAYS.items():
        holiday = date(day.year, month, number)
        if holiday > day:
            return art.name, (holiday-day).days
    return CIVIL_HOLIDAYS[1, 1].name, (date(day.year+1, 1, 1)-day).days


ROTATION_MINUTES = 10


def verse_index(now):
    return (now.hour*60 + now.minute) // ROTATION_MINUTES % 4


def edition(now):
    return verse_index(now) % 2


def until_rotation(now):
    boundary = now.replace(second=0, microsecond=0) + timedelta(minutes=ROTATION_MINUTES-now.minute%ROTATION_MINUTES)
    return max(1, int((boundary-now).total_seconds()*1000)+1)


@dataclass(frozen=True)
class AlmanacDay:
    day: date
    lunar: str
    term: str
    term_today: bool
    next_term: str
    days_left: int
    festival: str
    civil_festival: str

    @property
    def events(self):
        return tuple(name for name in (self.civil_festival, self.festival, self.term if self.term_today else '') if name)

    def card(self, choice=0):
        events = self.events
        return ART[events[choice % len(events)] if events else self.term]

    def civil_countdown(self):
        if self.civil_festival:
            return f'今日{self.civil_festival}'
        holiday, distance = next_civil_holiday(self.day)
        return f'距{holiday} {distance} 天'

    def badge(self):
        names = ([self.festival] if self.festival else []) + ([self.term] if self.term_today else [])
        return ' · '.join(names) if names else f'{self.next_term} {self.days_left}天'


@lru_cache(maxsize=32)
def almanac(day):
    if not FIRST_DAY <= day <= LAST_DAY:
        return None
    entries = term_dates(day.year-1) + term_dates(day.year) + term_dates(day.year+1)
    at = bisect_right(entries, day, key=lambda entry: entry[0])
    previous, term = entries[at-1] if at else (None, '冬至')
    upcoming, name = entries[at]
    _, lunar, festival = lunar_details(day)
    civil = CIVIL_HOLIDAYS.get((day.month, day.day))
    return AlmanacDay(day, lunar, term, previous == day, name, (upcoming-day).days, festival, civil.name if civil else '')
