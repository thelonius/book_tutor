"""
Тесты HTTP-слоя. К моделям не ходим: llm.stream и llm.complete подменяются,
иначе набор зависел бы от чужой квоты и отвечал бы по десять секунд.
"""
import importlib
import json

import pytest

import store
from conftest import BOOK, CHAPTERS, FakeEmbed


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / 'library.db'
    conn = store.connect(db_path)
    store.add_book(conn, BOOK, CHAPTERS)
    store.index_vectors(conn, FakeEmbed())
    conn.close()

    monkeypatch.setenv('LIBRARY_DB_PATH', str(db_path))
    # Запрос должен эмбеддиться той же моделью, что и корпус, иначе поиск
    # честно уходит в лексику и векторная половина тестов ничего не проверит.
    import embeddings
    monkeypatch.setattr(embeddings, 'embed', FakeEmbed())
    monkeypatch.setattr(embeddings, 'embed_one', lambda t: FakeEmbed()([t])[0])
    import app as app_module
    app_module = importlib.reload(app_module)

    monkeypatch.setattr(app_module.llm, 'stream',
                        lambda messages, **kw: iter([
                            'data: ' + json.dumps({'text': 'ответ'}) + '\n\n',
                            'data: ' + json.dumps({'done': True,
                                                   'model': 'stub'}) + '\n\n']))
    monkeypatch.setattr(app_module.llm, 'complete',
                        lambda *a, **kw: '[{"term": "сажень", "gloss": "мера длины"}]')
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        c.module = app_module
        yield c


def sse(response) -> list[dict]:
    out = []
    for line in response.get_data(as_text=True).splitlines():
        if line.startswith('data: '):
            out.append(json.loads(line[6:]))
    return out


def test_health_reports_corpus(client):
    body = client.get('/health').get_json()
    assert body['ok'] and body['books'] == 1
    assert body['paragraphs'] == 3 and body['vectors'] == 4


def test_library_lists_chapters_and_modes(client):
    body = client.get('/api/library').get_json()
    assert [c['title'] for c in body['books'][0]['chapters']] == [
        'Дом на углу', 'Лишенец']
    assert set(body['modes']) == {'discuss', 'quiz', 'context', 'search'}


def test_chapter_returns_paragraphs(client):
    cid = client.get('/api/library').get_json()['books'][0]['chapters'][0]['id']
    ch = client.get(f'/api/chapter/{cid}').get_json()
    assert ch['title'] == 'Дом на углу'
    assert [p['kind'] for p in ch['paragraphs']] == ['body', 'caption']


def test_missing_chapter_is_404(client):
    assert client.get('/api/chapter/9999').status_code == 404


def test_search_returns_citations(client):
    body = client.post('/api/search',
                       json={'query': 'избирательных прав'}).get_json()
    assert body['hits']
    assert 'гл. 2' in body['hits'][0]['citation']


def test_search_rejects_empty_query(client):
    assert client.post('/api/search', json={'query': '  '}).status_code == 400


def test_chat_search_mode_emits_sources_before_text(client):
    r = client.post('/api/chat', json={
        'mode': 'search',
        'messages': [{'role': 'user', 'content': 'кого лишили прав'}]})
    events = sse(r)
    assert 'sources' in events[0]
    assert any(e.get('text') == 'ответ' for e in events)


def test_chat_search_404_when_nothing_found(client, monkeypatch):
    """Порог косинуса поднят до предела: фейковый эмбеддер раскладывает
    слова по хеш-бакетам и даёт ненулевое сходство чему угодно, а проверить
    надо ветку «поиск ничего не нашёл», а не геометрию заглушки."""
    import retrieval
    monkeypatch.setattr(retrieval, 'VEC_FLOOR', 0.99)
    r = client.post('/api/chat', json={
        'mode': 'search',
        'messages': [{'role': 'user', 'content': 'квантовая хромодинамика'}]})
    assert r.status_code == 404


def test_chat_chapter_mode_needs_chapter_id(client):
    r = client.post('/api/chat', json={
        'mode': 'discuss', 'messages': [{'role': 'user', 'content': 'привет'}]})
    assert r.status_code == 400


def test_chat_rejects_unknown_mode(client):
    r = client.post('/api/chat', json={
        'mode': 'mock_interview', 'chapter_id': 1,
        'messages': [{'role': 'user', 'content': 'привет'}]})
    assert r.status_code == 400


def test_chat_puts_chapter_text_into_system_prompt(client, monkeypatch):
    seen = {}

    def capture(messages, **kw):
        seen['system'] = messages[0]['content']
        return iter([])

    monkeypatch.setattr(client.module.llm, 'stream', capture)
    cid = client.get('/api/library').get_json()['books'][0]['chapters'][0]['id']
    client.post('/api/chat', json={'mode': 'discuss', 'chapter_id': cid,
                                   'messages': [{'role': 'user', 'content': 'о чём тут'}]})
    assert 'Сося Борухова' in seen['system']
    assert 'ПРАВИЛО ИСТОЧНИКА' in seen['system']


def test_notes_reach_the_prompt(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(client.module.llm, 'stream',
                        lambda m, **kw: seen.setdefault('system', m[0]['content']) and iter([]) or iter([]))
    cid = client.get('/api/library').get_json()['books'][0]['chapters'][0]['id']
    client.post('/api/notes', json={'chapter_id': cid, 'text': 'сверить с метрической книгой'})
    client.post('/api/chat', json={'mode': 'discuss', 'chapter_id': cid,
                                   'messages': [{'role': 'user', 'content': '?'}]})
    assert 'сверить с метрической книгой' in seen['system']


def test_note_requires_text(client):
    assert client.post('/api/notes', json={'book_id': 'test', 'text': ''}).status_code == 400


def test_glossary_parses_json_and_caches(client):
    first = client.get('/api/glossary/1').get_json()
    assert first['terms'][0]['term'] == 'сажень'
    assert first['cached'] is False
    assert client.get('/api/glossary/1').get_json()['cached'] is True


def test_glossary_survives_model_chatter(client, monkeypatch):
    """Модель охотно оборачивает JSON в ```json и предисловие."""
    monkeypatch.setattr(client.module.llm, 'complete', lambda *a, **kw:
                        'Вот термины:\n```json\n[{"term": "аршин", "gloss": "0,71 м"}]\n```')
    client.module._glossary_cache.clear()
    assert client.get('/api/glossary/1').get_json()['terms'][0]['term'] == 'аршин'


def test_glossary_returns_empty_on_garbage(client, monkeypatch):
    monkeypatch.setattr(client.module.llm, 'complete', lambda *a, **kw: 'не осилил')
    client.module._glossary_cache.clear()
    assert client.get('/api/glossary/1').get_json()['terms'] == []


def test_delete_book_drops_it_from_library(client):
    assert client.delete('/api/books/test').status_code == 200
    assert client.get('/api/library').get_json()['books'] == []
    assert client.delete('/api/books/test').status_code == 404


def test_upload_rejects_non_pdf(client):
    import io
    r = client.post('/api/books', data={
        'file': (io.BytesIO(b'hello'), 'notes.txt')},
        content_type='multipart/form-data')
    assert r.status_code == 400
