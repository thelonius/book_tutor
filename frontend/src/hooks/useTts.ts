import { useCallback, useEffect, useRef, useState } from 'react';

export type TtsState = 'idle' | 'loading' | 'playing' | 'paused';

interface SpeakOpts {
  onComplete?: () => void;
}

// TTS-плеер: один активный аудио-трек на инстанс хука. Аналог speak/ttsReset
// из legacy. Race-safety: каждое аудио сверяется с currentRef перед действием —
// если нас успели сбросить (reset вызвали или другой speak пошёл), обработчики
// молча выходят.
export function useTts() {
  const [state, setState] = useState<TtsState>('idle');
  // ID текущего трека. Любая async-операция сверяет свой captured runId
  // с currentRunRef.current — если не совпало, операция отменена.
  const currentRunRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const allAudiosRef = useRef<Set<HTMLAudioElement>>(new Set());

  const reset = useCallback(() => {
    currentRunRef.current++; // инвалидируем все async ветки
    if (abortRef.current) {
      try {
        abortRef.current.abort();
      } catch {
        // ignore
      }
      abortRef.current = null;
    }
    audioRef.current = null;
    for (const a of allAudiosRef.current) {
      try {
        a.pause();
        a.src = '';
        a.load();
      } catch {
        // ignore
      }
    }
    allAudiosRef.current.clear();
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    setState('idle');
  }, []);

  useEffect(() => () => reset(), [reset]);

  // Чистим markdown-шум перед отправкой на /api/tts. Сервер сам делает
  // основную очистку, тут только phantom-блоки.
  const cleanForTts = (raw: string): string =>
    raw
      .replace(/_\(резервная модель:[^)]+\)_/g, '')
      .replace(/<think>[\s\S]*?<\/think>/g, '')
      .trim();

  // Тело запроса к /api/tts. Текст пузыря уходит как есть, а глава — по
  // chapter_id: десять тысяч символов незачем гонять по сети, и сервер
  // отдаёт такую озвучку из кеша.
  const play = useCallback(
    async (body: Record<string, unknown>, opts: SpeakOpts = {}): Promise<void> => {
      // Если уже играет тот же трек — toggle play/pause.
      // На уровне хука это упрощено: caller сам решает идемпотентность.
      // (Полноценный «вторая клик — пауза» делается через сравнение btn id
      // в legacy; здесь это можно сделать на уровне компонента, если нужно.)
      reset();
      const runId = ++currentRunRef.current;
      setState('loading');
      abortRef.current = new AbortController();
      try {
        const res = await fetch('/api/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: abortRef.current.signal,
        });
        if (runId !== currentRunRef.current) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        if (runId !== currentRunRef.current) return;
        const url = URL.createObjectURL(blob);
        if (runId !== currentRunRef.current) {
          URL.revokeObjectURL(url);
          return;
        }
        urlRef.current = url;
        const audio = new Audio(url);
        audioRef.current = audio;
        allAudiosRef.current.add(audio);
        audio.onplay = () => {
          if (audioRef.current === audio) setState('playing');
        };
        audio.onpause = () => {
          if (audioRef.current === audio && !audio.ended) setState('paused');
        };
        audio.onended = () => {
          allAudiosRef.current.delete(audio);
          if (audioRef.current === audio) {
            reset();
            opts.onComplete?.();
          }
        };
        audio.onerror = () => {
          allAudiosRef.current.delete(audio);
          if (audioRef.current === audio) reset();
        };
        try {
          await audio.play();
        } catch (err) {
          if (err && (err as Error).name === 'AbortError') return;
          if (audioRef.current === audio) reset();
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        if (runId !== currentRunRef.current) return;
        reset();
      }
    },
    [reset],
  );

  const speak = useCallback(
    (rawText: string, opts: SpeakOpts = {}) =>
      play({ text: cleanForTts(rawText).slice(0, 4000) }, opts),
    [play],
  );

  const speakChapter = useCallback(
    (chapterId: number, opts: SpeakOpts = {}) => play({ chapter_id: chapterId }, opts),
    [play],
  );

  // Прелоад: дёргаем /api/tts без проигрывания, чтобы сервер прогрел кеш.
  const preload = useCallback((rawText: string): void => {
    void fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: cleanForTts(rawText).slice(0, 4000) }),
    }).catch(() => undefined);
  }, []);

  const toggle = useCallback((): void => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      a.play().catch(() => reset());
    } else {
      a.pause();
    }
  }, [reset]);

  return { state, speak, speakChapter, preload, toggle, reset };
}
