import { useEffect, useRef, type ChangeEvent, type KeyboardEvent } from 'react';
import { useStore } from '../../state/store';
import { useChatStream } from '../../hooks/useChatStream';
import { useComposerDraft } from './ComposerDraftContext';

const PLACEHOLDER: Record<string, string> = {
  discuss: 'Спроси что-нибудь по главе…',
  quiz: 'Твой ответ…',
  context: 'Какое слово или обстоятельство непонятно?',
  search: 'Вопрос по всем книгам сразу…',
};

export function Composer() {
  const { state } = useStore();
  const { mode, messages, streaming, preferredModel, chapterId, bookId } = state;
  const { send } = useChatStream();
  const { draft, setDraft } = useComposerDraft();
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }, [draft]);

  // Поиск главы не требует, остальные режимы без неё бессмысленны.
  const ready = mode === 'search' || chapterId != null;

  const submit = () => {
    const msg = draft.trim();
    if (!msg || streaming || !ready) return;
    void send({
      userMessage: { role: 'user', content: msg },
      historyBefore: messages,
      mode,
      model: preferredModel,
      chapterId,
      bookId,
    });
    setDraft('');
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="input-area">
      <div className="input-wrap">
        <textarea
          ref={taRef}
          value={draft}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setDraft(e.target.value)}
          onKeyDown={onKey}
          placeholder={ready ? (PLACEHOLDER[mode] ?? 'Вопрос…') : 'Сначала выбери главу слева'}
          rows={1}
          disabled={!ready}
        />
      </div>
      <button
        type="button"
        className="send-btn"
        disabled={streaming || !ready || draft.trim().length === 0}
        onClick={submit}
        title="Отправить"
      >
        ↑
      </button>
    </div>
  );
}
