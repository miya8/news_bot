import scrapy
import sys
sys.path.append('news')
from news.items import NewsItem

class TbsSpider(scrapy.Spider):
    name = 'tbs'
    allowed_domains = ['www.tbs.co.jp']
    start_urls = ['https://www.tbs.co.jp/tv/index.html']
    target_bangumi_list = ['あさチャン！', 'ＮＥＷＳ２３']

    def parse(self, response):
        for bangumi in response.css('div.news'):
            item = NewsItem()
            text = bangumi.css('strong::text').extract_first()
            for target_bangumi in TbsSpider.target_bangumi_list:
                if not target_bangumi in text:
                    continue
                desc_url = bangumi.css('a::attr(href)').extract_first()
                yield response.follow(desc_url,
                                        callback=self.parse_desc_page,
                                        meta={'item': item})

    def parse_desc_page(self, response):
        item = response.meta['item']
        item['text'] = response.css('div.copy-box').css('p::text').extract_first().strip()
        yield item
