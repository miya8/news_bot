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
                    RegexReplaceCharFilter(r'text|[ -/:-@0-9\[-~]', '')]
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
    file_path_list = glob.glob(TARGET_DIR + os.sep + file_name)
    for file_path in file_path_list:
        if int(file_path.split('.')[-2][-8:]) < int(min_date_str):
            continue
        logger.info('reading ' + file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 1行に複数のタイトルが含まれる。局ごとに異なる区切り文字で分割する。
            for line in lines:
                title_list = title_list + re.split(KYOKU_SEP_DICT[kyoku], line)
    return title_list

def get_cooccurrence_words(titles, freq_word_id_list, dic):
    '''
    most_freq_word_list の単語セットと共起する単語と共起したドキュメント数を取得する。
    共起する単語とは、対象の単語セットを含むtitle内の他の単語を指す。
    '''

    co_word_list = []
    for title in titles:
        word_ids_in_doc = [word[0] for word in dic.doc2bow(title)]
        if set(freq_word_id_list) <= set(word_ids_in_doc):
            word_ids = list(set(word_ids_in_doc) - set(freq_word_id_list))
            co_word_list = co_word_list + word_ids
    if len(co_word_list) > 0:
        return Counter(co_word_list)
    else:
        return None

def decide_cooccurrence_word_most(word_id_list, dfs):
    '''
    word_id_listの中でdfs(その単語を含むドキュメント数)が最大の単語を取得する
    最大となる単語が複数ある場合は先に出現した単語を採用する
    '''

    if len(word_id_list) == 1:
        return word_id_list[0]
    else:
        logger.debug('multiple most frequent words found.')
        dfs_max_word_id = None
        for word_id in word_id_list:
            if dfs_max_word_id == None:
                dfs_max_word_id = word_id
            elif dfs[word_id] > dfs[dfs_max_word_id]:
                dfs_max_word_id = word_id
        return dfs_max_word_id

def get_most_common(title_list, num=COMMON_TOPIC_WORDS_NUM, random_state=None):
    '''最頻出の話題の単語num個のセットを取得する'''

    dic = Dictionary(title_list)
    freq_word_id_dict = dic.dfs
    # 1つ目の重要単語を取得
    most_freq_word_id = sorted(freq_word_id_dict.items(), key=lambda x: x[1], reverse=True)[0][0]
    most_freq_word = dic[most_freq_word_id]
    logger.debug('most_freq_word: {}'.format(most_freq_word))
    # 2つ目以降の重要単語を取得
    important_word_id_list = [most_freq_word_id]
    for important_word_no in range(1, num):
        logger.debug('seeking no.{} freq word...'.format(important_word_no))
        co_word_cnt_dict =  get_cooccurrence_words(title_list, important_word_id_list, dic)
        if co_word_cnt_dict is None:
            break
        else:
            logger.debug('co_word_cnt_dict(~5): {}'.format(co_word_cnt_dict.most_common(5)))
            co_most_num = co_word_cnt_dict.most_common(1)[0][1]
            logger.debug('co_most_num: {}'.format(co_most_num))
            # 最多単語が複数ある場合、dfs(その単語を含むドキュメント数)の大きい単語を採用する
            # 更にdfsも同値だった場合は先に出現した単語を採用とする
            co_most_word_id_list = \
                [word_id for word_id, cnt in co_word_cnt_dict.items()  if cnt == co_most_num]
            co_most_word_id = \
                decide_cooccurrence_word_most(co_most_word_id_list, freq_word_id_dict)
            important_word_id_list.append(co_most_word_id)
    important_word_list = [dic[word_id] for word_id in important_word_id_list]
    logger.debug('important_word_list: {}'.format(important_word_list))
    return important_word_list


def get_googlenews(words_list, num=SCRAPE_NEWS_NUM):
    '''ニュースサイトから、単語リストにマッチする最新記事のリンクを返す'''

    keyword = '+'.join(words_list)
    keyword_encoded = urllib.parse.quote(keyword)
    url = 'http://news.google.com/news?hl=ja&ned=ja&ie=UTF-8&oe=UTF-8&output=rss&q={}' \
            .format(keyword_encoded)
    title_url_dict = {}
    for entry in feedparser.parse(url).entries[:10 if num<=5 else num*2]:
        title_url_dict[(entry.title, entry.link)] = datetime(*entry.published_parsed[:6])
    title_url_list = [(key[0], key[1]) \
        for key, _ in sorted(title_url_dict.items(), key=lambda x: x[1], reverse=True)[:num]]
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
    # 完全重複する文章を削除（当日の番組表のみ取得できない局は複数ファイルに同じ番組情報が記載されるため）
    title_sentence_list = list(set(title_sentence_list))
    # タイトルごとの単語リスト取得
    title_list = get_words(title_sentence_list, stop_words)
    if len(title_list) == 0:
        logger.warning('Interrupt news_bot_main.: No TV title data in target periods.')
        sys.exit(-1)
    # 最頻出の話題の重要な単語を取得
    common_topic_word_list = get_most_common(title_list)
    # 該当する単語でgoogleニュースを検索
    title_url_list = get_googlenews(common_topic_word_list)
    # Linebotする
    linebot.bot_to_line(title_url_list)


if __name__ == '__main__':
    main()
