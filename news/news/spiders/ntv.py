import os
import sys
import re

import scrapy

sys.path.append('news')
from news.items import NewsItem
from news.middlewares_selenium import close_driver_chrome
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))
from settings_newsbot import KYOKU_SEP_DICT
from common.util import remove_words, get_target_bangumi_name

TARGET_BANGUMI_DICT = {
    'Oha!4 NEWS LIVE': {'rm_word': ['Oha!4から', '放送内容は']}, 
    'ZIP!': {'rm_word': ['ZIP!', '放送内容は']},
    'news zero': {'rm_word': ['ZIP!は', '放送内容は']},
    'news every.': {'rm_word': ['ニュースを分かりやすく', '放送内容は']},
    'スッキリ': {'rm_word': ['朝を元気に!', '事件も政治も経済', '｢今｣に触れる大特集', 'ゲストも登場']},
    '真相報道 バンキシャ!': {'rm_word': ['バンキシャ!は毎週']}
}


class NtvSpider(scrapy.Spider):
    name = 'ntv'
    allowed_domains = ['www.ntv.co.jp']
    start_urls = ['http://www.ntv.co.jp/program/']

    def parse(self, response):
        for bangumi in response.css('tbody td'):
            item = NewsItem()
            text = ''
            oa = bangumi.css('p.oa::text').extract_first()
            if oa is None:
                continue
            if re.match(r'\d{2}\:\d{2}', oa.strip()):
                bangumi_name = bangumi.css('h3::text').extract_first().split()
                # 取得対象の番組か判定
                target_name = get_target_bangumi_name(bangumi_name, TARGET_BANGUMI_DICT)
                if target_name is None:
                    continue
                # 番組概要を取得
                text = bangumi.css('p::text').extract()[1]
                if text is None:
                    continue
                text = remove_words(
                    text.strip(),
                    TARGET_BANGUMI_DICT[target_name]['rm_word'],
                    KYOKU_SEP_DICT['ntv']
                )
                desc_url = bangumi.css('a::attr(href)').extract_first().strip()
                yield response.follow(
                    desc_url,
                    callback=self.parse_desc_page,
                    meta={
                        'item': item,
                        'text': text,
                        'target_name': target_name
                    }
                )


    def parse_desc_page(self, response):
        item = response.meta['item']
        text = response.meta['text']
        target_name = response.meta['target_name']
        text_tmp = ''
        for info in response.css('div.program'):
            if info.css('h2::text').extract_first() == '詳細':
                text_tmp = info.css('p::text').extract_first()
                break
        if (text_tmp != '') and (not text_tmp is None):
            text_tmp = remove_words(
                text_tmp.strip(),
                TARGET_BANGUMI_DICT[target_name]['rm_word'],
                KYOKU_SEP_DICT['ntv']
            )
            text = text_tmp
        if text != '':
            item['text'] = text
            yield item


    def closed(self, response):
        close_driver_chrome()
        