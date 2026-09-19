"""
Эмбеддинги через fastembed — ONNX-модель локально, без сервера.

Сюда пробовали зайти облаком, но не вышло: у Zhipu на международном
эндпоинте embeddings не отдаются («Unknown Model» на все коды), у OpenRouter
на эндпоинт эмбеддингов нужны купленные кредиты. Ollama с bge-m3 работала бы,
но это отдельный демон и 2 ГБ весов ради шестисот абзацев.

paraphrase-multilingual-MiniLM-L12-v2 — 384 измерения, около 120 МБ в ONNX,
шестьсот абзацев считает за пятнадцать секунд на ноутбуке. На N150 это те же
секунды, потому что модель маленькая, а считается один раз при загрузке книги.

Модель тянется с Hugging Face при первом вызове, поэтому грузим её лениво:
импорт модуля не должен ходить в сеть, иначе тесты и `--help` начинают
зависеть от интернета.
"""
from __future__ import annotations

import functools
import os

import numpy as np

MODEL = os.getenv('EMBEDDING_MODEL',
                  'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
DIM = 384


@functools.lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL)


def embed(texts: list[str]) -> np.ndarray:
    """Нормированные векторы, по строке на текст. Косинус = скалярное произведение."""
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    mat = np.asarray(list(_model().embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / np.clip(norms, 1e-9, None)


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]
