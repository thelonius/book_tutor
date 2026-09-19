// Режимы, привязанные к главе, плюс два, которые к ней не привязаны:
// 'read' — просто текст главы, без модели; 'search' — вопрос по всей
// библиотеке через гибридный поиск.
export type Mode = 'read' | 'discuss' | 'quiz' | 'context' | 'search';

export type Role = 'user' | 'assistant';

export interface Message {
  role: Role;
  content: string;
  // Источники, на которых построен ответ в режиме поиска. Приходят
  // отдельным SSE-событием перед текстом.
  sources?: Hit[];
}

export interface Paragraph {
  id: number;
  idx: number;
  kind: 'body' | 'caption';
  page: number | null;
  text: string;
}

export interface ChapterRef {
  id: number;
  idx: number;
  title: string;
  subtitle: string | null;
  page_from: number;
  page_to: number;
  n_paragraphs: number;
  n_chars: number;
}

export interface Chapter extends ChapterRef {
  book_id: string;
  book_title: string;
  paragraphs: Paragraph[];
  notes: Note[];
}

export interface Book {
  id: string;
  title: string;
  subtitle: string | null;
  source: string | null;
  n_pages: number;
  n_chapters: number;
  n_paragraphs: number;
  n_chars: number;
  chapters: ChapterRef[];
}

export interface Note {
  id: number;
  book_id: string;
  chapter_id: number | null;
  text: string;
  created_at: string;
}

export interface Hit {
  paragraph_id: number;
  text: string;
  kind: 'body' | 'caption';
  page: number | null;
  book_id: string;
  book_title: string;
  chapter_id: number;
  chapter_idx: number;
  chapter_title: string;
  score: number;
  // Позиции в лексическом и векторном списках до слияния. null — эта
  // половина поиска абзац не нашла; полезно видеть, кто сработал.
  lexical_rank: number | null;
  vector_rank: number | null;
  citation: string;
}

export interface ModeInfo {
  title: string;
  emoji: string;
  hint: string;
}

export interface LibraryPayload {
  books: Book[];
  modes: Record<string, ModeInfo>;
  /** Порядок показа режимов: словарь его не сохраняет. */
  mode_order: Mode[];
}

export interface Term {
  term: string;
  gloss: string;
  /** Написания термина, реально встречающиеся в главе: «ревизской сказке»,
   *  «мещанина». Подбираются на бэкенде стеммером. */
  forms: string[];
}
