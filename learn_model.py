import glob
import os
import sys
import re
import urllib
from collections import Counter
from datetime import datetime, timedelta
from logging import StreamHandler, getLogger
#from pprint import pprint

#import feedparser
import requests
from gensim.corpora import Dictionary
from gensim.models.ldamodel import LdaModel
from janome.analyzer import Analyzer, Tokenizer
from janome.charfilter import RegexReplaceCharFilter, UnicodeNormalizeCharFilter
from janome.tokenfilter import LowerCaseFilter, POSKeepFilter, POSStopFilter

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


def learn_model(title_list, num=COMMON_TOPIC_WORDS_NUM, random_state=None):
    '''LDAモデルを学習して保存する'''

    dic = Dictionary(title_list)
    bow = [dic.doc2bow(title) for title in title_list]
    # TODO: 適切なトピック数を取得して設定する
    if LOG_LEVEL == 'DEBUG':
        random_state = 123
    model = LdaModel(bow, id2word=dic, num_topics=TOPIC_NUM, random_state=random_state)
    model.save('test\\lda_topics{}'.format(TOPIC_NUM))


def main():

    # 読み込み対象とする最小日付
    min_date = (datetime.today() - timedelta(days=TARGET_LEARN_DAYS)
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
    # LDAモデルの学習と保存
    learn_model(title_list)


if __name__ == '__main__':
    main()
