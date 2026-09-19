// История переписки и выбранное место в книге — в localStorage. Заметки
// и сами книги живут на сервере: их человек пишет осознанно и терять их
// при очистке браузера нельзя, а переписка с моделью расходная.
import type { Message, Mode } from '../types';
import { DEFAULT_MODEL, isKnownModel } from './models';

export const histKey = (chapterId: number, mode: Mode) =>
  `book_chat_${chapterId}_${mode}`;
const SEARCH_HIST_KEY = 'book_chat_search';
const SESSION_KEY = 'book_session';
const READ_KEY = 'book_read';
const MODEL_KEY = 'book_model';
const SIDEBAR_COLLAPSED_KEY = 'book_sidebar_collapsed';

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function loadHistory(chapterId: number | null, mode: Mode): Message[] {
  if (mode === 'search') return read<Message[]>(SEARCH_HIST_KEY, []);
  if (chapterId == null) return [];
  return read<Message[]>(histKey(chapterId, mode), []);
}

export function saveHistory(chapterId: number | null, mode: Mode, msgs: Message[]): void {
  const key = mode === 'search' ? SEARCH_HIST_KEY
    : chapterId != null ? histKey(chapterId, mode) : null;
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(msgs));
  } catch {
    // Квота кончилась — переписка расходная, молча переживаем.
  }
}

export function clearHistory(chapterId: number | null, mode: Mode): void {
  const key = mode === 'search' ? SEARCH_HIST_KEY
    : chapterId != null ? histKey(chapterId, mode) : null;
  if (key) localStorage.removeItem(key);
}

export interface SessionState {
  bookId: string | null;
  chapterId: number | null;
  mode: Mode;
}

export function loadSession(): SessionState | null {
  const parsed = read<Partial<SessionState> | null>(SESSION_KEY, null);
  if (!parsed) return null;
  return {
    bookId: typeof parsed.bookId === 'string' ? parsed.bookId : null,
    chapterId: typeof parsed.chapterId === 'number' ? parsed.chapterId : null,
    mode: (parsed.mode as Mode) ?? 'read',
  };
}

export function saveSession(s: SessionState): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
}

/** Прочитанные главы — для отметок в оглавлении. */
export function loadRead(): Set<number> {
  const arr = read<number[]>(READ_KEY, []);
  return new Set(Array.isArray(arr) ? arr : []);
}

export function saveRead(ids: Set<number>): void {
  localStorage.setItem(READ_KEY, JSON.stringify([...ids]));
}

export function loadPreferredModel(): string {
  const saved = localStorage.getItem(MODEL_KEY);
  return saved && isKnownModel(saved) ? saved : DEFAULT_MODEL;
}

export function savePreferredModel(model: string): void {
  localStorage.setItem(MODEL_KEY, model);
}

export function loadSidebarCollapsed(): boolean {
  return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
}

export function saveSidebarCollapsed(collapsed: boolean): void {
  if (collapsed) localStorage.setItem(SIDEBAR_COLLAPSED_KEY, '1');
  else localStorage.removeItem(SIDEBAR_COLLAPSED_KEY);
}
