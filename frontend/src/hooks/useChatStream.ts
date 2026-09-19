import { useCallback, useRef } from 'react';
import { useStore } from '../state/store';
import type { Hit, Message, Mode } from '../types';

interface SendArgs {
  userMessage: Message;
  /** История ДО userMessage: на бэкенд уходит historyBefore + [userMessage]. */
  historyBefore: Message[];
  mode: Mode;
  model: string;
  chapterId: number | null;
  /** В режиме поиска ограничивает выдачу одной книгой. */
  bookId?: string | null;
}

interface SseEvent {
  text?: string;
  thinking?: string;
  error?: string;
  sources?: Hit[];
  done?: boolean;
}

export function useChatStream() {
  const { dispatch } = useStore();
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async ({ userMessage, historyBefore, mode, model, chapterId, bookId }: SendArgs) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      dispatch({ type: 'STREAM_START', userMessage });

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [...historyBefore, userMessage],
            mode,
            model,
            chapter_id: chapterId,
            book_id: bookId ?? null,
          }),
          signal: ctrl.signal,
        });

        if (!res.ok) {
          let msg = `HTTP ${res.status}`;
          try {
            const body = (await res.json()) as { error?: string };
            if (body.error) msg = body.error;
          } catch {
            // не-JSON — оставляем статус
          }
          dispatch({ type: 'STREAM_ERROR', error: msg });
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) {
          dispatch({ type: 'STREAM_ERROR', error: 'пустой ответ' });
          return;
        }
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // Неполный хвост оставляем в буфере: событие может прийти
          // разорванным по границе чанка.
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            let ev: SseEvent;
            try {
              ev = JSON.parse(line.slice(6)) as SseEvent;
            } catch {
              continue;
            }
            if (ev.error) {
              dispatch({ type: 'STREAM_ERROR', error: ev.error });
              return;
            }
            if (ev.sources) dispatch({ type: 'STREAM_SOURCES', sources: ev.sources });
            if (ev.thinking) dispatch({ type: 'STREAM_THINKING', text: ev.thinking });
            if (ev.text) dispatch({ type: 'STREAM_TEXT', text: ev.text });
            if (ev.done) {
              dispatch({ type: 'STREAM_END' });
              return;
            }
          }
        }
        dispatch({ type: 'STREAM_END' });
      } catch (err) {
        if (ctrl.signal.aborted) return;
        dispatch({
          type: 'STREAM_ERROR',
          error: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [dispatch],
  );

  const cancel = useCallback(() => abortRef.current?.abort(), []);

  return { send, cancel };
}
