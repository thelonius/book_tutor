import type { Chapter, Hit, LibraryPayload, Term } from './types';

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) msg = body.error;
    } catch {
      // не-JSON — оставляем статус
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const fetchLibrary = () => json<LibraryPayload>('/api/library');

export const fetchChapter = (id: number) => json<Chapter>(`/api/chapter/${id}`);

export const fetchGlossary = (chapterId: number) =>
  json<{ terms: Term[] }>(`/api/glossary/${chapterId}`);

export const search = (query: string, bookId?: string | null) =>
  json<{ hits: Hit[] }>('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, book_id: bookId ?? null }),
  });

export const createNote = (chapterId: number, text: string) =>
  json<{ id: number }>('/api/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapter_id: chapterId, text }),
  });

export async function uploadBook(file: File, title?: string) {
  const form = new FormData();
  form.append('file', file);
  if (title) form.append('title', title);
  const res = await fetch('/api/books', { method: 'POST', body: form });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error ?? `HTTP ${res.status}`);
  return body as { id: string; title: string; chapters: number; chars: number };
}

// URL, а не blob: <audio> тянет его сам и умеет проигрывать по мере
// загрузки, не дожидаясь конца синтеза.
export const ttsUrl = () => '/api/tts';
