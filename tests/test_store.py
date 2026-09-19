import store
from conftest import BOOK, CHAPTERS


def test_book_counters_ignore_captions_and_do_not_multiply(db):
    """Счётчики считаются подзапросами: два LEFT JOIN давали 208×20 абзацев."""
    (book,) = store.books(db)
    assert book['n_chapters'] == 2
    assert book['n_paragraphs'] == 3          # четвёртый абзац — подпись
    assert book['n_chars'] == sum(
        len(p['text']) for c in CHAPTERS for p in c['paragraphs']
        if p['kind'] == 'body')


def test_chapters_carry_pages(db):
    chapters = store.chapters_of(db, 'test')
    assert [c['idx'] for c in chapters] == [1, 2]
    assert (chapters[1]['page_from'], chapters[1]['page_to']) == (2, 3)


def test_chapter_text_can_drop_captions(db):
    cid = store.chapters_of(db, 'test')[0]['id']
    assert 'Ревизская сказка' in store.chapter_text(db, cid, captions=True)
    assert 'Ревизская сказка' not in store.chapter_text(db, cid, captions=False)


def test_chapter_text_marks_captions(db):
    cid = store.chapters_of(db, 'test')[0]['id']
    assert '[подпись или справочная врезка]' in store.chapter_text(db, cid)


def test_reingest_replaces_instead_of_duplicating(db):
    store.add_book(db, BOOK, CHAPTERS)
    assert len(store.books(db)) == 1
    assert store.books(db)[0]['n_paragraphs'] == 3


def test_reingest_leaves_no_orphan_fts_rows(db):
    """FTS5 с внешним содержимым не каскадит: строки индекса чистятся вручную."""
    before = db.execute('SELECT COUNT(*) FROM paragraphs_fts').fetchone()[0]
    store.add_book(db, BOOK, CHAPTERS)
    after = db.execute('SELECT COUNT(*) FROM paragraphs_fts').fetchone()[0]
    assert before == after == 4


def test_delete_book_clears_everything(db, embed):
    store.index_vectors(db, embed)
    store.delete_book(db, 'test')
    assert store.books(db) == []
    for table in ('chapters', 'paragraphs', 'vectors', 'paragraphs_fts'):
        assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_index_vectors_is_idempotent(db, embed):
    assert store.index_vectors(db, embed) == 4
    assert store.index_vectors(db, embed) == 0


def test_load_vectors_matches_paragraph_ids(db, embed):
    store.index_vectors(db, embed)
    mat, ids = store.load_vectors(db)
    assert mat.shape == (4, embed.dim)
    assert ids == sorted(ids)


def test_notes_roundtrip(db):
    cid = store.chapters_of(db, 'test')[0]['id']
    store.add_note(db, 'test', cid, 'проверить по метрической книге')
    assert len(store.notes_of(db, 'test', cid)) == 1
    assert len(store.notes_of(db, 'test')) == 1
    assert store.notes_of(db, 'test', 999) == []
