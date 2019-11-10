import os
import sys
import re
from datetime import date

import scrapy

sys.path.append('news')
from news.middlewares_selenium import close_driver_chrome
from news.items import NewsItem
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))
from common.util import remove_words, get_target_bangumi_name
from settings_newsbot import KYOKU_SEP_DICT

# rm_wordの2つ目も出現した場合、
TARGET_BANGUMI_DICT = {
    'グッド!モーニング': {'rm_word': ['「朝の情報まとめ番組」']},
    'モーニングショー': {'rm_word': ['様々なニュースを']},
    'スーパーJチャンネル': {'rm_word': ['知りたいニュース・情報']},
    '報道ステーション': {'rm_word': ['知っておくべきニュース']},
    'サタデーステーション': {'rm_word': ['知りたいニュース']},
    'サンデーLIVE!!': {'rm_word': ['知りたいニュース', '東山紀之']},
    '週刊ニュースリーダー': {'rm_word': ['様々なニュース', '気になる人物']}
}


class AsahiSpider(scrapy.Spider):
    name = 'asahi'
    allowed_domains = ['www.tv-asahi.co.jp']
    start_urls = ['https://www.tv-asahi.co.jp/bangumi/index.html']

    def parse(self, response):
        youbi_cd = date.today().weekday()
        for idx, bangumi_list in enumerate(response.css('td[valign="top"]')):
            # 対象外（当日の曜日以外）の番組情報は取得しない
            if idx != youbi_cd:
                continue
            item = NewsItem()
            text = ''
            # 取得対象の番組の概要テキストのみ取得
            for bangumi in bangumi_list.css('table.new_day'):
                bangumi_name = bangumi.css(
                    'span.prog_name a.bangumiDetailOpen::text').extract_first()
                if bangumi_name is None:
                    continue
                target_name = get_target_bangumi_name(
                    bangumi_name.strip(), TARGET_BANGUMI_DICT)
                if target_name is None:
                    continue
                print(bangumi_name)
                text = bangumi.css(
                    'span.expo_org a.bangumiDetailOpen::text').extract_first()
                if text is None:
                    continue
                text = remove_words(
                    text,
                    TARGET_BANGUMI_DICT[target_name]['rm_word'],
                    KYOKU_SEP_DICT['asahi']
                )
                if text != '':
                    item['text'] = text
                    yield item

    def closed(self, response):
        close_driver_chrome()
