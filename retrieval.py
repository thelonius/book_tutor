"""
Гибридный поиск по библиотеке: FTS5 плюс косинус по эмбеддингам.

Оба способа нужны, и это видно на замерах по этим самым книгам. Лексический
поиск выигрывает там, где в вопросе стоит само слово из текста — год, имя,
термин: «что случилось в 1919 году» он отрабатывает точно, а векторный
расползается по соседним годам. Векторный выигрывает, когда вопрос пересказан
своими словами: на «как звали женщину, владевшую домом с аптекой» FTS5 не
находит ничего, а косинус достаёт «Хозяйку звали Сося Борухова», где слова
«владелица» нет вовсе.

Списки сливаются обратным ранговым слиянием (RRF): вес позиции, а не балла.
Нормировать bm25 и косинус к одной шкале пришлось бы подбором коэффициентов
под каждый корпус, а ранги сравнимы всегда.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

import ru_stem
import store

RRF_K = 60          # сглаживание из статьи Cormack et al., работает без подбора
POOL = 40           # сколько берём из каждого списка до слияния

# Косинусный пол для векторной половины.
#
# Плотный поиск всегда возвращает топ-K, каким бы посторонним ни был вопрос,
# и без отсечки на «python asyncio event loop» модель получала бы восемь
# абзацев про минских мещан и должна была бы сама догадаться их не трогать.
#
# Замер на этом корпусе (paraphrase-multilingual-MiniLM-L12-v2): у осмысленных
# вопросов максимум косинуса 0,49–0,68, у посторонних 0,16–0,40. Порог 0,45
# пропускает все осмысленные и режет посторонние — кроме «рецепта борща»,
# который дотягивает до 0,55, зацепившись за домашний обиход. Полной защиты
# порог не даёт, поэтому в промпте отдельным правилом стоит «не тяни ответ
# за уши, если нужного нет».
VEC_FLOOR = float(os.getenv('VECTOR_FLOOR', '0.45'))


@dataclass
class Hit:
    paragraph_id: int
    text: str
    kind: str
    page: Optional[int]
    book_id: str
    book_title: str
    chapter_id: int
    chapter_idx: int
    chapter_title: str
    score: float
    lexical_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    # Иллюстрации, к которым этот абзац служит подписью.
    image_ids: tuple[int, ...] = ()

    @property
    def citation(self) -> str:
        return f'{self.book_title}, гл. {self.chapter_idx} «{self.chapter_title}», с. {self.page}'

    def as_dict(self) -> dict:
        return {
            'paragraph_id': self.paragraph_id,
            'text': self.text,
            'kind': self.kind,
            'page': self.page,
            'book_id': self.book_id,
            'book_title': self.book_title,
            'chapter_id': self.chapter_id,
            'chapter_idx': self.chapter_idx,
            'chapter_title': self.chapter_title,
            'score': round(self.score, 5),
            'lexical_rank': self.lexical_rank,
            'vector_rank': self.vector_rank,
            'image_ids': list(self.image_ids),
            'citation': self.citation,
        }


def lexical(db: sqlite3.Connection, query: str, book_id: Optional[str] = None,
            limit: int = POOL) -> list[int]:
    match = ru_stem.fts_match(query)
    if not match:
        return []
    sql = """
        SELECT f.rowid FROM paragraphs_fts f
        JOIN paragraphs p ON p.id = f.rowid
        WHERE paragraphs_fts MATCH ?
    """
    args: list = [match]
    if book_id:
        sql += " AND p.book_id = ?"
        args.append(book_id)
    sql += " ORDER BY bm25(paragraphs_fts, 1.0, 0.6) LIMIT ?"
    args.append(limit)
    try:
        return [r[0] for r in db.execute(sql, args)]
    except sqlite3.OperationalError:
        # Экзотический запрос всё-таки развалил синтаксис MATCH — поиск
        # должен деградировать до векторного, а не падать пятисоткой.
        return []


class VectorIndex:
    """
    Матрица эмбеддингов в памяти.

    Шестьсот абзацев по 384 float32 — 0,9 МБ. Грузится один раз при старте,
    перечитывается после добавления книги (reload).

    Соединение берётся вызовом, а не хранится: под веб-сервером у каждого
    потока своё (см. store.Pool), и держать чужое здесь нельзя.
    """

    def __init__(self, db: sqlite3.Connection | Callable[[], sqlite3.Connection]):
        # Проверять через callable() нельзя: у sqlite3.Connection есть
        # легаси-метод __call__, и готовое соединение ушло бы в ветку
        # фабрики, а потом вызвалось бы как функция.
        self._db = (lambda: db) if isinstance(db, sqlite3.Connection) else db
        self.mat = np.zeros((0, 0), dtype=np.float32)
        self.ids: list[int] = []
        # Заполняется, если размерность запроса разошлась с базой; health
        # показывает это, чтобы молчаливая деградация до лексики была видна.
        self.dim_mismatch: Optional[tuple[int, int]] = None
        self.reload()

    @property
    def db(self) -> sqlite3.Connection:
        return self._db()

    def reload(self) -> None:
        self.mat, self.ids = store.load_vectors(self.db)

    def search(self, query: str, book_id: Optional[str] = None,
               limit: int = POOL) -> list[int]:
        if not len(self.ids):
            return []
        import embeddings
        qv = embeddings.embed_one(query)
        if qv.shape[0] != self.mat.shape[1]:
            # EMBEDDING_MODEL сменили после индексации. Векторы в базе
            # посчитаны прежней моделью и с новым запросом несравнимы.
            # Поиск обязан продолжить работать на одной лексике, а не
            # ронять каждый запрос ошибкой из numpy.
            self.dim_mismatch = (self.mat.shape[1], qv.shape[0])
            return []
        sims = self.mat @ qv

        if book_id:
            allowed = {r[0] for r in self.db.execute(
                "SELECT id FROM paragraphs WHERE book_id = ?", (book_id,))}
            mask = np.array([i in allowed for i in self.ids])
            sims = np.where(mask, sims, -np.inf)

        top = np.argpartition(-sims, min(limit, len(sims) - 1))[:limit]
        top = top[np.argsort(-sims[top])]
        return [self.ids[i] for i in top
                if np.isfinite(sims[i]) and sims[i] >= VEC_FLOOR]


def fuse(lex: list[int], vec: list[int]) -> tuple[dict[int, float],
                                                  dict[int, int], dict[int, int]]:
    """
    Обратное ранговое слияние двух списков.

    Каждое попадание добавляет 1/(K+позиция), дальше складываем. Смысл
    не в том, что «середина в обоих» всегда обгоняет «первое место в
    одном» — при близких позициях выражение почти линейно, и (2,2) с
    (1,3) дают практически одно и то же. Выигрыш появляется на разрыве:
    абзац на позициях 5 и 3 обходит того, кто первый в лексике и
    двенадцатый в векторах. Ровно так «Хозяйку звали Сося Борухова»
    вышла на первое место, не будучи первой ни в одном из списков.
    """
    scores: dict[int, float] = {}
    lrank: dict[int, int] = {}
    vrank: dict[int, int] = {}
    for rank, pid in enumerate(lex, 1):
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank)
        lrank[pid] = rank
    for rank, pid in enumerate(vec, 1):
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank)
        vrank[pid] = rank
    return scores, lrank, vrank


def search(db: sqlite3.Connection, index: Optional[VectorIndex], query: str,
           book_id: Optional[str] = None, limit: int = 8,
           captions: bool = True) -> list[Hit]:
    lex = lexical(db, query, book_id)
    vec = index.search(query, book_id) if index else []
    scores, lrank, vrank = fuse(lex, vec)

    if not scores:
        return []
    order = sorted(scores, key=lambda p: -scores[p])
    meta = store.paragraphs_by_id(db, order)

    hits: list[Hit] = []
    for pid in order:
        m = meta.get(pid)
        if not m or (not captions and m['kind'] == 'caption'):
            continue
        hits.append(Hit(
            paragraph_id=pid, text=m['text'], kind=m['kind'], page=m['page'],
            book_id=m['book_id'], book_title=m['book_title'],
            chapter_id=m['chapter_id'], chapter_idx=m['chapter_idx'],
            chapter_title=m['chapter_title'],
            score=scores[pid], lexical_rank=lrank.get(pid),
            vector_rank=vrank.get(pid),
            image_ids=tuple(m.get('image_ids') or ())))
        if len(hits) >= limit:
            break
    return hits


def format_context(hits: list[Hit]) -> str:
    """Найденное в виде, пригодном для промпта: с номерами для ссылок."""
    return '\n\n'.join(
        f'[{i}] {h.citation}\n{h.text}' for i, h in enumerate(hits, 1))
