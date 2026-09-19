"""
Разбор PDF с текстовым слоем на главы и абзацы.

Работает на `pdftotext -layout`, который сохраняет отступы вёрстки — и это
оказывается единственным, что отделяет подписи к иллюстрациям от основного
текста. Смотреть надо на строки-продолжения: абзац выключен по левому краю,
и вторая его строка всегда садится на нулевую колонку, а у подписи она
сдвинута или центрована.

Первая строка блока для этого не годится, хотя так и было сделано сначала.
Достаточно длинная подпись растягивается на всю ширину полосы и тоже
начинается с нулевой колонки: «Сося Борухова. Ателье Г. В. Трунова…» на
странице 23 «Румера» уезжала в основной текст, и с нею ещё 43 блока на двух
книгах.

Главы ищутся по шапке страницы: две-три коротких строки по левому краю без
точки на конце («Сося Борухова» / «Глава пятая · 1838—1859»). Абзац такого
блока не даёт — он длинный и кончается знаком препинания.

    python ingest.py --pdf "Румер.pdf" --id rumer
    python ingest.py --pdf "Румер.pdf" --id rumer --dry-run
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_HEAD_LINE = 60          # длиннее — это уже текст, а не заголовок
MAX_HEAD_LINES = 3


def pdf_pages(pdf: Path) -> list[str]:
    try:
        out = subprocess.run(['pdftotext', '-layout', str(pdf), '-'],
                             capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        sys.exit('нужен pdftotext: brew install poppler')
    except subprocess.CalledProcessError as e:
        sys.exit(f'pdftotext не осилил {pdf}: {e.stderr[:200]}')
    return out.split('\f')


def line_blocks(page: str) -> list[list[str]]:
    """Страница -> абзацы: непрерывные группы непустых строк."""
    out: list[list[str]] = []
    cur: list[str] = []
    for line in page.split('\n'):
        if line.strip():
            cur.append(line)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def is_caption(block: list[str]) -> bool:
    """
    Подпись, цитата-врезка или библиографическая запись — всё, что набрано
    не как основной текст.

    Решают отступы строк-продолжений: у абзаца они на нулевой колонке, у
    подписи сдвинуты. Первую строку не смотрим — длинная подпись доходит
    до левого края и ничем от абзаца не отличается.
    """
    indents = [len(l) - len(l.lstrip()) for l in block]
    if len(indents) == 1:
        # Однострочный блок продолжений не имеет, судим по нему самому.
        return indents[0] > 0
    return all(i > 0 for i in indents[1:])


def head_lines(page: str) -> list[str] | None:
    """Шапка главы, если страница её открывает."""
    blocks = line_blocks(page)
    if not blocks:
        return None
    head = blocks[0]
    if not 2 <= len(head) <= MAX_HEAD_LINES:
        return None
    for line in head:
        if len(line) - len(line.lstrip()):
            return None
        s = line.strip()
        if len(s) > MAX_HEAD_LINE or re.search(r'[.,;:!?»]$', s):
            return None
    return [l.strip() for l in head]


def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text.replace('­', '')).strip()


def parse(pdf: Path, title: str | None = None) -> tuple[dict, list[dict]]:
    pages = pdf_pages(pdf)
    chapters: list[dict] = []

    for pageno, page in enumerate(pages, 1):
        head = head_lines(page)
        blocks = line_blocks(page)

        if head or not chapters:
            chapters.append({
                'title': head[0] if head else 'Титул',
                'subtitle': head[1] if head and len(head) > 1 else None,
                'page_from': pageno,
                'page_to': pageno,
                'paragraphs': [],
            })
            # Шапка уже записана в заголовок главы, второй раз как абзац
            # она не нужна.
            if head:
                blocks = blocks[1:]

        chapters[-1]['page_to'] = pageno
        for block in blocks:
            text = clean(' '.join(l.strip() for l in block))
            if not text:
                continue
            # На титуле «подпись» — это само название книги, её оставляем
            # телом: иначе первая глава окажется пустой.
            kind = 'caption' if (is_caption(block) and pageno > 1) else 'body'
            chapters[-1]['paragraphs'].append(
                {'kind': kind, 'page': pageno, 'text': text})

    chapters = [c for c in chapters if c['paragraphs']]

    # Название и подзаголовок книги — первые строки титула. head_lines их
    # не отдаёт: на титуле шапка центрована, а он требует нулевой колонки.
    # Поэтому берём первый блок первой страницы построчно, до склейки.
    title_block = (line_blocks(pages[0]) or [[]])[0]
    lines = [clean(l) for l in title_block if clean(l)]
    book = {
        'title': title or (lines[0] if lines else pdf.stem),
        'subtitle': ' · '.join(lines[1:3]) if len(lines) > 1 else None,
        'source': pdf.name,
        'n_pages': len([p for p in pages if p.strip()]),
    }
    return book, chapters


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', required=True, type=Path)
    ap.add_argument('--id', help='идентификатор книги; по умолчанию имя файла')
    ap.add_argument('--title', help='название, если из титула вышло криво')
    ap.add_argument('--db', default='data/library.db')
    ap.add_argument('--no-vectors', action='store_true',
                    help='только текст и FTS, эмбеддинги посчитать позже')
    ap.add_argument('--no-images', action='store_true',
                    help='не вынимать иллюстрации (книга на 20+ МБ растров)')
    ap.add_argument('--images-dir', default='data/images',
                    help='куда складывать иллюстрации')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    book, chapters = parse(args.pdf, args.title)
    book['id'] = args.id or re.sub(r'\W+', '_', args.pdf.stem.lower()).strip('_')

    n_body = sum(sum(p['kind'] == 'body' for p in c['paragraphs']) for c in chapters)
    n_cap = sum(sum(p['kind'] == 'caption' for p in c['paragraphs']) for c in chapters)
    chars = sum(len(p['text']) for c in chapters for p in c['paragraphs']
                if p['kind'] == 'body')
    print(f"[{book['id']}] {book['title']}")
    print(f"  {len(chapters)} глав, {n_body} абзацев, {n_cap} подписей, "
          f"{chars} символов основного текста")

    if args.dry_run:
        for i, c in enumerate(chapters, 1):
            body = sum(len(p['text']) for p in c['paragraphs'] if p['kind'] == 'body')
            print(f"{i:>3}. с.{c['page_from']:>3}–{c['page_to']:<3} "
                  f"{c['title'][:44]:<44} {body:>6} симв")
        return

    import store
    db = store.connect(args.db)
    store.add_book(db, book, chapters)
    print(f'  записано в {args.db}')

    if not args.no_images:
        import images
        items = images.link(args.pdf, Path(args.images_dir) / book['id'])
        linked = store.add_images(db, book['id'], items)
        print(f'  иллюстраций {len(items)}, привязано к подписям {linked}')

    if not args.no_vectors:
        import embeddings
        n = store.index_vectors(db, embeddings.embed, book_id=book['id'])
        print(f'  посчитано эмбеддингов: {n}')


if __name__ == '__main__':
    main()
