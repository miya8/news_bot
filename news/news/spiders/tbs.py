import os
import sys

import scrapy

sys.path.append('news')
from news.items import NewsItem
from news.middlewares_selenium import close_driver_chrome
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))
from common.util import remove_words
from settings_newsbot import KYOKU_SEP_DICT


TARGET_BANGUMI_DICT = {
    'はやドキ！': {'rm_word': ['最新のニュース']}, 
    'あさチャン！': {'rm_word': ['あさチャン！']}, 
    'グッとラック！': {'rm_word': ['社会派ネタから生活情報']}, 
    'ひるおび！': {'rm_word': ['ニュースの「真相、裏側」']}, 
    '情報７ｄａｙｓニュースキャスター': {'rm_word': ['生放送で総まとめ']}, 
    'ＮＥＷＳ２３': {'rm_word': ['注目のニュース']},
    'ＴＢＳ　ＮＥＷＳ': {'rm_word': ['日本各地の最新ニュース']},
    'まるっと！サタデー': {'rm_word': ['一週間のニュース']},
    'サンデーモーニング': {'rm_word': ['世界と日本の出来事']},
    '報道特集': {'rm_word': ['地道な深い調査報道']}
}

class TbsSpider(scrapy.Spider):
    name = 'tbs'
    allowed_domains = ['www.tbs.co.jp']
    start_urls = ['https://www.tbs.co.jp/tv/index.html']


    def parse(self, response):
        for bangumi in response.css('div.news'):
            item = NewsItem()
            text = bangumi.css('strong::text').extract_first()
            for target_bangumi in TARGET_BANGUMI_DICT.keys():
                if not target_bangumi in text:
                    continue
                desc_url = bangumi.css('a::attr(href)').extract_first()
                yield response.follow(desc_url,
                                        callback=self.parse_desc_page,
                                        meta={
                                            'item': item,
                                            'target_name': target_bangumi
                                        })


    def parse_desc_page(self, response):
        item = response.meta['item']
        target_name = response.meta['target_name']
        text = response.css('div.copy-box').css('p::text').extract_first()
        if not text is None:
            text = remove_words(
                text.strip(),
                TARGET_BANGUMI_DICT[target_name]['rm_word'],
                KYOKU_SEP_DICT['tbs']
            )
        if text != '':
            item['text'] = text
            yield item


    def closed(self, response):
        close_driver_chrome()
