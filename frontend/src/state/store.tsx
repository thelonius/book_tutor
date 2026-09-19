import {
  createContext,
  useContext,
  useEffect,
  useReducer,
  useRef,
  type Dispatch,
  type ReactNode,
} from 'react';
import type { Book, Chapter, Hit, Message, Mode, ModeInfo } from '../types';
import { fetchChapter, fetchLibrary } from '../api';
import { DEFAULT_MODEL } from './models';
import {
  loadHistory,
  loadPreferredModel,
  loadRead,
  loadSession,
  saveHistory,
  savePreferredModel,
  saveRead,
  saveSession,
} from './persistence';

export interface State {
  books: Book[];
  modes: Record<string, ModeInfo>;
  modeOrder: Mode[];
  libraryStatus: 'idle' | 'loading' | 'ready' | 'error';
  libraryError: string | null;

  bookId: string | null;
  chapterId: number | null;
  chapter: Chapter | null;
  chapterStatus: 'idle' | 'loading' | 'ready' | 'error';

  mode: Mode;
  messages: Message[];
  streaming: boolean;
  thinking: string;
  read: Set<number>;
  preferredModel: string;
}

export type Action =
  | { type: 'LIBRARY_LOAD' }
  | { type: 'LIBRARY_READY'; books: Book[]; modes: Record<string, ModeInfo>; modeOrder: Mode[] }
  | { type: 'LIBRARY_ERROR'; error: string }
  | { type: 'SELECT_BOOK'; bookId: string | null }
  | { type: 'SELECT_CHAPTER'; chapterId: number; messages: Message[] }
  | { type: 'CHAPTER_LOAD' }
  | { type: 'CHAPTER_READY'; chapter: Chapter }
  | { type: 'CHAPTER_ERROR' }
  | { type: 'SET_MODE'; mode: Mode; messages: Message[] }
  | { type: 'SET_MESSAGES'; messages: Message[] }
  | { type: 'STREAM_START'; userMessage: Message }
  | { type: 'STREAM_SOURCES'; sources: Hit[] }
  | { type: 'STREAM_TEXT'; text: string }
  | { type: 'STREAM_THINKING'; text: string }
  | { type: 'STREAM_END' }
  | { type: 'STREAM_ERROR'; error: string }
  | { type: 'MARK_READ'; chapterId: number }
  | { type: 'SET_MODEL'; model: string };

const initialState: State = {
  books: [],
  modes: {},
  modeOrder: [],
  libraryStatus: 'idle',
  libraryError: null,
  bookId: null,
  chapterId: null,
  chapter: null,
  chapterStatus: 'idle',
  mode: 'read',
  messages: [],
  streaming: false,
  thinking: '',
  read: new Set(),
  preferredModel: DEFAULT_MODEL,
};

/** Последний пузырь ассистента, который сейчас наполняется стримом. */
function patchLast(messages: Message[], patch: (m: Message) => Message): Message[] {
  const last = messages[messages.length - 1];
  if (!last || last.role !== 'assistant') return messages;
  const out = [...messages];
  out[out.length - 1] = patch(last);
  return out;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'LIBRARY_LOAD':
      return { ...state, libraryStatus: 'loading', libraryError: null };
    case 'LIBRARY_READY':
      return {
        ...state, libraryStatus: 'ready', books: action.books,
        modes: action.modes, modeOrder: action.modeOrder,
      };
    case 'LIBRARY_ERROR':
      return { ...state, libraryStatus: 'error', libraryError: action.error };

    case 'SELECT_BOOK':
      return { ...state, bookId: action.bookId };
    case 'SELECT_CHAPTER':
      return {
        ...state,
        chapterId: action.chapterId,
        messages: action.messages,
        thinking: '',
        streaming: false,
      };
    case 'CHAPTER_LOAD':
      return { ...state, chapterStatus: 'loading' };
    case 'CHAPTER_READY':
      return { ...state, chapterStatus: 'ready', chapter: action.chapter };
    case 'CHAPTER_ERROR':
      return { ...state, chapterStatus: 'error', chapter: null };

    case 'SET_MODE':
      return {
        ...state,
        mode: action.mode,
        messages: action.messages,
        thinking: '',
        streaming: false,
      };
    case 'SET_MESSAGES':
      return { ...state, messages: action.messages };

    case 'STREAM_START':
      return {
        ...state,
        streaming: true,
        thinking: '',
        messages: [...state.messages, action.userMessage, { role: 'assistant', content: '' }],
      };
    case 'STREAM_SOURCES':
      // Источники приезжают до первой буквы ответа — кладём их в тот же
      // пузырь, чтобы они показались рядом с текстом, пока он печатается.
      return {
        ...state,
        messages: patchLast(state.messages, (m) => ({ ...m, sources: action.sources })),
      };
    case 'STREAM_TEXT':
      return {
        ...state,
        thinking: '',
        messages: patchLast(state.messages, (m) => ({ ...m, content: m.content + action.text })),
      };
    case 'STREAM_THINKING':
      return { ...state, thinking: state.thinking + action.text };
    case 'STREAM_END':
      return { ...state, streaming: false, thinking: '' };
    case 'STREAM_ERROR': {
      const last = state.messages[state.messages.length - 1];
      const errMsg: Message = { role: 'assistant', content: `_(ошибка: ${action.error})_` };
      const updated = [...state.messages];
      if (last && last.role === 'assistant' && last.content === '') {
        updated[updated.length - 1] = errMsg;
      } else {
        updated.push(errMsg);
      }
      return { ...state, messages: updated, streaming: false, thinking: '' };
    }

    case 'MARK_READ': {
      if (state.read.has(action.chapterId)) return state;
      const next = new Set(state.read);
      next.add(action.chapterId);
      return { ...state, read: next };
    }
    case 'SET_MODEL':
      return { ...state, preferredModel: action.model };
    default:
      return state;
  }
}

