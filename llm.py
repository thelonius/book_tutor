"""
Обращения к моделям: цепочка с fallback и разбор стрима.

Взято из mlops_tutor и почищено по факту проверки 19.09.2026: из семи
моделей прежней цепочки три отвалились. `minimax/minimax-m3:free` OpenRouter
сделал платной и отдаёт 404 с подсказкой убрать суффикс, `z-ai/glm-5.3-flash`
требует купленных кредитов. Остались две бесплатные Zhipu со своей квотой
и nemotron на OpenRouter; gemma и glm-5.2 держим последними — они сидят на
общем free-пуле и отвечают через раз.
"""
from __future__ import annotations

import json
import os
from typing import Iterator, Optional

from openai import OpenAI

ZHIPU_MODELS = {"glm-4.7-flash", "glm-4.5-flash"}

MODELS = [
    "glm-4.7-flash",                            # Zhipu, бесплатно, своя квота
    "glm-4.5-flash",                            # Zhipu, бесплатно, поколением младше
    "nvidia/nemotron-3-super-120b-a12b:free",   # OpenRouter, 262K контекста
    "z-ai/glm-5.2:free",                        # OpenRouter, общий пул
    "google/gemma-4-31b-it:free",               # OpenRouter, общий пул
]

# Глава целиком уходит в промпт, и самая длинная из двух книг — 10 тысяч
# символов, около 4500 токенов. Плюс рассуждения модели, которые списываются
# из того же бюджета. 4000 на ответ хватает с запасом.
MAX_TOKENS = 4000

# Служебные генерации (переписать под озвучку, собрать тест) — только там,
# где квота своя и ответ приходит быстро.
UTILITY_MODELS = ("glm-4.7-flash", "glm-4.5-flash")

_openrouter: Optional[OpenAI] = None
_zhipu: Optional[OpenAI] = None


def init() -> None:
    """Клиенты создаются на живых ключах: на пустой строке конструктор
    OpenAI бросает «Missing credentials» прямо при импорте, и приложение
    не стартует из-за необязательного провайдера."""
    global _openrouter, _zhipu
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    _openrouter = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=or_key,
        default_headers={
            "HTTP-Referer": os.getenv("APP_URL", "http://localhost:5003/"),
            "X-Title": "Book Tutor",
        },
    ) if or_key else None

    z_key = os.getenv("ZHIPU_API_KEY", "").strip()
    _zhipu = OpenAI(base_url="https://api.z.ai/api/paas/v4/",
                    api_key=z_key) if z_key else None


def client_for(model: str) -> Optional[OpenAI]:
    return _zhipu if model in ZHIPU_MODELS else _openrouter


def available() -> list[str]:
    return [m for m in MODELS if client_for(m) is not None]


def retryable(e: Exception) -> bool:
    """Стоит ли брать следующую модель вместо показа ошибки.

    429 — квота или троттлинг общего free-пула. 402 и «insufficient credits» —
    модель стала платной, а кредитов нет. 404 — слаг протух: так ушла
    minimax-m3:free, и без этой ветки чат падал бы на ней, не дойдя до живых.
    «overloaded» и код 1305 — Zhipu под нагрузкой; у бесплатных flash это
    ловится по нескольку раз в день и проходит само.
    """
    msg = str(e).lower()
    return any(t in msg for t in
               ("rate_limit", "429", "402", "404", "insufficient credits",
                "unknown model", "no endpoints", "overloaded", "1305",
                "502", "503", "timeout", "temporarily"))


def stream(messages: list[dict], preferred: Optional[str] = None,
           temperature: float = 0.6,
           max_tokens: int = MAX_TOKENS) -> Iterator[str]:
    """
    SSE-события для фронта. Текст идёт как {'text': ...}, рассуждения
    модели — отдельным каналом {'thinking': ...}, чтобы интерфейс мог
    показать их приглушённо и не мешать их с ответом.
    """
    chain = available()
    if not chain:
        yield _ev({"error": "нет ни одного настроенного провайдера: "
                            "заполни ZHIPU_API_KEY или OPENROUTER_API_KEY"})
        return
    if preferred in chain:
        start = chain.index(preferred)
        chain = chain[start:] + chain[:start]

    last_error = None
    for i, model in enumerate(chain):
        api = client_for(model)
        try:
            resp = api.chat.completions.create(
                model=model, messages=messages, stream=True,
                temperature=temperature, max_tokens=max_tokens)
            if i:
                yield _ev({"text": f"_(резервная модель: {model})_\n\n"})
            for chunk in resp:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning = (getattr(delta, "reasoning", None)
                             or getattr(delta, "reasoning_content", None))
                if reasoning:
                    yield _ev({"thinking": reasoning})
                if delta.content:
                    yield _ev({"text": delta.content})
            yield _ev({"done": True, "model": model})
            return
        except Exception as e:                      # noqa: BLE001
            last_error = e
            if retryable(e) and i < len(chain) - 1:
                continue
            yield _ev({"error": f"{type(e).__name__}: {str(e)[:300]}"})
            return
    yield _ev({"error": f"все модели отказали: {last_error}"})


def complete(messages: list[dict], models: tuple = UTILITY_MODELS,
             temperature: float = 0.3, max_tokens: int = 1500) -> str:
    """Разовый ответ без стрима — для служебных генераций."""
    for model in models:
        api = client_for(model)
        if api is None:
            continue
        try:
            resp = api.chat.completions.create(
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens)
            out = (resp.choices[0].message.content or "").strip()
            if out:
                return out
        except Exception as e:                      # noqa: BLE001
            if retryable(e):
                continue
            raise
    return ""


def _ev(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
