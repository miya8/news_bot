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
from gensim.models import KeyedVectors
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
                    RegexReplaceCharFilter(r'text|[ -/:-@!0-9\[-~]', '')]
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
        title_list.append(word_list_per_title)
    # 全title中で1回しか出現しない単語を削除
    dic = Dictionary(title_list)
    valid_word_list = [word_id for word_id, num in dic.dfs.items() if num > 1]
    title_list_2 = []
    for title in title_list:
        word_list_per_title_2 = [word for word in title if dic.token2id[word] in valid_word_list]
        # 要素が0のtitleを除外
        if len(word_list_per_title_2) > 0:
            title_list_2.append(word_list_per_title_2)
    return title_list_2, dic


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
            # 1行に複数のタイトルが含まれる。局ごとに異なる区切り文字で分割する。
            for line in lines:
                title_list = title_list + re.split(KYOKU_SEP_DICT[kyoku], line)
    return title_list


def create_rep_dict_one(dic, similar_list_dict, self_w_id):
    '''DF値最大の単語に置換する1行辞書を作成する'''
    
    rep_dict = {}
    dfs_max_w_id = self_w_id
    for w_id in similar_list_dict[self_w_id]:
        if not w_id in similar_list_dict.keys():
            continue
        if dic.dfs[w_id] > dic.dfs[dfs_max_w_id]:
            dfs_max_w_id = w_id
    # 自分がDF最大値の場合、他の単語を自分に置換する辞書を作成
    if dfs_max_w_id == self_w_id:
        rep_dict = {w_id: self_w_id for w_id in similar_list_dict[self_w_id]}
    # 他の単語がDF最大値の場合、その単語の類義語リストを辿る
    else:
        rep_dict = create_rep_dict_one(dic, similar_list_dict, dfs_max_w_id)
    return rep_dict


def create_rep_dict(dic, vec, rep_dict, similar_list_dict):
    '''類義語置換辞書を作成する'''
    
    # 類義語辞書1セット目を起点としてDF最大値の単語に合わせる置換辞書を作成
    tmp_rep_dict = create_rep_dict_one(dic, similar_list_dict, list(similar_list_dict.keys())[0])
    rep_dict.update(tmp_rep_dict)
    # 全類義語辞書セットを置換辞書の対象外の単語のみ残して更新
    del_k_list = []
    for k_w_id, sim_list in similar_list_dict.items():
        sim_list_new = []
        if k_w_id in list(tmp_rep_dict.keys()):
            del_k_list.append(k_w_id)
            continue
        for w_id in sim_list:
            if w_id in list(tmp_rep_dict.keys()):
                continue
            else:
                sim_list_new.append(w_id)
        sim_list_new = list(set(sim_list_new))
        similar_list_dict[k_w_id] = sim_list_new
        if len(sim_list_new) == 0:
            del_k_list.append(k_w_id)
    # 置換辞書のキーまたは要素がなくなった類義語辞書セットを削除
    for k_id in set(del_k_list):
        del similar_list_dict[k_id]
    return rep_dict, similar_list_dict


def get_replace_dict(dic, threshold=SIMILAR_THRESHOLD):
    '''dic内の語彙の類似語セットを作成し、類義語置換辞書を作成する'''

    # 学習済の単語分散表現を読込み
    vec_path = os.path.join(os.environ['WIKI_ENT_VEC_PATH'], 'jawiki.all_vectors.200d.txt')
    logger.debug('reading jawiki...')
    vec = KeyedVectors.load_word2vec_format(vec_path, binary=False)
    logger.debug('finished reading.')
    # コサイン類似度で類似語セットを作成
    similar_word_dict = {}
    ignored_word_list = []
    for self_id in dic.keys():
        try:
            _ = vec.word_vec(dic[self_id])
        except KeyError:
            ignored_word_list.append(dic[self_id])
            continue
        similar_word_list = []
        for word_id in dic.keys():
            try:
                _ = vec.word_vec(dic[word_id])
            except KeyError:
                continue
            similarity = vec.similarity(dic[self_id], dic[word_id])
            if similarity >= threshold and word_id != self_id:
                similar_word_list.append(word_id)
        if len(similar_word_list) > 0:
            similar_word_dict[self_id] = similar_word_list
    if len(ignored_word_list) > 0:
        logger.warning('Not included in word_vec, ignored.:{}'.format(ignored_word_list))
    # 類似語セットから類義語置換辞書を作成
    rep_dict = {}
    while len(similar_word_dict) > 0:
        rep_dict, similar_word_dict = create_rep_dict(dic, vec, rep_dict, similar_word_dict)
    return rep_dict


def replace_similar_word(dic, rep_dict, title_list):
    '''rep_dictに従い類義語を置換する'''
    
    title_list2 = []
    for title in title_list:
        title2 = []
        for word in title:
            rep_flg = False
            for key, val in rep_dict.items():
                if word == dic[key]:
                    title2.append(dic[val])
                    rep_flg = True
                    break
            if rep_flg == False:
                title2.append(word)
        title_list2.append(title2)
    return title_list2


def get_most_common(title_list, dic, num=COMMON_TOPIC_WORDS_NUM, random_state=None):
    '''最頻出の話題の単語num個のセットを取得する'''

    bow = [dic.doc2bow(title) for title in title_list]
    # TODO: 適切なトピック数を取得して設定する
    if LOG_LEVEL == 'DEBUG':
        random_state = 123
    model = LdaModel(bow, id2word=dic, num_topics=TOPIC_NUM, random_state=random_state)
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
        # titleごとのトピック分布
        df_topic_dist = pd.DataFrame({
            'title': title_list,
            'topic_id' :topic_id_list
        })
        # トピックごとの単語分布
        cols = ['{}_{}'.format(word_no, elem) \
                for word_no in range(10) \
                    for elem in range(2)]
        df_word_dist = pd.DataFrame()
        arr_dist = topic_dist_arr.reshape(-1, model.get_topics().shape[0], 2)
        for topic_id in range(model.get_topics().shape[0]):
            df_topic_dist['topic_{}'.format(topic_id)] = arr_dist[:, topic_id, 1]
            topic_terms = model.get_topic_terms(topic_id, topn=int(len(cols)/2))
            topic_terms_2 = []
            for term in topic_terms:
                topic_terms_2 = topic_terms_2 + [dic.id2token[term[0]], term[1]]
            df_word_dist = df_word_dist.append(
                pd.Series(topic_terms_2, name='topic_{}'.format(topic_id))
            )
        df_topic_dist.to_csv(
            os.path.join('test', 'classified_topic_{}.csv' \
                .format(datetime.today().strftime(format='%Y%m%d'))),
            index=False,
            encoding='cp932'
        )
        df_word_dist.columns = cols
        df_word_dist.to_csv(
            os.path.join('test', 'word_distribution_per_topic_{}.csv' \
                .format(datetime.today().strftime(format='%Y%m%d'))),
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
    title_list, dic = get_words(title_sentence_list, stop_words)
    if len(title_list) == 0:
        logger.warning('Interrupt news_bot_main.: No TV title data in target periods.')
        sys.exit(-1)
    # title_list内の類似語を1単語にまとめる
    replace_dict = get_replace_dict(dic)
    title_list2 = replace_similar_word(dic, replace_dict, title_list)
    # 最頻出の話題の重要な単語を取得
    common_topic_word_list = get_most_common(title_list2, dic)
    # 該当する単語でgoogleニュースを検索
    title_url_list = get_googlenews(common_topic_word_list)
    # Linebotする
    linebot.bot_to_line(title_url_list)


if __name__ == '__main__':
    main()
