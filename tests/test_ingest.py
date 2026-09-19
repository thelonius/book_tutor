import ingest


def test_caption_detected_by_indentation():
    """Подпись центрована, у абзаца продолжение садится на нулевую колонку."""
    caption = ['  «RIVKIND Мордух Мовшов, глава двора, 11 / 27». Ревизская сказка',
               '     НИАБ, ф. 333, оп. 9, д. 96, л. 10 об. — 11.']
    body = ['   В 1816 году в Минске стояло три двора этой семьи, и по ним',
            'хорошо видно, как был устроен род.']
    assert ingest.is_caption(caption)
    assert not ingest.is_caption(body)


def test_long_caption_starting_at_column_zero():
    """
    Ровно тот случай, на котором сломалось первое правило: подпись длинная,
    первая строка дотянулась до левого края, и блок уехал в основной текст.
    Судить надо по продолжениям — они сдвинуты.
    """
    caption = ['Сося Борухова. Ателье Г. В. Трунова, придворного фотографа, в Москве.',
               '  чужою рукою сделанная надпись: «Мать Бориса Ефимовича Румер».',
               '                    середине девяностых годов.']
    assert ingest.is_caption(caption)


def test_single_line_block_judged_by_its_own_indent():
    assert ingest.is_caption(['   Ревизская сказка 1816 года.'])
    assert not ingest.is_caption(['Первое имя, какое удаётся разобрать.'])


def test_chapter_head_recognised():
    page = 'Сося Борухова\nГлава пятая · 1838—1859\n\nПервое имя, какое удаётся разобрать.\n'
    assert ingest.head_lines(page) == ['Сося Борухова', 'Глава пятая · 1838—1859']


def test_body_page_has_no_head():
    page = ('Тот же двор второй в подлиннике. Семья № 377 записана так, как её\n'
            'разобрал писарь, и это важно.\n\nДальше идёт следующий абзац.\n')
    assert ingest.head_lines(page) is None


def test_head_rejects_indented_block():
    """Сдвинутый блок — подпись, а не шапка главы."""
    page = '  Сося Борухова\n  Глава пятая\n\nТекст главы.\n'
    assert ingest.head_lines(page) is None


def test_head_rejects_long_line():
    page = ('Э' * (ingest.MAX_HEAD_LINE + 1)) + '\nГлава пятая\n\nТекст.\n'
    assert ingest.head_lines(page) is None


def test_head_rejects_sentence_punctuation():
    page = 'Сося Борухова.\nГлава пятая\n\nТекст.\n'
    assert ingest.head_lines(page) is None


def test_line_blocks_split_on_blank_lines():
    page = 'а\nб\n\nв\n\n\nг\n'
    assert ingest.line_blocks(page) == [['а', 'б'], ['в'], ['г']]


def test_clean_collapses_whitespace_and_soft_hyphen():
    assert ingest.clean('дом­   на    углу') == 'дом на углу'
