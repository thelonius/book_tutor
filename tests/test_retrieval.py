import numpy as np

import retrieval
import store


class StubIndex:
    """Векторная половина с заранее заданным порядком — чтобы проверять
    слияние рангов, а не качество эмбеддингов."""

    def __init__(self, order):
        self.order = order
        self.mat = np.zeros((len(order), 1), dtype=np.float32)

    def search(self, query, book_id=None, limit=None):
        return self.order


def test_lexical_finds_by_stem(db):
    """«лишению» в тексте, «лишили» в запросе — без стеммера не находится."""
    hits = retrieval.lexical(db, 'кого лишили прав')
    texts = [store.paragraphs_by_id(db, [h])[h]['text'] for h in hits]
    assert any('лишению' in t for t in texts)


def test_lexical_empty_query_returns_nothing(db):
    assert retrieval.lexical(db, 'и в на') == []


def test_lexical_survives_operator_words(db):
    """Слово из запроса не должно ломать синтаксис MATCH пятисоткой."""
    assert isinstance(retrieval.lexical(db, 'NEAR OR AND дом'), list)


def test_lexical_respects_book_filter(db):
    assert retrieval.lexical(db, 'дом', book_id='другая') == []


def test_rrf_prefers_decent_in_both_over_first_in_one():
    """
    Ради чего слияние и нужно: абзац на пятом месте у лексики и третьем
    у векторов обходит того, кто первый в лексике, но двенадцатый в
    векторах. Так «Хозяйку звали Сося Борухова» вышла на первое место,
    не возглавляя ни один из списков.
    """
    lex = [101, 102, 103, 104, 100] + list(range(200, 235))
    vec = [105, 106, 100] + list(range(300, 308)) + [101]
    scores, lrank, vrank = retrieval.fuse(lex, vec)

    assert (lrank[100], vrank[100]) == (5, 3)
    assert (lrank[101], vrank[101]) == (1, 12)
    assert max(scores, key=scores.get) == 100


def test_rrf_is_nearly_flat_on_adjacent_ranks():
    """Обратная сторона: на соседних позициях слияние почти ничего не
    решает, и (2,2) с (1,3) различаются в четвёртом знаке. Поэтому
    полагаться на него как на тайбрейк нельзя."""
    scores, _, _ = retrieval.fuse([2, 1, 3], [3, 1, 2])
    a, c = scores[1], scores[2]
    assert abs(a - c) < 1e-4


def test_fuse_marks_where_each_hit_came_from():
    scores, lrank, vrank = retrieval.fuse([10, 20], [20, 30])
    assert lrank == {10: 1, 20: 2}
    assert vrank == {20: 1, 30: 2}
    assert scores[20] > scores[10] and scores[20] > scores[30]


def test_search_without_index_falls_back_to_lexical(db):
    hits = retrieval.search(db, None, 'избирательных прав', limit=5)
    assert hits and all(h.vector_rank is None for h in hits)


def test_search_can_drop_captions(db):
    hits = retrieval.search(db, None, 'ревизская сказка', captions=False)
    assert all(h.kind == 'body' for h in hits)


def test_hit_citation_names_book_chapter_page(db):
    hits = retrieval.search(db, None, 'избирательных прав', limit=1)
    assert 'Тестовая книга' in hits[0].citation
    assert 'гл. 2' in hits[0].citation
    assert 'с. 2' in hits[0].citation


def test_format_context_numbers_hits(db):
    hits = retrieval.search(db, None, 'избирательных прав', limit=2)
    ctx = retrieval.format_context(hits)
    assert ctx.startswith('[1] ')
    assert '[2] ' in ctx


def test_vector_index_reload_picks_up_new_vectors(db, embed):
    index = retrieval.VectorIndex(db)
    assert index.mat.shape[0] == 0
    store.index_vectors(db, embed)
    index.reload()
    assert index.mat.shape[0] == 4


def test_vector_half_degrades_to_lexical_on_dim_change(db, embed, monkeypatch):
    """Смена EMBEDDING_MODEL после индексации не должна ронять поиск:
    старые векторы несравнимы с новым запросом, и половина просто молчит."""
    store.index_vectors(db, embed)
    index = retrieval.VectorIndex(db)

    import embeddings
    monkeypatch.setattr(embeddings, 'embed_one',
                        lambda t: np.zeros(embed.dim + 1, dtype=np.float32))

    assert index.search('избирательных прав') == []
    assert index.dim_mismatch == (embed.dim, embed.dim + 1)
    hits = retrieval.search(db, index, 'избирательных прав')
    assert hits and all(h.vector_rank is None for h in hits)


def test_vector_floor_cuts_off_topic_queries(db, embed, monkeypatch):
    """Плотный поиск всегда отдаёт топ-K, поэтому посторонний вопрос
    отсекается порогом косинуса, а не отсутствием результатов."""
    store.index_vectors(db, embed)
    index = retrieval.VectorIndex(db)
    import embeddings

    far = np.zeros(embed.dim, dtype=np.float32)
    far[0] = 1.0
    monkeypatch.setattr(embeddings, 'embed_one', lambda t: far)
    monkeypatch.setattr(retrieval, 'VEC_FLOOR', 0.99)
    assert index.search('посторонний вопрос') == []

    monkeypatch.setattr(retrieval, 'VEC_FLOOR', -1.0)
    assert index.search('посторонний вопрос') != []


def test_vector_index_accepts_a_connection_factory(tmp_path, embed):
    """Под веб-сервером у каждого потока своё соединение, поэтому индекс
    берёт его вызовом. Проверка заодно ловит ловушку: у sqlite3.Connection
    есть свой __call__, и наивный callable() принял бы его за фабрику."""
    conn = store.connect(tmp_path / 'lib.db')
    from conftest import BOOK, CHAPTERS
    store.add_book(conn, BOOK, CHAPTERS)
    store.index_vectors(conn, embed)

    calls = []

    def factory():
        calls.append(1)
        return conn

    index = retrieval.VectorIndex(factory)
    assert index.mat.shape[0] == 4
    assert calls, 'фабрика не была вызвана'
    assert retrieval.VectorIndex(conn).mat.shape[0] == 4
