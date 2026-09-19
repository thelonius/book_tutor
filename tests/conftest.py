import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402

BOOK = {'id': 'test', 'title': 'Тестовая книга', 'subtitle': 'проверка',
        'source': 'test.pdf', 'n_pages': 3}

CHAPTERS = [
    {'title': 'Дом на углу', 'subtitle': 'Пролог', 'page_from': 1, 'page_to': 1,
     'paragraphs': [
         {'kind': 'body', 'page': 1,
          'text': 'Хозяйку звали Сося Борухова. Дом достался ей от отца по завещанию.'},
         {'kind': 'caption', 'page': 1,
          'text': 'Ревизская сказка минских мещан, НИАБ, ф. 333, оп. 9.'},
     ]},
    {'title': 'Лишенец', 'subtitle': 'Глава вторая', 'page_from': 2, 'page_to': 3,
     'paragraphs': [
         {'kind': 'body', 'page': 2,
          'text': 'В начале 1929 года его лишили избирательных прав как сына домовладелицы.'},
         {'kind': 'body', 'page': 3,
          'text': 'Комиссия по лишению прав собралась в тот же день и постановила отказать.'},
     ]},
]


class FakeEmbed:
    """Детерминированные векторы без похода в сеть и без выкачивания ONNX.

    Направление задаётся хешем слов, поэтому одинаковые тексты дают
    одинаковые векторы, а разные — почти ортогональные. Этого хватает,
    чтобы проверить слияние рангов, но не качество поиска: качество
    меряется на настоящей модели, а не в юнит-тестах.
    """

    dim = 16

    def __call__(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in t.lower().split():
                out[i, hash(w) % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.clip(norms, 1e-9, None)


@pytest.fixture
def db(tmp_path):
    conn = store.connect(tmp_path / 'library.db')
    store.add_book(conn, BOOK, CHAPTERS)
    yield conn
    conn.close()


@pytest.fixture
def embed():
    return FakeEmbed()