interface StoreContextValue {
  state: State;
  dispatch: Dispatch<Action>;
}

const StoreContext = createContext<StoreContextValue | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState, hydrate);

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: 'LIBRARY_LOAD' });
    fetchLibrary()
      .then((data) => {
        if (cancelled) return;
        dispatch({
          type: 'LIBRARY_READY', books: data.books,
          modes: data.modes, modeOrder: data.mode_order,
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        dispatch({
          type: 'LIBRARY_ERROR',
          error: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Восстановление места в книге — только после загрузки библиотеки и
  // только если глава ещё существует: книгу могли удалить.
  const hydrated = useRef(false);
  useEffect(() => {
    if (state.libraryStatus !== 'ready' || hydrated.current) return;
    hydrated.current = true;
    const sess = loadSession();
    if (!sess) return;
    const book = state.books.find((b) => b.id === sess.bookId);
    if (!book) return;
    dispatch({ type: 'SELECT_BOOK', bookId: book.id });

    // Главу восстанавливаем всегда, даже если уходили в поиск: он к главе
    // не привязан, но вернувшись в чтение человек ждёт ту же главу, а не
    // пустой экран.
    const chapterId =
      sess.chapterId != null && book.chapters.some((c) => c.id === sess.chapterId)
        ? sess.chapterId
        : null;

    // Порядок важен: обе команды выставляют messages, поэтому историю
    // кладёт последняя.
    if (chapterId != null) {
      dispatch({ type: 'SELECT_CHAPTER', chapterId, messages: [] });
    }
    dispatch({
      type: 'SET_MODE',
      mode: sess.mode,
      messages: loadHistory(sess.mode === 'search' ? null : chapterId, sess.mode),
    });
  }, [state.libraryStatus, state.books]);

  // Текст главы нужен и для чтения, и для подсказок в чате — тянем один
  // раз на выбор главы, а не на каждое переключение режима.
  useEffect(() => {
    if (state.chapterId == null) return;
    let cancelled = false;
    dispatch({ type: 'CHAPTER_LOAD' });
    fetchChapter(state.chapterId)
      .then((ch) => !cancelled && dispatch({ type: 'CHAPTER_READY', chapter: ch }))
      .catch(() => !cancelled && dispatch({ type: 'CHAPTER_ERROR' }));
    return () => {
      cancelled = true;
    };
  }, [state.chapterId]);

  useEffect(() => {
    saveSession({ bookId: state.bookId, chapterId: state.chapterId, mode: state.mode });
  }, [state.bookId, state.chapterId, state.mode]);

  // Во время стрима не пишем: на перезагрузке подхватился бы обрывок ответа.
  useEffect(() => {
    if (state.streaming || state.messages.length === 0) return;
    saveHistory(state.chapterId, state.mode, state.messages);
  }, [state.chapterId, state.mode, state.messages, state.streaming]);

  useEffect(() => saveRead(state.read), [state.read]);
  useEffect(() => savePreferredModel(state.preferredModel), [state.preferredModel]);

  return <StoreContext.Provider value={{ state, dispatch }}>{children}</StoreContext.Provider>;
}

function hydrate(base: State): State {
  return { ...base, read: loadRead(), preferredModel: loadPreferredModel() };
}

export function useStore(): StoreContextValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useStore must be used inside <StoreProvider>');
  return ctx;
}
