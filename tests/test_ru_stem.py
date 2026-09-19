import ru_stem


def test_stem_collapses_inflections():
    """Основной выигрыш в русском: падежи и числа одного слова сходятся
    в одну основу, и запрос «дом» находит «дома» и «домом»."""
    for group in (['дом', 'дома', 'домом', 'доме'],
                  ['избирательный', 'избирательных', 'избирательными'],
                  ['лишение', 'лишению', 'лишения']):
        stems = {ru_stem.stem_word(w) for w in group}
        assert len(stems) == 1, f'формы разошлись по основам: {group} -> {stems}'


def test_stem_does_not_bridge_derivation():
    """Чего стеммер не умеет и что не надо ему приписывать: глагол
    «лишили» и существительное «лишение» остаются разными основами.
    Словообразование снимается только лемматизатором."""
    assert ru_stem.stem_word('лишили') != ru_stem.stem_word('лишению')


def test_stop_words_dropped():
    assert ru_stem.query_terms('что было в этом доме') == [
        ru_stem.stem_word('доме')]


def test_short_words_dropped():
    assert ru_stem.query_terms('и о на') == []


def test_query_terms_dedupe():
    assert ru_stem.query_terms('дом дома домом') == [ru_stem.stem_word('дом')]


def test_fts_match_covers_both_columns():
    m = ru_stem.fts_match('лишенец')
    assert 'text:' in m and 'stem:' in m and ' OR ' in m


def test_fts_match_empty_for_noise():
    assert ru_stem.fts_match('и в на') == ''


def test_fts_match_quotes_operator_words():
    """Слово OR из запроса не должно разобраться как оператор FTS5."""
    m = ru_stem.fts_match('near or and')
    assert m == '' or all(part.count('"') == 2 for part in m.split(' OR '))


def test_find_forms_catches_inflections():
    """Термин глоссария приходит от модели в именительном, а в главе стоит
    в косвенном. Подсветке нужны реальные написания."""
    text = ('Ревизская сказка 1816 года. В той же ревизской сказке записан '
            'мещанин Мордух; до станции восемнадцать вёрст, а по другим '
            'бумагам в верстах считали иначе.')
    assert ru_stem.find_forms(text, 'ревизская сказка') == [
        'Ревизская сказка', 'ревизской сказке']
    assert ru_stem.find_forms(text, 'мещанин') == ['мещанин']
    assert set(ru_stem.find_forms(text, 'верста')) == {'вёрст', 'верстах'}


def test_find_forms_requires_adjacent_words():
    """Между словами термина допустимы пробел и дефис, но не точка:
    иначе конец одного предложения склеится с началом следующего."""
    assert ru_stem.find_forms('...закончилась ревизская. Сказка про другое',
                              'ревизская сказка') == []


def test_find_forms_on_absent_term():
    assert ru_stem.find_forms('дом на углу', 'ревизская сказка') == []
