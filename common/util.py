'''共通で使用する関数をまとめる'''

import json
import os
from urllib.parse import urlencode

import requests


def requests_post(url, headers, body, logger, encode=False, safe=''):
    '''指定したurlにpostする'''

    if encode:
        body_encoded = urlencode(body, safe=safe)
        response = requests.post(url, data=body_encoded, headers=headers)
    else:
        body_encoded = json.dumps(body).encode("utf-8")
        response = requests.post(url, data=body_encoded, headers=headers)
    logger.debug('requests_post: status_code: {}'.format(response.status_code))
    if response.status_code != 200:
        logger.warning('requests_post: post failed. status_code: {}{}{}'.format(
            response.status_code, os.linesep, response.text))
    return response.status_code, json.loads(response.text)


def requests_get(url, params, logger, encode=False, safe=''):
    '''指定したurlからgetする'''

    if encode:
        params = urlencode(params, safe=safe)
        response = requests.get('{}?{}'.format(url, params))
    else:
        response = requests.get(url, params=params)
    response.encoding = response.apparent_encoding
    logger.debug('requests_post: status_code: {}'.format(response.status_code))
    if response.status_code != 200:
        logger.warning('requests_get: get failed. status_code: {}{}{}'.format(
            response.status_code, os.linesep, response.text))
    return response.status_code, json.loads(response.text)


def remove_words(text, words, sep_list):
    '''textをsepで区切り、wordsを含む要素を削除する'''

    import re
    text_sep = re.split(sep_list, text)
    text_part_list = []
    for text_part in text_sep:
        if text_part == '':
            continue
        is_included = False
        for word in words:
            if word in text_part:
                is_included = True
                break
        if is_included == False:
            text_part_list.append(text_part)
    return sep_list[0].join(text_part_list)


def get_target_bangumi_name(title, target_bangumi_dict):
    '''取得対象の番組か判定し、対象の場合は番組名を返す'''

    for target_bangumi in target_bangumi_dict.keys():
        if target_bangumi in title:
            return target_bangumi
    return None


