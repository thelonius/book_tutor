import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useStore } from '../../state/store';
import { useSharedTts } from '../TtsProvider';
import { useGlossary } from '../Glossary/GlossaryProvider';
import { createNote } from '../../api';
import type { Illustration, Paragraph } from '../../types';

/**
 * Подсветка терминов глоссария в обычном тексте.
 *
 * В пузырях чата это делает rehype-плагин поверх markdown-дерева, но текст
 * главы markdown'ом не является — это plain text из PDF, и гонять его через
 * парсер значило бы ловить ложные срабатывания на каждом подчёркивании и
 * звёздочке в архивной цитате. Поэтому здесь свой проход по строке.
 */
function withTerms(text: string, regex: RegExp | null,
                   lookup: ((t: string) => string | null) | null) {
  if (!regex || !lookup) return text;
  const out: ReactNode[] = [];
  let last = 0;
  regex.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text))) {
    const gloss = lookup(m[1]);
    if (!gloss) continue;
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      <span key={`${m.index}-${m[1]}`} className="gloss-term" data-tooltip={gloss}>
        {m[1]}
      </span>,
    );
    last = m.index + m[0].length;
  }
  if (last === 0) return text;
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/**
 * Иллюстрации к одной подписи.
 *
 * Их бывает две: в книге они стоят рядом, и подпись описывает обе разом
 * («слева портрет молодых лет; справа он же с братом жены»). Поэтому в
 * ряд, а не столбиком — иначе «слева» и «справа» перестают значить что-то.
 */
function Plates({ items }: { items: Illustration[] }) {
  if (!items.length) return null;
  return (
    <div className={`plates${items.length > 1 ? ' pair' : ''}`}>
      {items.map((im) => (
        <a
          key={im.id}
          className="plate"
          href={`/api/image/${im.id}?full=1`}
          target="_blank"
          rel="noreferrer"
          title="Открыть оригинал"
          // Пропорции заранее: без них текст прыгает, пока грузятся
          // растры, а их в главе бывает по семь.
          style={{ flexGrow: im.width / im.height }}
        >
          <img src={`/api/image/${im.id}`} width={im.width} height={im.height}
               loading="lazy" alt="" />
        </a>
      ))}
    </div>
  );
}

export function ReaderView() {
  const { state, dispatch } = useStore();
  const { chapter, chapterStatus, chapterId } = state;
  const tts = useSharedTts();
  const glossary = useGlossary();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [noteSaved, setNoteSaved] = useState(false);

  // Новая глава — наверх, иначе открываешь её с середины предыдущей.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
    setNoteDraft('');
    setNoteSaved(false);
  }, [chapterId]);

  // Глава считается прочитанной, когда докрутили до низа. Отметка нужна
  // только для точки в оглавлении, так что порог грубый.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || chapterId == null) return;
    const onScroll = () => {
      if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
        dispatch({ type: 'MARK_READ', chapterId });
      }
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [chapterId, dispatch]);

  const terms = useMemo(
    () => (glossary ? { regex: glossary.regex, lookup: glossary.lookup } : null),
    [glossary],
  );

  // Картинка идёт перед своей подписью, как в книге. Те, чью подпись
  // геометрия не нашла, собираются в конце главы: потерять документ хуже,
  // чем показать его не на своём месте.
  const { byParagraph, orphans } = useMemo(() => {
    const map = new Map<number, Illustration[]>();
    const rest: Illustration[] = [];
    for (const im of chapter?.images ?? []) {
      if (im.paragraph_id == null) rest.push(im);
      else map.set(im.paragraph_id, [...(map.get(im.paragraph_id) ?? []), im]);
    }
    return { byParagraph: map, orphans: rest };
  }, [chapter]);

  if (chapterId == null) {
    return (
      <div className="messages">
        <div className="welcome">
          <div className="welcome-arrow">←</div>
          <h2>Выбери главу слева</h2>
          <p>
            Главу можно прочитать, послушать, разобрать с наставником или
            проверить себя по ней. Поиск работает сразу по всем книгам.
          </p>
        </div>
      </div>
    );
  }

  if (chapterStatus === 'loading' || !chapter) {
    return <div className="messages muted" style={{ padding: 24 }}>Открываю главу…</div>;
  }

  const saveNote = async () => {
    const text = noteDraft.trim();
    if (!text) return;
    await createNote(chapter.id, text);
    setNoteDraft('');
    setNoteSaved(true);
  };

  return (
    <div className="messages reader" ref={scrollRef}>
      <div className="reader-head">
        <h2>{chapter.title}</h2>
        {chapter.subtitle && <div className="reader-sub">{chapter.subtitle}</div>}
        <div className="reader-meta">
          {chapter.book_title} · с. {chapter.page_from}–{chapter.page_to}
          <button
            type="button"
            className="reader-tts"
            onClick={() =>
              tts.state === 'playing' || tts.state === 'paused'
                ? tts.toggle()
                : void tts.speakChapter(chapter.id)
            }
            title="Прочитать главу вслух"
          >
            {tts.state === 'loading' ? '⏳ готовлю…'
              : tts.state === 'playing' ? '⏸ пауза'
              : tts.state === 'paused' ? '▶ дальше'
              : '🔊 послушать'}
          </button>
        </div>
      </div>

      {chapter.paragraphs.map((p: Paragraph) => (
        <div key={p.id}>
          <Plates items={byParagraph.get(p.id) ?? []} />
          <p className={p.kind === 'caption' ? 'para caption' : 'para'}>
            {withTerms(p.text, terms?.regex ?? null, terms?.lookup ?? null)}
          </p>
        </div>
      ))}
      <Plates items={orphans} />

      <div className="reader-notes">
        <div className="section-label">Заметка к главе</div>
        {chapter.notes.map((n) => (
          <div key={n.id} className="note">{n.text}</div>
        ))}
        <textarea
          value={noteDraft}
          onChange={(e) => {
            setNoteDraft(e.target.value);
            setNoteSaved(false);
          }}
          placeholder="Что проверить, с чем сверить, что показалось странным…"
          rows={2}
        />
        <button type="button" className="upload-btn" onClick={() => void saveNote()}
                disabled={!noteDraft.trim()}>
          {noteSaved ? 'Сохранено' : 'Сохранить'}
        </button>
        <div className="muted">
          Заметки уходят наставнику вместе с текстом главы — он их видит и может
          на них ссылаться.
        </div>
      </div>
    </div>
  );
}
