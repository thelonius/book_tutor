"""
Book Tutor — чтение и разбор книг из PDF.

Каркас взят из mlops_tutor (Flask, SSE-стриминг, цепочка моделей с fallback),
но подача содержания устроена наоборот. Там модель рассказывала из своей
головы, а 11 тысяч строк curriculum.py задавали ей рамку. Здесь содержание
приходит из книги: глава целиком уходит в промпт, а вопросы поперёк книг
обслуживает гибридный поиск.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import OrderedDict
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import images
import llm
import narrate
import prompts
import retrieval
import ru_stem
import store

load_dotenv()
llm.init()

DB_PATH = os.getenv("LIBRARY_DB_PATH", "data/library.db")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", "data/images"))
STATIC_DIR = Path(__file__).parent / "static" / "dist"

# Vite собирается с base='/static/dist/', и ассеты запрашиваются именно по
# этому пути. Отдаём их штатной статикой Flask: иначе catch-all ниже ловит
# /static/dist/assets/index.js и возвращает на него index.html, а браузер
# отказывается исполнять модуль с типом text/html.
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static/dist")
# Соединение берётся по вызову get_db() — своё на каждый поток веб-сервера.
get_db = store.Pool(DB_PATH)
get_db()                       # создаём схему до первого запроса
index = retrieval.VectorIndex(get_db)

# Глава уходит в промпт целиком. Самая длинная из двух книг — 10 200 символов,
# около 4600 токенов; вместе с ответом это спокойно влезает в контекст любой
# модели цепочки. Обрезка нужна только на случай книги с главой в авторский лист.
MAX_CHAPTER_CHARS = 40_000


# ------------------------------------------------------------------ статика

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    target = STATIC_DIR / path
    if path and target.is_file():
        return send_from_directory(STATIC_DIR, path)
    if (STATIC_DIR / "index.html").is_file():
        return send_from_directory(STATIC_DIR, "index.html")
    return jsonify({
        "service": "book-tutor",
        "hint": "фронтенд не собран: cd frontend && npm install && npm run build",
        "api": ["/api/library", "/api/chapter/<id>", "/api/chat",
                "/api/search", "/api/tts", "/health"],
    })


@app.route("/health")
def health():
    books = store.books(get_db())
    return jsonify({
        "ok": True,
        "books": len(books),
        "paragraphs": sum(b["n_paragraphs"] or 0 for b in books),
        "vectors": int(index.mat.shape[0]),
        "models": llm.available(),
    })


# ---------------------------------------------------------------- библиотека

@app.route("/api/library")
def library():
    out = []
    for book in store.books(get_db()):
        book["chapters"] = store.chapters_of(get_db(), book["id"])
        out.append(book)
    return jsonify({"books": out, "modes": prompts.MODES,
                    "mode_order": list(prompts.MODE_ORDER)})


@app.route("/api/chapter/<int:chapter_id>")
def get_chapter(chapter_id):
    ch = store.chapter(get_db(), chapter_id)
    if not ch:
        return jsonify({"error": "нет такой главы"}), 404
    ch["notes"] = store.notes_of(get_db(), ch["book_id"], chapter_id)
    ch["images"] = store.images_of_chapter(get_db(), chapter_id)
    return jsonify(ch)


@app.route("/api/image/<int:image_id>")
def get_image(image_id):
    """
    Иллюстрация. По умолчанию уменьшённая копия, с ?full=1 — оригинал.

    Оригиналы бывают 2467 пикселей по длинной стороне и весят по 600 КБ;
    для чтения с экрана это впустую, а для разглядывания подписи писаря
    в купчей — наоборот, единственное, что нужно. Копия делается при
    первом обращении и остаётся на диске рядом с оригиналом.
    """
    raw = store.image_path(get_db(), image_id)
    if not raw or not Path(raw).is_file():
        return jsonify({"error": "нет такой иллюстрации"}), 404
    path = Path(raw)
    if not request.args.get("full"):
        try:
            path = images.make_web_copy(path)
        except Exception:                               # noqa: BLE001
            # Битый или экзотический растр — отдаём оригинал, это лучше,
            # чем дырка на месте документа.
            path = Path(raw)
    return send_from_directory(path.parent, path.name,
                               max_age=60 * 60 * 24 * 30)


@app.route("/api/notes", methods=["POST"])
def create_note():
    data = request.json or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "пустая заметка"}), 400
    chapter_id = data.get("chapter_id")
    book_id = data.get("book_id")
    if chapter_id and not book_id:
        ch = store.chapter(get_db(), chapter_id)
        if not ch:
            return jsonify({"error": "нет такой главы"}), 404
        book_id = ch["book_id"]
    if not book_id:
        return jsonify({"error": "нужен book_id или chapter_id"}), 400
    nid = store.add_note(get_db(), book_id, chapter_id, text)
    return jsonify({"id": nid})


# -------------------------------------------------------------------- поиск

@app.route("/api/search", methods=["POST"])
def search():
    data = request.json or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "пустой запрос"}), 400
    hits = retrieval.search(get_db(), index, query,
                            book_id=data.get("book_id"),
                            limit=int(data.get("limit", 8)),
                            captions=bool(data.get("captions", True)))
    return jsonify({"query": query, "hits": [h.as_dict() for h in hits]})


# --------------------------------------------------------------------- чат

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    messages = data.get("messages") or []
    mode = data.get("mode", "discuss")
    if not messages:
        return jsonify({"error": "нет сообщений"}), 400
    if mode not in prompts.MODES:
        return jsonify({"error": f"неизвестный режим: {mode!r}"}), 400

    hits: list = []
    if mode == "search":
        # Ищем по последней реплике пользователя: она и есть вопрос.
        query = next((m["content"] for m in reversed(messages)
                      if m.get("role") == "user"), "")
        hits = retrieval.search(get_db(), index, query,
                                book_id=data.get("book_id"), limit=8)
        if not hits:
            return jsonify({"error": "поиск ничего не нашёл"}), 404
        system = prompts.search_prompt(retrieval.format_context(hits))
    else:
        chapter_id = data.get("chapter_id")
        ch = store.chapter(get_db(), chapter_id) if chapter_id else None
        if not ch:
            return jsonify({"error": "нужен chapter_id"}), 400
        text = store.chapter_text(get_db(), chapter_id,
                                  captions=bool(data.get("captions", True)))
        notes = "\n".join(f"— {n['text']}" for n in
                          store.notes_of(get_db(), ch["book_id"], chapter_id))
        system = prompts.chapter_prompt(
            mode, ch["book_title"], ch, text[:MAX_CHAPTER_CHARS], notes)

    history = [{"role": "user" if m.get("role") == "user" else "assistant",
                "content": m.get("content", "")} for m in messages]
    payload = [{"role": "system", "content": system}] + history
    preferred = data.get("model")

    def generate():
        # Источники уходят первым событием, чтобы интерфейс показал их
        # рядом с ответом, пока тот ещё печатается.
        if hits:
            yield ("data: " + json.dumps(
                {"sources": [h.as_dict() for h in hits]},
                ensure_ascii=False) + "\n\n")
        yield from llm.stream(payload, preferred=preferred)

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ глоссарий

_glossary_cache: "OrderedDict[int, list]" = OrderedDict()


@app.route("/api/glossary/<int:chapter_id>")
def glossary(chapter_id):
    """Устаревшие слова главы с пояснениями — для тултипов в тексте."""
    if chapter_id in _glossary_cache:
        _glossary_cache.move_to_end(chapter_id)
        return jsonify({"terms": _glossary_cache[chapter_id], "cached": True})

    text = store.chapter_text(get_db(), chapter_id, captions=True)
    if not text:
        return jsonify({"error": "нет такой главы"}), 404

    raw = llm.complete([{"role": "user",
                         "content": prompts.GLOSSARY.replace("{text}", text[:8000])}],
                       max_tokens=1200)
    terms = _parse_terms(raw)

    # Модель отвечает именительным падежом, в тексте стоят косвенные.
    # Подбираем реальные написания здесь: стеммер на стороне Python, и
    # тянуть русскую морфологию в браузер ради подсветки незачем.
    for t in terms:
        t["forms"] = ru_stem.find_forms(text, t["term"]) or [t["term"]]
    terms = [t for t in terms if t["forms"]]
    _glossary_cache[chapter_id] = terms
    if len(_glossary_cache) > 64:
        _glossary_cache.popitem(last=False)
    return jsonify({"terms": terms, "cached": False})


def _parse_terms(raw: str) -> list:
    """JSON из ответа модели. Модель охотно оборачивает его в ```json."""
    if not raw:
        return []
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [t for t in data
            if isinstance(t, dict) and t.get("term") and t.get("gloss")]


# --------------------------------------------------------------------- tts

TTS_CACHE_MAX = 32
_tts_cache: "OrderedDict[str, bytes]" = OrderedDict()


@app.route("/api/tts", methods=["POST"])
def tts():
    data = request.json or {}
    chapter_id = data.get("chapter_id")
    text = (data.get("text") or "").strip()
    voice = narrate.VOICES.get(data.get("voice", "male"),
                               data.get("voice") or narrate.DEFAULT_VOICE)
    rate = data.get("rate", narrate.DEFAULT_RATE)

    if chapter_id and not text:
        ch = store.chapter(get_db(), chapter_id)
        if not ch:
            return jsonify({"error": "нет такой главы"}), 404
        text = f"{ch['title']}. " + store.chapter_text(
            get_db(), chapter_id, captions=bool(data.get("captions", False)))
    if not text:
        return jsonify({"error": "нечего озвучивать"}), 400

    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()
    cached = _tts_cache.get(key)
    if cached is not None:
        _tts_cache.move_to_end(key)
        return Response(cached, mimetype="audio/mpeg")

    audio = narrate.synth(text, voice, rate)
    _tts_cache[key] = audio
    if len(_tts_cache) > TTS_CACHE_MAX:
        _tts_cache.popitem(last=False)
    return Response(audio, mimetype="audio/mpeg")


# ------------------------------------------------------------------ загрузка

@app.route("/api/books", methods=["POST"])
def upload_book():
    """Приём нового PDF: разбор, индексация, эмбеддинги."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "нужен файл в поле file"}), 400
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "поддерживается только PDF с текстовым слоем"}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", Path(file.filename).name)
    dest = UPLOAD_DIR / safe
    file.save(dest)

    import ingest
    try:
        book, chapters = ingest.parse(dest, request.form.get("title"))
    except SystemExit as e:
        return jsonify({"error": str(e)}), 400

    book["id"] = (request.form.get("id")
                  or re.sub(r"\W+", "_", dest.stem.lower()).strip("_"))
    body_chars = sum(len(p["text"]) for c in chapters for p in c["paragraphs"]
                     if p["kind"] == "body")
    if body_chars < 500:
        # Сканы без распознанного слоя дают пустой или почти пустой текст.
        dest.unlink(missing_ok=True)
        return jsonify({"error": "в PDF нет текстового слоя — нужен OCR"}), 400

    store.add_book(get_db(), book, chapters)

    # Иллюстрации: без них книга документов наполовину пропадает, а подписи
    # вроде «слева портрет, справа письмо» повисают в воздухе.
    n_images = 0
    try:
        items = images.link(dest, IMAGES_DIR / book["id"])
        n_images = store.add_images(get_db(), book["id"], items)
    except Exception as e:                              # noqa: BLE001
        # Книга без картинок полезнее, чем отказ на загрузке целиком.
        app.logger.warning("иллюстрации не вынулись: %s", e)

    import embeddings
    n = store.index_vectors(get_db(), embeddings.embed, book_id=book["id"])
    index.reload()

    return jsonify({"id": book["id"], "title": book["title"],
                    "chapters": len(chapters), "chars": body_chars,
                    "images": n_images, "vectors": n})


@app.route("/api/books/<book_id>", methods=["DELETE"])
def delete_book(book_id):
    if not any(b["id"] == book_id for b in store.books(get_db())):
        return jsonify({"error": "нет такой книги"}), 404
    store.delete_book(get_db(), book_id)
    index.reload()
    return jsonify({"deleted": book_id})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5003)), debug=True)
