import glob
import os
import sys
import re
import urllib
from collections import Counter
from datetime import datetime, timedelta
from logging import StreamHandler, getLogger
from pprint import pprint

import feedparser
import requests
from gensim.corpora import Dictionary
from gensim.models.ldamodel import LdaModel
from janome.analyzer import Analyzer, Tokenizer
from janome.charfilter import RegexReplaceCharFilter, UnicodeNormalizeCharFilter
from janome.tokenfilter import LowerCaseFilter, POSKeepFilter, POSStopFilter
import pandas as pd
import numpy as np

import linebot
from settings_newsbot import *


logger = getLogger(LOGGER_NAME)
handler = StreamHandler()
logger.setLevel(LOG_LEVEL)
logger.addHandler(handler)


def get_words(titles, stop_words):
    '''titlesを形態素解析し、下処理を適用した単語リストを作成する'''

    char_filters = [UnicodeNormalizeCharFilter(),
                    RegexReplaceCharFilter(r'text|[ -/:-@\[-~]', '')]
    token_filters = [POSKeepFilter(KEEP_FILTER),
                     POSStopFilter(STOP_FILTER),
                     LowerCaseFilter()]
    tokenizer = Tokenizer(mmap=True)
    analyzer = Analyzer(
        tokenizer=tokenizer,
        char_filters=char_filters,
        token_filters=token_filters
    )

    title_list = []
    for title in titles:
        word_list_per_title = []
        for word in analyzer.analyze(title):
            # アルファベット、平仮名、カタカナ1文字の単語を除外
            if (len(word.surface) == 1) \
                and (re.compile('[~a-zあ-んア-ン]').fullmatch(word.surface)):
                continue
            # ストップワードを除外
            if word.base_form in stop_words:
                continue
            hinshi_split = word.part_of_speech.split(',')
            hinshi_taple = (hinshi_split[0], hinshi_split[1])
            if hinshi_taple in WEIGHTS_HINSHI_DICT.keys():
                word_list_per_title += [word.base_form] * WEIGHTS_HINSHI_DICT[hinshi_taple]
            else:
                word_list_per_title.append(word.base_form)
        # 要素が0のtitleを除外
        if len(word_list_per_title) > 0:
            title_list.append(word_list_per_title)
    return title_list


