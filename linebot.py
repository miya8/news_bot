import json
import os
import sys
from logging import StreamHandler, getLogger

from common.util import requests_get, requests_post
from settings_line import *

logger = getLogger(LOGGER_NAME)
handler = StreamHandler()
logger.setLevel(LOG_LEVEL)
logger.addHandler(handler)


def check_accs_token_valid(accs_token):
    '''アクセストークンが有効かチェックする'''

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    body = {'access_token': accs_token}
    status, _ = requests_post(LINE_URL_VERIFY_ACCS_TOKEN,
                              headers,
                              body,
                              logger,
                              encode=True,
                              safe='=')
    logger.debug('check_accs_token_valid status_code: {}'.format(status))
    # 期限切れの場合、ステータスコード400(Bad Request)が返る
    if status == 400:
        return False
    elif status == 200:
        return True
    else:
        return None


def issue_accs_token():
    '''アクセストークンを取得する'''

    line_env_dict = json.loads(os.environ[LINE_ENV_NAME])
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    body = {
        'grant_type': 'client_credentials',
        'client_id': line_env_dict[LINE_ENV_KEY_CLIENT_ID],
        'client_secret': line_env_dict[LINE_ENV_KEY_CLIENT_SECRET]
    }
    status, contens_dict = requests_post(LINE_URL_ISSUE_ACCS_TOKEN,
                                         headers,
                                         body,
                                         logger,
                                         encode=True)
    if status == 200:
        return contens_dict['access_token']
    else:
        logger.error('issue_accs_token failed.')
        return None


def send_broadcast_msg(accs_token, contens_list):
    '''Lineにブロードキャストメッセージを送信する'''

    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + accs_token
    }
    body = {
        "messages": [{'type': 'text',
                      'text': title + '\n' + url,
                      'wrap': True} for (title, url) in contens_list]
    }
    status, _ = requests_post(LINE_URL_BOT, headers, body, logger)
    if status != 200:
        logger.error('send_broadcast_msg failed.')
    return status


def bot_to_line(title_url_list):
    '''Lineへbotする'''

    # アクセストークンを取得
    accs_token = issue_accs_token()
    if accs_token is None:
        return -1

    # ブロードキャストメッセージを送信
    status = send_broadcast_msg(accs_token, title_url_list)
    if status == 200:
        return 0
    else:
        logger.error('bot_to_line failed.')
        return -1

# test
#print(bot_to_line([('aiu', 'https://.....url string'), ('xyz', 'https://.....url string2')]))
