"""
Русская морфология для полнотекстового поиска.

Токенизатор unicode61 из FTS5 режет текст по небуквенным символам и на этом
останавливается: «лишили», «лишению» и «лишённый» остаются тремя разными
словами, и запрос по одному из них не находит остальные. Для русского это
рубит отдачу поиска примерно вдвое.

Лечится теневой колонкой: тот же абзац, прогнанный через snowball-стеммер,
индексируется рядом с оригиналом. Запрос стеммится так же и матчится по
обеим колонкам сразу — точное совпадение слова всё ещё весит больше, потому
что попадает в обе.
"""
from __future__ import annotations

import functools
import re

import snowballstemmer

_WORD = re.compile(r'[а-яёa-z0-9]+', re.IGNORECASE)


@functools.lru_cache(maxsize=1)
def _stemmer():
    return snowballstemmer.stemmer('russian')


@functools.lru_cache(maxsize=100_000)
def stem_word(word: str) -> str:
    return _stemmer().stemWord(word.lower())


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def stem_text(text: str) -> str:
    """Строка из основ — то, что ложится в теневую колонку FTS."""
    return ' '.join(stem_word(w) for w in tokens(text))


# Слова, которые в запросе не несут смысла: из MATCH их выкидываем, иначе
# bm25 подтягивает абзацы, где часто встречается «который».
STOP = frozenset("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы
по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг
ли если уже или ни быть был него до вас нибудь опять уж вам сказал ведь там
потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была
сам чтоб без будто человек чего раз тоже себе под жизнь будет ж тогда кто этот
говорил того потому этого какой совсем ним здесь этом один почти мой тем чтобы
нее кажется сейчас были куда зачем сказать всех никогда сегодня можно при
наконец два об другой хоть после над больше тот через эти нас про всего них
какая много разве сказала три эту моя впрочем хорошо свою этой перед иногда
лучше чуть том нельзя такой им более всегда конечно всю между это её
""".split())


def query_terms(query: str, min_len: int = 3) -> list[str]:
    """Значимые основы запроса. Пустой список — искать нечего."""
    out, seen = [], set()
    for w in tokens(query):
        if len(w) < min_len or w in STOP:
            continue
        s = stem_word(w)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fts_match(query: str) -> str:
    """
    Выражение для FTS5 MATCH.

    Термины идут через OR, каждый ищется и в оригинале, и в основах. Кавычки
    вокруг термина обязательны: иначе слово вроде «NEAR» или «OR» из текста
    запроса разберётся как оператор и MATCH упадёт синтаксической ошибкой.
    """
    terms = query_terms(query)
    if not terms:
        return ''
    parts = []
    for t in terms:
        safe = t.replace('"', '')
        parts.append(f'text:"{safe}"')
        parts.append(f'stem:"{safe}"')
    return ' OR '.join(parts)


def find_forms(text: str, phrase: str, limit: int = 12) -> list[str]:
    """
    Все написания фразы, встречающиеся в тексте.

    Модель выдаёт термины глоссария в именительном падеже — «ревизская
    сказка», «мещанин», «верста», — а в тексте стоит «ревизской сказке»,
    «мещанина», «вёрстах». Подсветка по точному совпадению из двенадцати
    терминов главы находила два.

    Стеммер тут на стороне Python, поэтому формы подбираем здесь и отдаём
    фронту готовый список: собирать русскую морфологию в браузере ради
    подсказок незачем.

    Возвращает подстроки исходного текста как есть, включая регистр и «ё»:
    из них на фронте собирается regex подсветки.
    """
    target = [stem_word(w) for w in tokens(phrase)]
    if not target:
        return []

    # Позиции слов в тексте: нужны, чтобы вырезать подстроку целиком,
    # вместе с дефисами и пробелами между словами фразы.
    spans = [(m.start(), m.end(), stem_word(m.group(0)))
             for m in _WORD.finditer(text)]
    n = len(target)

    out, seen = [], set()
    for i in range(len(spans) - n + 1):
        if [s[2] for s in spans[i:i + n]] != target:
            continue
        # Между словами фразы допускаем только пробелы и дефис: иначе
        # «сказка» и «ревизская» с точкой между ними склеятся в термин.
        gap = text[spans[i][1]:spans[i + n - 1][0]]
        if n > 1 and not re.fullmatch(r'[\s\-–—]*', gap):
            continue
        form = text[spans[i][0]:spans[i + n - 1][1]]
        key = form.lower()
        if key not in seen:
            seen.add(key)
            out.append(form)
        if len(out) >= limit:
            break
    return out