def get_words_list_per_title(kyoku, min_date_str):
    '''ニュース内容のファイルから、タイトルのリストを取得する'''

    title_list = []
    # ニュース内容のファイル（局ごと）を取得
    file_name = TARGET_FILE_BASE_NAME.format(kyoku, '*')
    #file_name = TARGET_FILE_BASE_NAME.format(kyoku, '20191112')
    file_path_list = glob.glob(TARGET_DIR + os.sep + file_name)
    for file_path in file_path_list:
        if int(file_path.split('.')[-2][-8:]) < int(min_date_str):
            continue
        logger.info('reading ' + file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            lines_set = set(lines)
            # 完全重複する文章は、番組内容が未定の段階で使われる仮文章であるため削除する
            for line, cnt in Counter(lines).items():
                if cnt > 1:
                    lines_set.remove(line)
            lines = list(lines_set)
            # 1行に複数のタイトルが含まれる。局ごとに異なる区切り文字で分割する。
            for line in lines:
                title_list = title_list + re.split(KYOKU_SEP_DICT[kyoku], line)
    return title_list


def get_most_common(title_list, num=COMMON_TOPIC_WORDS_NUM, random_state=None):
    '''最頻出の話題の単語num個のセットを取得する'''

    dic = Dictionary(title_list)
    bow = [dic.doc2bow(title) for title in title_list]
    # TODO: 適切なトピック数を取得して設定する
    if LOG_LEVEL == 'DEBUG':
        random_state = 123
    model = LdaModel(bow, id2word=dic, num_topics=5, random_state=random_state)
    # 各タイトルを分類
    topic_id_list = []
    for idx, title in enumerate(title_list):
        logger.debug('title')
        logger.debug(title)
        doc_topics_tuple = model.get_document_topics(dic.doc2bow(title), minimum_probability=0.0)
        doc_topic_dist = [[val[0], val[1]] for val in doc_topics_tuple]
        doc_topic_dist = np.array(doc_topic_dist)
        if idx == 0:
            topic_dist_arr = doc_topic_dist
        else:
            topic_dist_arr = np.vstack([topic_dist_arr, doc_topic_dist])
        topic_id = int(sorted(doc_topic_dist, key=lambda x: x[1], reverse=True)[0][0])
        topic_id_list.append(topic_id)
    if LOG_LEVEL == 'DEBUG':
        df_dist = pd.DataFrame({
            'title': title_list,
            'topic_id' :topic_id_list
        })
        arr_dist = topic_dist_arr.reshape(-1, model.get_topics().shape[0], 2)
        for topic_id in range(model.get_topics().shape[0]):
            df_dist['topic_{}'.format(topic_id)] = arr_dist[:, topic_id, 1]
        df_dist.to_csv(
            os.path.join('test', 'classified_topic_{}.csv' \
                .format(datetime.today().strftime(format='%Y%m%d'))),
            index=False,
            encoding='cp932'
        )
    # 最頻出の話題を取得
    topic_id_counter = Counter(topic_id_list)
    most_common_topic_id = topic_id_counter.most_common(1)[0][0]
    topic_terms = model.get_topic_terms(most_common_topic_id)
    logger.debug('')
    logger.debug('topic_id_counter: ' + str(topic_id_counter))
    logger.debug('most_common_topic_id: ' + str(most_common_topic_id))
    logger.debug(topic_terms)
    # 最頻出の話題の重要な単語num個を取得
    important_word_list = [dic.id2token[topic_tuple[0]]
                           for topic_tuple in topic_terms[:num]]
    logger.debug(important_word_list)
    return important_word_list


def scrape_googlenews(words_list, num=SCRAPE_NEWS_NUM):
    '''ニュースサイトから、単語リストにマッチする最新記事のリンクを返す'''

    keyword = '+'.join(words_list)
    keyword_encoded = urllib.parse.quote(keyword)
    url = 'http://news.google.com/news?hl=ja&ned=ja&ie=UTF-8&oe=UTF-8&output=rss&q=' + keyword_encoded
    title_url_list = []
    for entry in feedparser.parse(url).entries[:num]:
        title_url_list.append((entry.title, entry.link))
    logger.debug(title_url_list)
    return title_url_list


def main():

    # 読み込み対象とする最小日付
    min_date = (datetime.today() - timedelta(days=TARGET_DAYS)
                ).strftime(format='%Y%m%d')
    # SlothLibのストップワードを取得
    url = 'http://svn.sourceforge.jp/svnroot/slothlib/CSharp/Version1/SlothLib/NLP/Filter/StopWord/word/Japanese.txt'
    stop_words = requests.get(url).text.split('\r\n')
    stop_words = stop_words + STOP_WORDS_ADDITIONAL
    # ニュース欄のタイトルを取得
    title_sentence_list = []
    for kyoku in KYOKU_SEP_DICT.keys():
        title_sentence_list += get_words_list_per_title(kyoku, min_date)
    # タイトルごとの単語リスト取得
    title_list = get_words(title_sentence_list, stop_words)
    if len(title_list) < 0:
        logger.warn('Interrupt news_bot_main.: No TV title data in target periods.')
        sys.exit(-1)
    # 最頻出の話題の重要な単語を取得
    common_topic_word_list = get_most_common(title_list)
    # 該当する単語でgoogleニュースを検索
    title_url_list = scrape_googlenews(common_topic_word_list)
    # Linebotする
    linebot.bot_to_line(title_url_list)


if __name__ == '__main__':
    main()
