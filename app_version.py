import json
from pathlib import Path

METADATA = json.loads(Path(__file__).with_name('version.json').read_text(encoding='utf-8-sig'))
VERSION = METADATA['version']
AUTHOR = METADATA['author']

PROJECT_ID = METADATA['project_id']
DISPLAY_NAME = '大肥鱼Dock'
PROJECT_URL = METADATA.get('repository_url', 'https://github.com/HuoXiaolin/BigFishDockpro')
