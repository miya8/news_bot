# ログレベル
LOG_LEVEL = 'DEBUG'
# logger名
LOGGER_NAME = 'news_bot'

# テレビ局のスクレ―ピング結果の保存場所とファイル名フォーマット
TARGET_DIR = 'news'
TARGET_FILE_BASE_NAME = '{}_news_{}.csv'

# 何日分のニュースファイルを対象とするか
TARGET_DAYS = 0

# テレビ局毎の話題区切り文字
KYOKU_SEP_DICT = {
    'tbs': '▽|▼',
    'nhk': '▽|▼|　【',
    'ntv': '▽|▼|※',
    'fuji': '▽|▼',
    'asahi': r'▽|▼|」1|　\d+'
}

# 抽出する品詞
KEEP_FILTER = ['名詞', '動詞', '形容詞']
STOP_FILTER = ['名詞,数']
# ストップワード（SlothLibのストップワード以外）
STOP_WORDS_ADDITIONAL = ['する', 'いる', 'ある']

# 品詞細分類1に対する重み（整数。重みw倍して出現数カウントする。重み0→除去）
#WEIGHTS_HINSHI_DICT = {('名詞', '固有名詞'): 2}
WEIGHTS_HINSHI_DICT = {}

# 最頻出の話題の重要単語の取得数
COMMON_TOPIC_WORDS_NUM = 3

# ニュースサイトから取得する記事数
SCRAPE_NEWS_NUM = 1
