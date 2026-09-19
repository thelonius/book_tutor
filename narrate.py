"""
Озвучка глав через Microsoft Edge TTS.

Движок сетевой: локальный процессор не нагружается вовсе, модель качать не
надо, и на слабой машине вроде N150 всё работает ровно так же, как на
ноутбуке. Для сравнения, XTTS с клонированием голоса на M1 с GPU даёт
real-time factor около 1,2, а на N150 без видеокарты ушёл бы в 6-15 — час
звучания за десять часов счёта. Клонированный голос того стоит, но это
отдельная история и отдельная машина.

Синтез идёт быстрее реального времени примерно в 3,7 раза: глава на десять
минут звучания рендерится за две с половиной.

    python narrate.py --chapter 8 --out audio/
    python narrate.py --book rumer --out audio/rumer
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

import edge_tts

VOICES = {'male': 'ru-RU-DmitryNeural', 'female': 'ru-RU-SvetlanaNeural'}
DEFAULT_VOICE = 'ru-RU-DmitryNeural'
DEFAULT_RATE = '-5%'

# Дореформенная орфография попадается внутри цитат из документов; синтезатор
# на ять и ижицу спотыкается.
PREREFORM = str.maketrans({'ѣ': 'е', 'Ѣ': 'Е', 'і': 'и', 'І': 'И',
                           'ѳ': 'ф', 'Ѳ': 'Ф', 'ѵ': 'и', 'Ѵ': 'И'})

ROMAN = {'XVI': 'шестнадцат', 'XVII': 'семнадцат', 'XVIII': 'восемнадцат',
         'XIX': 'девятнадцат', 'XX': 'двадцат', 'XXI': 'двадцать первы'}

ABBR = [
    (r'\bф\.\s*(?=\d)', 'фонд '),
    (r'\bоп\.\s*(?=\d)', 'опись '),
    (r'\bд\.\s*(?=\d)', 'дело '),
    (r'\bл\.\s*(?=\d)', 'лист '),
    (r'\bоб\.(?=\s|$|,)', 'оборот'),
    (r'\bкв\.\s+сажен', 'квадратных сажен'),
    (r'\bд\.\s*№\s*', 'дом номер '),
    (r'\bг\.\s*(?=[А-ЯЁ])', 'город '),
    (r'\bул\.\s*', 'улица '),
    (r'\bсм\.\s+', 'смотри '),
    (r'\bт\.\s*е\.', 'то есть'),
    (r'\bи\s+т\.\s*д\.', 'и так далее'),
    (r'\bгг\.', 'годов'),
]


def spoken(text: str) -> str:
    """Текст, пригодный для чтения вслух."""
    text = text.translate(PREREFORM)
    # Твёрдый знак на конце слова: «Мовшовъ Рифкинъ» -> «Мовшов Рифкин».
    text = re.sub(r'([бвгджзклмнпрстфхцчшщ])ъ\b', r'\1', text, flags=re.I)

    for roman, stem in ROMAN.items():
        text = re.sub(rf'\b{roman}\b(?=\s+(?:век|столет))', stem + 'ого', text)
        text = re.sub(rf'\b{roman}\b', stem + 'ый', text)

    for pattern, repl in ABBR:
        text = re.sub(pattern, repl, text)

    text = text.replace('№', 'номер ')
    # Диапазон годов синтезатор читает как вычитание.
    text = re.sub(r'(\d{4})\s*[—–-]\s*(\d{4})', r'\1 — \2', text)
    text = re.sub(r'\[подпись к иллюстрации\]', 'Подпись к иллюстрации.', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


async def synth_bytes(text: str, voice: str = DEFAULT_VOICE,
                      rate: str = DEFAULT_RATE) -> bytes:
    buf = bytearray()
    async for chunk in edge_tts.Communicate(spoken(text), voice, rate=rate).stream():
        if chunk['type'] == 'audio':
            buf.extend(chunk['data'])
    return bytes(buf)


def synth(text: str, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE) -> bytes:
    return asyncio.run(synth_bytes(text, voice, rate))


def slug(idx: int, title: str) -> str:
    s = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    return f'{idx:02d}_{s[:40]}'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='data/library.db')
    ap.add_argument('--book', help='озвучить книгу целиком, по главам')
    ap.add_argument('--chapter', type=int, help='id одной главы')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--voice', default='male', choices=list(VOICES) + list(VOICES.values()))
    ap.add_argument('--rate', default=DEFAULT_RATE)
    ap.add_argument('--captions', action='store_true',
                    help='читать и подписи к иллюстрациям')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    import store
    db = store.connect(args.db)
    voice = VOICES.get(args.voice, args.voice)

    if args.chapter:
        targets = [store.chapter(db, args.chapter)]
        if not targets[0]:
            raise SystemExit(f'главы {args.chapter} нет в {args.db}')
    elif args.book:
        targets = [store.chapter(db, c['id']) for c in store.chapters_of(db, args.book)]
        if not targets:
            raise SystemExit(f'книги {args.book!r} нет в {args.db}')
    else:
        raise SystemExit('нужен --book или --chapter')

    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for ch in targets:
        text = store.chapter_text(db, ch['id'], captions=args.captions)
        if not text.strip():
            continue
        dest = args.out / f"{slug(ch['idx'], ch['title'])}.mp3"
        if dest.exists() and not args.force:
            print(f"[{ch['idx']:>2}] готово раньше  {dest.name}")
            continue
        audio = synth(f"{ch['title']}. {text}", voice, args.rate)
        dest.write_bytes(audio)
        total += len(audio)
        print(f"[{ch['idx']:>2}] {len(audio)/1e6:>5.1f} МБ  {dest.name}", flush=True)
    print(f'итого {total/1e6:.1f} МБ в {args.out}')


if __name__ == '__main__':
    main()
