import os
import sys
from datetime import date, timedelta
from pprint import pprint

import scrapy

sys.path.append('news')
from news.items import NewsItem
from news.middlewares_selenium import close_driver_chrome
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))
from settings_newsbot import KYOKU_SEP_DICT
from common.util import get_target_bangumi_name, remove_words

# 番組表URLフォーマット
TARGET_URL_FORMAT = 'https://www.fujitv.co.jp/timetable/daily/index.html?day={}'
# 未来何日分の番組情報を取得するか（NHKのAPIの仕様により過去は取得できない）
# 複数日分取得する場合、次回同日の番組情報を取得する際に上書きする
# 当日のみの場合は0を設定する
TARGET_DAYS = 0

TARGET_BANGUMI_DICT = {
    'めざましテレビ': {'rm_word': ['今知りたい情報']},
    'めざましどようび': {'rm_word': ['お出かけ前の今、知りたい！']},
    'FNN Live News days': {'rm_word': ['「ライブニュース デイズ」', '「Live News days」']},
    'FNN Live News it！': {'rm_word': ['ニュース・スポーツを一挙紹介', '最新情報からエンタメ']},
    'FNN Live News α': {'rm_word': ['その日あったことを短時間']},
    'FNNニュース': {'rm_word': ['日曜日の朝は「FNNニュース」']},
    '日曜報道 THE PRIME': {'rm_word': ['本格報道の新たな形']},
    'とくダネ！': {'rm_word': ['']},
    '直撃LIVE グッディ！': {'rm_word': ['']}
}

target_days = []
for day_ago in range(0, TARGET_DAYS + 1):
    target_days.append(
        (date.today() + timedelta(days=day_ago)).strftime(format='%Y%m%d'))


class FujiSpider(scrapy.Spider):
    name = 'fuji'
    allowed_domains = ['www.fujitv.co.jp']
    start_urls = [TARGET_URL_FORMAT.format(day) for day in target_days]
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "news.middlewares_selenium.SeleniumMiddleware": 0,
        }
    }

    def parse(self, response):
        for bangumi in response.css('div#wrap').css('td.info'):
            text = ''
            if bangumi.css('span.inform::text').extract_first() == '報道・情報':
                bangumi_name = bangumi.css('a::text').extract_first()
                # 取得対象の番組か判定
                target_name = get_target_bangumi_name(bangumi_name, TARGET_BANGUMI_DICT)
                if target_name is None:
                    continue
                # 番組概要を取得
                text = bangumi.css('p.tx_pad::text').extract_first()
                if text is None:
                    continue
                text = remove_words(
                    text.strip(),
                    TARGET_BANGUMI_DICT[target_name]['rm_word'],
                    KYOKU_SEP_DICT['fuji']
                )
            item = NewsItem()
            if text != '':
                item['text'] = text
                yield item

    def closed(self, response):
        close_driver_chrome()
