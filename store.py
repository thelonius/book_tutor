"""
Хранилище библиотеки: SQLite с полнотекстовым индексом и векторами.

Отдельной векторной базы здесь нет намеренно. Книга даёт порядка трёхсот
абзацев, две книги — шестьсот; матрица эмбеддингов на шестьсот строк по 384
измерения занимает 0,9 МБ и целиком лежит в памяти процесса. Qdrant с его
контейнером и сетевым хопом начал бы окупаться тысячах на ста абзацев.

Векторы хранятся BLOB'ами в той же базе, что и текст, поэтому библиотека —
это один файл, который переносится копированием.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

import ru_stem

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    subtitle    TEXT,
    source      TEXT,
    n_pages     INTEGER,
    added_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id          INTEGER PRIMARY KEY,
    book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    title       TEXT NOT NULL,
    subtitle    TEXT,
    page_from   INTEGER,
    page_to     INTEGER,
    UNIQUE(book_id, idx)
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id          INTEGER PRIMARY KEY,
    book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_id  INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    kind        TEXT NOT NULL,          -- body | caption
    page        INTEGER,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS paragraphs_chapter ON paragraphs(chapter_id, idx);

-- Колонка stem — тот же абзац, прогнанный через стеммер: unicode61 русской
-- морфологии не знает, и без него «дома» не находится по запросу «дом».
--
-- Таблица обычная, не с внешним содержимым. С content='paragraphs' FTS5
-- требует, чтобы в исходной таблице нашлись все проиндексированные колонки,
-- а stem вычисляемый — любой COUNT(*) по индексу падал на «no such column:
-- T.stem». Своя копия текста стоит 150 КБ на книгу и убирает ручную
-- синхронизацию при удалении.
CREATE VIRTUAL TABLE IF NOT EXISTS paragraphs_fts USING fts5(
    text, stem,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS vectors (
    paragraph_id INTEGER PRIMARY KEY REFERENCES paragraphs(id) ON DELETE CASCADE,
    vec          BLOB NOT NULL
);

-- Заметки пользователя живут рядом с текстом и участвуют в поиске наравне
-- с ним: спрашивая «что я думал про Гороховую», человек ждёт и свою выписку.
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Соединение для скриптов и тестов — одно, в одном потоке."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(SCHEMA)
    return db


class Pool:
    """
    Соединение на поток.

    Одно общее соединение с check_same_thread=False выглядит соблазнительно
    и работает ровно до первого параллельного запроса: Flask в дев-режиме и
    gunicorn с потоками обслуживают их одновременно, sqlite3 на это не
    рассчитан, и процесс падает целиком, не отдав даже пятисотку. Ровно так
    браузер получил ERR_EMPTY_RESPONSE на /api/chapter и /api/glossary,
    ушедшие одновременно.

    Соединения дешёвые, база одна и маленькая, WAL разрешает параллельное
    чтение при пишущем — так что просто держим по штуке на поток.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._local = threading.local()

    def __call__(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.path)
            self._local.conn = conn
        return conn


# ------------------------------------------------------------------ запись

def delete_book(db: sqlite3.Connection, book_id: str) -> None:
    """Сносит книгу целиком. Нужен для переиндексации без дублей."""
    ids = [r[0] for r in db.execute(
        "SELECT id FROM paragraphs WHERE book_id = ?", (book_id,))]
    if ids:
        marks = ",".join("?" * len(ids))
        # Каскада у виртуальной таблицы нет, строки индекса сносим сами.
        db.execute(f"DELETE FROM paragraphs_fts WHERE rowid IN ({marks})", ids)
        db.execute(f"DELETE FROM vectors WHERE paragraph_id IN ({marks})", ids)
    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()


def add_book(db: sqlite3.Connection, book: dict, chapters: list[dict]) -> None:
    """
    Кладёт книгу со всеми главами и абзацами. Векторы считаются отдельно
    (index_vectors): разбор PDF идёт за доли секунды, а эмбеддинги — секунды,
    и на импорте пачки книг их удобно считать одним батчем.
    """
    delete_book(db, book["id"])
    db.execute(
        "INSERT INTO books(id, title, subtitle, source, n_pages) VALUES(?,?,?,?,?)",
        (book["id"], book["title"], book.get("subtitle"),
         book.get("source"), book.get("n_pages")))

    for ci, ch in enumerate(chapters, 1):
        cur = db.execute(
            "INSERT INTO chapters(book_id, idx, title, subtitle, page_from, page_to) "
            "VALUES(?,?,?,?,?,?)",
            (book["id"], ci, ch["title"], ch.get("subtitle"),
             ch.get("page_from"), ch.get("page_to")))
        chapter_id = cur.lastrowid
        for pi, para in enumerate(ch["paragraphs"], 1):
            pid = db.execute(
                "INSERT INTO paragraphs(book_id, chapter_id, idx, kind, page, text) "
                "VALUES(?,?,?,?,?,?)",
                (book["id"], chapter_id, pi, para["kind"],
                 para.get("page"), para["text"])).lastrowid
            db.execute(
                "INSERT INTO paragraphs_fts(rowid, text, stem) VALUES(?,?,?)",
                (pid, para["text"], ru_stem.stem_text(para["text"])))
    db.commit()


