import { useState } from 'react';
import { useStore } from '../../state/store';
import { loadHistory } from '../../state/persistence';
import type { Hit } from '../../types';

/**
 * Куски, на которых построен ответ поиска.
 *
 * Номера здесь те же, на которые ссылается модель в тексте: [1], [3].
 * Рядом показано, какая половина поиска нашла абзац — L лексическая,
 * V векторная. Это не украшение: когда ответ выглядит натянутым, сразу
 * видно, что абзац пришёл только из векторов с низкого места, и верить
 * ему нужно меньше.
 */
export function Sources({ hits }: { hits: Hit[] }) {
  const { state, dispatch } = useStore();
  const [open, setOpen] = useState(false);

  if (!hits.length) return null;

  const goto = (hit: Hit) => {
    dispatch({ type: 'SELECT_BOOK', bookId: hit.book_id });
    dispatch({ type: 'SET_MODE', mode: 'read', messages: [] });
    dispatch({
      type: 'SELECT_CHAPTER',
      chapterId: hit.chapter_id,
      messages: loadHistory(hit.chapter_id, 'read'),
    });
  };

  return (
    <div className="sources">
      <button type="button" className="sources-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? '▾' : '▸'} источники: {hits.length}
      </button>
      {open &&
        hits.map((h, i) => (
          <div key={h.paragraph_id} className="source">
            <div className="source-head">
              <span className="source-num">[{i + 1}]</span>
              <button type="button" className="source-link" onClick={() => goto(h)}>
                {h.citation}
              </button>
              <span className="source-rank" title="позиция в лексическом и векторном списках">
                {h.lexical_rank ? `L${h.lexical_rank}` : 'L—'}
                {' '}
                {h.vector_rank ? `V${h.vector_rank}` : 'V—'}
              </span>
            </div>
            {h.image_ids?.length > 0 && (
              <div className="source-plates">
                {h.image_ids.map((id) => (
                  <a key={id} href={`/api/image/${id}?full=1`} target="_blank"
                     rel="noreferrer" title="Открыть оригинал">
                    <img src={`/api/image/${id}`} loading="lazy" alt="" />
                  </a>
                ))}
              </div>
            )}
            <div className="source-text">{h.text}</div>
          </div>
        ))}
      {state.streaming && <div className="muted">отвечаю по найденному…</div>}
    </div>
  );
}
