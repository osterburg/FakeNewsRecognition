import os
import multiprocessing

import ujson
import subprocess

import numpy as np
import pandas as pd
from gensim.parsing import preprocess_string
from tqdm import tqdm

path_data = os.environ['FNR_PATH_DATA'] if 'FNR_PATH_DATA' in os.environ else 'data/fake_news_corpus/'
path_news_csv = path_data + 'news_cleaned_2018_02_13.csv'
path_fasttext = path_data + 'news_cleaned_2018_02_13.fasttext.bin'
path_news_preprocessed = path_data + 'news_cleaned_2018_02_13.preprocessed.jsonl'
path_news_shuffled = path_data + 'news_cleaned_2018_02_13.preprocessed.shuffled.jsonl'
path_news_train = path_data + 'news_cleaned_2018_02_13.preprocessed.shuffled.train.jsonl'
path_news_test = path_data + 'news_cleaned_2018_02_13.preprocessed.shuffled.test.jsonl'
path_news_val = path_data + 'news_cleaned_2018_02_13.preprocessed.shuffled.val.jsonl'


def _news_generator_process_line(line, fasttext, max_words):
    article = ujson.loads(line)

    embedding = np.zeros((max_words, 100))
    for i, word in enumerate(article['content'][:max_words]):
        if word in fasttext:
            embedding[i] = fasttext[word]

    return embedding, article['label']


def embedded_news_generator(path, batch, fasttext, max_words):
    while True:
        with open(path, 'r') as in_news:
            batch_i = 0
            batch_embedding = np.zeros((batch, max_words, 100))
            batch_label = np.zeros((batch, 1))
            for line in in_news:
                embedding, label = _news_generator_process_line(line, fasttext, max_words)

                if (batch_i + 1) == batch:
                    yield batch_embedding, batch_label
                    batch_embedding = np.zeros((batch, max_words, 100))
                    batch_label = np.zeros((batch, 1))
                    batch_i = 0
                else:
                    batch_embedding[batch_i] = embedding
                    batch_label[batch_i, 0] = label
                    batch_i += 1


def news_generator():
    with tqdm() as progress:
        for df_news_chunk in pd.read_csv(path_news_csv, encoding='utf-8', engine='python', chunksize=10 * 1000):
            news_filter = df_news_chunk.type.isin({'fake', 'conspiracy', 'unreliable', 'reliable'})
            df_news_chunk_filtered = df_news_chunk[news_filter]
            for row in df_news_chunk_filtered.itertuples():
                label = 1 if row.type == 'reliable' else 0

                progress.update()
                yield int(row.id), '%s %s' % (row.title, row.content), label


def _preprocess_string(news):
    _id, con, label = news
    return _id, preprocess_string(con), label


def news_preprocessed_generator():
    missing_words = {}

    with multiprocessing.Pool(multiprocessing.cpu_count(), maxtasksperchild=1) as pool:
        for _id, con, label in pool.imap(_preprocess_string, news_generator(), chunksize=1000):
            yield _id, con, label, missing_words


def train_test_val_count():
    count_lines = 0
    with open(path_news_shuffled, 'r') as in_news:
        for _ in tqdm(in_news):
            count_lines += 1

    train_size = int(count_lines * .8)
    test_size = int(count_lines * .1)
    val_size = count_lines - (train_size + test_size)

    return train_size, test_size, val_size, count_lines


def prepare_data():
    print('Preprocessing...')
    with open(path_news_preprocessed, 'w') as out_news_preprocessed:
        for _id, con, label, missing_words in news_preprocessed_generator():
            out_news_preprocessed.write(ujson.dumps({
                'id': _id, 'content': con, 'label': int(label)
            }) + '\n')

    print('Shuffling...')
    subprocess.call(['shuf', path_news_preprocessed, '>', path_news_shuffled])

    print('Counting...')
    train_size, test_size, val_size, count_lines = train_test_val_count()

    print('Splitting into train, test, and val...')
    with open(path_news_shuffled, 'r') as in_news:
        with open(path_news_train, 'w') as out_train:
            with open(path_news_test, 'w') as out_test:
                with open(path_news_val, 'w') as out_val:
                    for i, line in tqdm(enumerate(in_news)):
                        if i < train_size:
                            out_train.write(line)
                        elif i < (train_size + test_size):
                            out_test.write(line)
                        else:
                            out_val.write(line)


if __name__ == '__main__':
    prepare_data()