def index_vectors(db: sqlite3.Connection, embed, book_id: Optional[str] = None,
                  batch: int = 64) -> int:
    """Считает эмбеддинги для абзацев, у которых их ещё нет."""
    sql = ("SELECT p.id, p.text FROM paragraphs p "
           "LEFT JOIN vectors v ON v.paragraph_id = p.id WHERE v.paragraph_id IS NULL")
    args: tuple = ()
    if book_id:
        sql += " AND p.book_id = ?"
        args = (book_id,)
    rows = db.execute(sql, args).fetchall()
    if not rows:
        return 0

    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        vecs = embed([r["text"] for r in chunk])
        db.executemany(
            "INSERT OR REPLACE INTO vectors(paragraph_id, vec) VALUES(?,?)",
            [(r["id"], v.astype(np.float32).tobytes()) for r, v in zip(chunk, vecs)])
        db.commit()
    return len(rows)


# ------------------------------------------------------------------ чтение

def books(db: sqlite3.Connection) -> list[dict]:
    # Счётчики подзапросами, а не двумя LEFT JOIN: join по главам и по
    # абзацам сразу даёт декартово произведение, и 208 абзацев в двадцати
    # главах превращаются в 4160.
    rows = db.execute("""
        SELECT b.*,
          (SELECT COUNT(*) FROM chapters c WHERE c.book_id = b.id) AS n_chapters,
          (SELECT COUNT(*) FROM paragraphs p
             WHERE p.book_id = b.id AND p.kind = 'body') AS n_paragraphs,
          (SELECT COALESCE(SUM(LENGTH(p.text)), 0) FROM paragraphs p
             WHERE p.book_id = b.id AND p.kind = 'body') AS n_chars
        FROM books b ORDER BY b.added_at
    """).fetchall()
    return [dict(r) for r in rows]


def chapters_of(db: sqlite3.Connection, book_id: str) -> list[dict]:
    rows = db.execute("""
        SELECT c.*, COUNT(p.id) FILTER (WHERE p.kind = 'body') AS n_paragraphs,
               SUM(LENGTH(p.text)) FILTER (WHERE p.kind = 'body') AS n_chars
        FROM chapters c LEFT JOIN paragraphs p ON p.chapter_id = c.id
        WHERE c.book_id = ? GROUP BY c.id ORDER BY c.idx
    """, (book_id,)).fetchall()
    return [dict(r) for r in rows]


def chapter(db: sqlite3.Connection, chapter_id: int) -> Optional[dict]:
    row = db.execute("""
        SELECT c.*, b.title AS book_title FROM chapters c
        JOIN books b ON b.id = c.book_id WHERE c.id = ?
    """, (chapter_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["paragraphs"] = [dict(r) for r in db.execute(
        "SELECT id, idx, kind, page, text FROM paragraphs "
        "WHERE chapter_id = ? ORDER BY idx", (chapter_id,))]
    return out


def chapter_text(db: sqlite3.Connection, chapter_id: int,
                 captions: bool = True) -> str:
    """Текст главы одной строкой — то, что уходит в промпт."""
    ch = chapter(db, chapter_id)
    if not ch:
        return ""
    parts = []
    for p in ch["paragraphs"]:
        if p["kind"] == "caption":
            if not captions:
                continue
            parts.append(f"[подпись или справочная врезка] {p['text']}")
        else:
            parts.append(p["text"])
    return "\n\n".join(parts)


def paragraphs_by_id(db: sqlite3.Connection, ids: Iterable[int]) -> dict[int, dict]:
    ids = list(ids)
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = db.execute(f"""
        SELECT p.id, p.text, p.kind, p.page, p.book_id,
               c.id AS chapter_id, c.idx AS chapter_idx, c.title AS chapter_title,
               b.title AS book_title
        FROM paragraphs p
        JOIN chapters c ON c.id = p.chapter_id
        JOIN books b ON b.id = p.book_id
        WHERE p.id IN ({marks})
    """, ids).fetchall()
    return {r["id"]: dict(r) for r in rows}


def load_vectors(db: sqlite3.Connection,
                 book_id: Optional[str] = None) -> tuple[np.ndarray, list[int]]:
    """Матрица эмбеддингов и параллельный список id абзацев."""
    sql = ("SELECT v.paragraph_id, v.vec FROM vectors v "
           "JOIN paragraphs p ON p.id = v.paragraph_id")
    args: tuple = ()
    if book_id:
        sql += " WHERE p.book_id = ?"
        args = (book_id,)
    sql += " ORDER BY v.paragraph_id"
    rows = db.execute(sql, args).fetchall()
    if not rows:
        return np.zeros((0, 0), dtype=np.float32), []
    mat = np.stack([np.frombuffer(r["vec"], dtype=np.float32) for r in rows])
    return mat, [r["paragraph_id"] for r in rows]


# ------------------------------------------------------------------ заметки

def add_note(db: sqlite3.Connection, book_id: str, chapter_id: Optional[int],
             text: str) -> int:
    nid = db.execute(
        "INSERT INTO notes(book_id, chapter_id, text) VALUES(?,?,?)",
        (book_id, chapter_id, text)).lastrowid
    db.commit()
    return nid


def notes_of(db: sqlite3.Connection, book_id: str,
             chapter_id: Optional[int] = None) -> list[dict]:
    if chapter_id is None:
        rows = db.execute(
            "SELECT * FROM notes WHERE book_id = ? ORDER BY created_at",
            (book_id,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM notes WHERE book_id = ? AND chapter_id = ? "
            "ORDER BY created_at", (book_id, chapter_id)).fetchall()
    return [dict(r) for r in rows]
