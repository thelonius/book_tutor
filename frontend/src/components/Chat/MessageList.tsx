import { useEffect, useRef } from 'react';
import { useStore } from '../../state/store';
import { useChatStream } from '../../hooks/useChatStream';
import { Bubble } from './Bubble';
import { BubbleActions } from './BubbleActions';
import { Sources } from './Sources';

const EMPTY: Record<string, { title: string; body: string }> = {
  discuss: {
    title: 'Разбор главы',
    body: 'Наставник видит текст главы целиком. Спрашивай, что в ней происходит, что значит документ, почему автор делает такой вывод.',
  },
  quiz: {
    title: 'Проверка по главе',
    body: 'Вопросы по тому, что в главе действительно написано: кто кому кем приходится, что доказывает бумага, откуда взялась дата.',
  },
  context: {
    title: 'Эпоха',
    body: 'Что такое ревизская сказка, чем мещанин отличается от купца второй гильдии, сколько метров в квадратной сажени и что означало быть лишенцем.',
  },
  search: {
    title: 'Поиск по всем книгам',
    body: 'Вопрос поперёк глав и книг. Ответ собирается только из найденных кусков, каждый факт со ссылкой на книгу, главу и страницу.',
  },
};

export function MessageList() {
  const { state } = useStore();
  const { messages, streaming, thinking, mode, chapterId, bookId, preferredModel } = state;
  const { send } = useChatStream();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Автоскролл вниз, но не когда человек сам ушёл читать выше.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, thinking]);

  const sendQuick = (text: string) => {
    if (streaming) return;
    void send({
      userMessage: { role: 'user', content: text },
      historyBefore: messages,
      mode,
      model: preferredModel,
      chapterId,
      bookId,
    });
  };

  const empty = EMPTY[mode];

  return (
    <div className="messages" ref={scrollRef}>
      {messages.length === 0 ? (
        <div className="welcome">
          <h2>{empty?.title ?? 'Начнём'}</h2>
          <p>{empty?.body}</p>
          {mode !== 'search' && chapterId == null && (
            <p className="muted">Сначала выбери главу слева.</p>
          )}
        </div>
      ) : (
        messages.map((m, i) => {
          const isLast = i === messages.length - 1;
          const typing = streaming && isLast && m.role === 'assistant';
          const showActions =
            m.role === 'assistant' && m.content !== '' && !(streaming && isLast);
          return (
            <div key={i}>
              {m.sources && <Sources hits={m.sources} />}
              <Bubble role={m.role} content={m.content} typing={typing && m.content === ''} />
              {showActions && (
                <BubbleActions
                  text={m.content}
                  showNext={isLast && (mode === 'discuss' || mode === 'quiz')}
                  onNext={() =>
                    sendQuick(mode === 'quiz' ? 'Следующий вопрос.' : 'Дальше.')
                  }
                />
              )}
            </div>
          );
        })
      )}
      {streaming && thinking && (
        <div className="thinking-preview" style={{ marginLeft: 56 }}>
          {thinking}
        </div>
      )}
    </div>
  );
}
