"""
Иллюстрации из PDF и привязка их к подписям.

Без картинок половина книги пропадает: это семейный архив, и подпись
«слева портрет молодых лет; справа он же с братом жены» без самого снимка
не значит ничего.

Растры достаёт `pdfimages -all -p` из poppler — быстро (92 картинки за
полсекунды) и без перекодирования, JPEG из PDF выходит тем же файлом.
Номер страницы он кладёт прямо в имя, `prefix-003-000.jpg`.

Геометрию даёт pdfplumber: где стоит картинка и где строки текста. Она же
решает, какая подпись чья. По количеству сопоставить не выходит — на двух
книгах число картинок и подписей сходится меньше чем на половине страниц:
одна подпись описывает два снимка рядом, а часть блоков с той же вёрсткой
вообще относится не к иллюстрациям, а к перечню источников.

Геометрия заодно исправляет разметку. Блок, стоящий вплотную под картинкой,
является подписью независимо от отступов, и так находятся подписи под
схемами на альбомных страницах, которые правило отступов пропускало.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

# Подпись стоит сразу под картинкой; на двух книгах зазор около пяти
# пунктов. Двадцать пять — с запасом на вёрстку, но меньше межабзацного
# отступа, чтобы не прихватить начало основного текста.
MAX_GAP = 25.0

# Минимальное перекрытие по горизонтали, чтобы считать строку подписью к
# этой картинке, а не к соседней в две колонки.
MIN_OVERLAP = 0.3

# Ширина для показа в браузере. Оригиналы бывают 2467 пикселей по длинной стороне
# и весят по 600 КБ — для чтения с экрана это впустую.
WEB_WIDTH = 1400
WEB_QUALITY = 85

# Мелочь вроде логотипов и линеек: иллюстрацией не является.
MIN_SIDE = 120


def _real_images(pdf: Path) -> set[tuple[int, int]]:
    """
    Номера настоящих картинок — (страница, номер) из `pdfimages -list`.

    Маску прозрачности pdfimages выгружает отдельным файлом ровно того же
    размера, и в «Сегалове» таких тринадцать. Без отсева маска занимала
    место картинки при сведении по размеру, и настоящая иллюстрация
    оставалась без подписи.
    """
    out = subprocess.run(['pdfimages', '-list', '-p', str(pdf)],
                         capture_output=True, text=True).stdout
    keep = set()
    for line in out.splitlines()[2:]:
        f = line.split()
        if len(f) > 2 and f[2] == 'image':
            keep.add((int(f[0]), int(f[1])))
    return keep


def extract(pdf: Path, dest: Path) -> list[dict]:
    """Растры из PDF в каталог. Возвращает [{page, idx, path}] без масок."""
    if not shutil.which('pdfimages'):
        sys.exit('нужен pdfimages: brew install poppler')
    dest.mkdir(parents=True, exist_ok=True)
    keep = _real_images(pdf)
    subprocess.run(['pdfimages', '-all', '-p', str(pdf), str(dest / 'img')],
                   check=True, capture_output=True)

    out = []
    for path in sorted(dest.glob('img-*')):
        m = re.match(r'img-(\d+)-(\d+)', path.stem)
        if not m:
            continue
        page, idx = int(m.group(1)), int(m.group(2))
        if keep and (page, idx) not in keep:
            path.unlink(missing_ok=True)
            continue
        out.append({'page': page, 'idx': idx, 'path': path})
    return out


def layout(pdf: Path) -> dict[int, dict]:
    """Позиции картинок и строк текста по страницам."""
    import pdfplumber

    pages: dict[int, dict] = {}
    with pdfplumber.open(str(pdf)) as doc:
        for n, page in enumerate(doc.pages, 1):
            try:
                lines = page.extract_text_lines()
            except Exception:                       # noqa: BLE001
                lines = []
            pages[n] = {
                'images': [
                    {'x0': im['x0'], 'x1': im['x1'],
                     'top': im['top'], 'bottom': im['bottom'],
                     'srcsize': tuple(im.get('srcsize') or ())}
                    for im in page.images
                ],
                'lines': [
                    {'x0': ln['x0'], 'x1': ln['x1'], 'top': ln['top'],
                     'text': re.sub(r'\s+', ' ', ln['text']).strip()}
                    for ln in lines
                ],
            }
    return pages


def _caption_line(rect: dict, lines: list[dict],
                  next_lines: list[dict] | None = None) -> str | None:
    """
    Строка, стоящая вплотную под картинкой.

    Картинка внизу полосы уносит подпись на следующую страницу — так вышло
    у всех шести иллюстраций «Румера», которым подпись сперва не нашлась.
    Если ниже на своей странице ничего нет, берём первую строку следующей.
    """
    width = max(rect['x1'] - rect['x0'], 1.0)
    best, best_gap = None, MAX_GAP
    for ln in lines:
        gap = ln['top'] - rect['bottom']
        if not 0 <= gap < best_gap:
            continue
        overlap = min(rect['x1'], ln['x1']) - max(rect['x0'], ln['x0'])
        if overlap / width < MIN_OVERLAP:
            continue
        best, best_gap = ln, gap
    if best:
        return best['text']

    below = [ln for ln in lines if ln['top'] >= rect['bottom']]
    if below or not next_lines:
        # Под картинкой что-то есть, просто далеко — значит подпись к ней
        # не относится, и тянуть её со следующей страницы нельзя.
        return None
    return next_lines[0]['text']


def link(pdf: Path, dest: Path) -> list[dict]:
    """
    Картинки с привязкой к подписи.

    Файлы от pdfimages и прямоугольники от pdfplumber сводятся по размеру в
    пикселях: порядок внутри страницы у них совпадает не всегда, а
    ширина с высотой совпадают точно.
    """
    files = extract(pdf, dest)
    geo = layout(pdf)

    from PIL import Image

    by_page: dict[int, list[dict]] = {}
    for f in files:
        by_page.setdefault(f['page'], []).append(f)

    out = []
    for page, items in sorted(by_page.items()):
        rects = list(geo.get(page, {}).get('images', []))
        lines = geo.get(page, {}).get('lines', [])
        next_lines = geo.get(page + 1, {}).get('lines', [])

        for item in items:
            with Image.open(item['path']) as im:
                size = im.size
            if min(size) < MIN_SIDE:
                item['path'].unlink(missing_ok=True)
                continue

            match = next((r for r in rects if r['srcsize'] == size), None)
            if match is None and rects:
                # Размер не сошёлся — берём прямоугольник по порядку. Так
                # бывает, когда PDF хранит картинку с маской и pdfimages
                # отдаёт уже склеенный растр другого размера.
                match = rects[0]
            if match is not None:
                rects.remove(match)

            out.append({
                'page': page,
                'idx': item['idx'],
                'path': item['path'],
                'width': size[0],
                'height': size[1],
                'caption_line': (_caption_line(match, lines, next_lines)
                                 if match else None),
            })
    return out


def make_web_copy(src: Path) -> Path:
    """Уменьшенная копия для показа. Оригинал остаётся рядом."""
    from PIL import Image

    dest = src.with_suffix('.web.jpg')
    if dest.exists():
        return dest
    with Image.open(src) as im:
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        if im.width > WEB_WIDTH:
            height = round(im.height * WEB_WIDTH / im.width)
            im = im.resize((WEB_WIDTH, height), Image.LANCZOS)
        im.save(dest, 'JPEG', quality=WEB_QUALITY, optimize=True)
    return dest
