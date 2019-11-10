import json
import os
import sys
import time
from datetime import date, timedelta, datetime
from logging import StreamHandler, getLogger
from pprint import pprint

import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))
from settings_newsbot import KYOKU_SEP_DICT
from common.util import requests_get, get_target_bangumi_name, remove_words

# ログ設定
LOG_LEVEL = 'DEBUG'
LOGGER_NAME = 'nhk'
# 未来何日分の番組情報を取得するか（NHKのAPIの仕様により過去は取得できない）
# 複数日分取得する場合、次回同日の番組情報を取得する際に上書きする
# 当日のみの場合は0を設定する
TARGET_DAYS = 0
# 取得対象の番組
TARGET_BANGUMI_DICT = {
    'おはよう日本': {
        'target': ['content', 'subtitle'],
        'rm_word': ['キャスター】', '今、知りたい！', '天気を気象予報士', 'まちかど情報室']
    },
    '週刊まるわかりニュース': {
        'target':  ['content', 'subtitle'],
        'rm_word': ['キャスター】', '気になるニュース']
    },
    'ＮＨＫニュース７': {
        'target':  ['content', 'subtitle'],
        'rm_word': ['キャスター】', '一歩先へ、一歩深く']
    },
    'ニュースウオッチ９': {
        'target':  ['content', 'subtitle'],
        'rm_word': ['キャスター】', 'きょうのニュース', '特集', '速報スポーツ', 
                    'スポーツ情報を速報', '突撃取材', '気象情報', 'キャスターが解説']
    },
    'ニュースきょう一日': {
        'target':  ['content', 'subtitle'],
        'rm_word': ['キャスター】', '押さえておきたいニュース', 'テレワークやってみた']
    },
    '時論公論': {
        'target':  ['content', 'subtitle'],
        'rm_word': ['社会がわかる', '時事問題を幅広く', '主要ニュース']
    },
    'クローズアップ現代': {
        'target':  ['content', 'subtitle'],
        'rm_word': ['キャスター】']
    },
    '日曜討論': {
        'target': 'subtitle',
        'rm_word': []
    }
}
# NHKのAPI呼出し用定義
NHK_URL = 'http://api.nhk.or.jp/v2/pg/genre/{area}/{service}/{genre}/{date}.json?key={apikey}'
NHK_ENV_NAME = 'NHK_API_KEY'
AREA = "130"
SERVICE = "g1"
JENRE = '0000'

logger = getLogger(LOGGER_NAME)
handler = StreamHandler()
logger.setLevel(LOG_LEVEL)
logger.addHandler(handler)

def get_nhk_program(target_day):
    '''NHKの番組表からニュース番組情報を取得する'''

    print('target_day ', target_day)
    url = NHK_URL.format(area=AREA,
                         service=SERVICE,
                         genre=JENRE,
                         date=target_day,
                         apikey=os.environ[NHK_ENV_NAME])
    status, contens_dict = requests_get(url, None, logger)
    if status != 200:
        logger.error('get_nhk_program_{} failed.'.format(target_day))
        sys.exit(-1)
    else:
        return contens_dict


def exract_target_data(f, contents_dict):
    '''必要な情報を抜き出してファイルに出力する'''

    for content in contents_dict['list']['g1']:
        # 取得対象の番組か判定
        target_name = get_target_bangumi_name(content['title'], TARGET_BANGUMI_DICT)
        if target_name is None:
            continue
        # 番組概要を取得
        print('target_name   ', target_name)
        text = ''
        for target_content in TARGET_BANGUMI_DICT[target_name]['target']:
            text += content[target_content] + KYOKU_SEP_DICT['nhk'][0]
        print('text  ', text)
        if text is None:
            continue
        text = remove_words(
            text.strip(),
            TARGET_BANGUMI_DICT[target_name]['rm_word'],
            KYOKU_SEP_DICT['nhk']
        )
        if text != '':
            f.write(text + '\n')


def main():
    for day_ago in range(0, TARGET_DAYS + 1):
        target_day = date.today() + timedelta(days=day_ago)
        print(target_day)
        # NHKの番組表からニュース情報を取得
        contents_dict = get_nhk_program(target_day)
        # 必要な情報をファイルへ出力
        file_path = os.path.join(os.path.join(os.path.dirname(__file__), '../../'),
                                 'nhk_news_{}.csv'
                                 .format(datetime.strftime(target_day, format='%Y%m%d')))
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info('file exists: {}, removed it.'.format(file_path))
        with open(file_path, mode='a', encoding='utf-8') as f:
            exract_target_data(f, contents_dict)


if __name__ == '__main__':
    main()
