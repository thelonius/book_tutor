import images


def rect(x0, x1, top, bottom, srcsize=(100, 100)):
    return {'x0': x0, 'x1': x1, 'top': top, 'bottom': bottom, 'srcsize': srcsize}


def line(x0, x1, top, text):
    return {'x0': x0, 'x1': x1, 'top': top, 'text': text}


def test_caption_is_the_line_right_below():
    r = rect(66, 529, 57, 355)
    lines = [line(68, 527, 360, 'Захарьевская улица на открытке начала XX века.'),
             line(74, 538, 726, 'Купчей с планом и адресом у меня по-прежнему нет.')]
    assert images._caption_line(r, lines).startswith('Захарьевская')


def test_line_above_the_image_is_not_its_caption():
    r = rect(66, 529, 300, 600)
    assert images._caption_line(r, [line(68, 527, 100, 'текст выше')]) is None


def test_distant_line_is_not_a_caption():
    """Между картинкой и основным текстом зазор больше, чем до подписи."""
    r = rect(66, 529, 57, 355)
    far = line(68, 527, 355 + images.MAX_GAP + 5, 'Это уже основной текст.')
    assert images._caption_line(r, [far]) is None


def test_neighbouring_column_is_not_a_caption():
    """Подпись под соседней картинкой в развороте не должна прилипнуть."""
    r = rect(62, 314, 100, 300)
    other = line(400, 533, 305, 'Подпись правого снимка.')
    assert images._caption_line(r, [other]) is None


def test_caption_carries_over_to_the_next_page():
    """
    Картинка внизу полосы уносит подпись на следующую страницу — так вышло
    у шести иллюстраций «Румера» и у тринадцати «Сегалова».
    """
    r = rect(62, 533, 611, 779)
    nxt = [line(90, 504, 60, 'Слева Мила, Людмила Абрамовна Залкинд.')]
    assert images._caption_line(r, [], nxt).startswith('Слева Мила')


def test_no_carry_over_when_something_stands_below():
    """Если ниже на своей странице текст всё-таки есть, но далеко, значит
    подпись к картинке не относится и тащить её со следующей нельзя."""
    r = rect(62, 533, 100, 300)
    below = [line(57, 538, 500, 'Основной текст, стоящий много ниже.')]
    nxt = [line(90, 504, 60, 'Первая строка следующей страницы.')]
    assert images._caption_line(r, below, nxt) is None


def test_closest_line_wins():
    r = rect(66, 529, 57, 355)
    lines = [line(68, 527, 375, 'дальше'), line(68, 527, 360, 'ближе')]
    assert images._caption_line(r, lines) == 'ближе'
