import { useRef, useState } from 'react';
import { useStore } from '../../state/store';
import { useUi } from '../../state/ui';
import { ModeSelector } from './ModeSelector';
import { loadHistory } from '../../state/persistence';
import { uploadBook } from '../../api';
import type { Book } from '../../types';

function minutes(chars: number): string {
  // Русская речь при синтезе держит примерно 16 символов в секунду.
  const m = Math.round(chars / 16 / 60);
  return m < 1 ? '<1 мин' : `${m} мин`;
}

export function Sidebar() {
  const { state, dispatch } = useStore();
  const ui = useUi();
  const { books, bookId, chapterId, mode, read, libraryStatus, libraryError } = state;
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string | null>(null);

  const openChapter = (id: number) => {
    dispatch({ type: 'SELECT_CHAPTER', chapterId: id, messages: loadHistory(id, mode) });
    ui.closeMobileSidebar();
  };

  const onUpload = async (file: File) => {
    setUploading(`Разбираю «${file.name}»…`);
    try {
      const res = await uploadBook(file);
      setUploading(`Готово: ${res.chapters} глав`);
      // Библиотека перечитывается перезагрузкой: книг мало, событие редкое,
      // а инкрементальное обновление стора здесь не окупается.
      setTimeout(() => window.location.reload(), 700);
    } catch (err) {
      setUploading(`Не вышло: ${err instanceof Error ? err.message : String(err)}`);
      setTimeout(() => setUploading(null), 5000);
    }
  };

  return (
    <div className={`sidebar${ui.mobileSidebarOpen ? ' open' : ''}${
      ui.desktopSidebarCollapsed ? ' collapsed' : ''}`}>
      <div className="sidebar-header">
        <h1>Книги</h1>
        <p className="sidebar-sub">чтение, разбор и поиск по архиву</p>
      </div>

      <ModeSelector />

      <div className="library">
        <div className="section-label">Библиотека</div>

        {libraryStatus === 'loading' && <div className="muted">Загружаю…</div>}
        {libraryStatus === 'error' && (
          <div className="muted">Библиотека не отвечает: {libraryError}</div>
        )}
        {libraryStatus === 'ready' && books.length === 0 && (
          <div className="muted">
            Пока пусто. Загрузи PDF с текстовым слоем кнопкой внизу.
          </div>
        )}

        {books.map((book: Book) => {
          const open = bookId === book.id;
          return (
            <div key={book.id} className="book">
              <button
                type="button"
                className={`book-btn${open ? ' active' : ''}`}
                onClick={() => dispatch({ type: 'SELECT_BOOK', bookId: open ? null : book.id })}
              >
                <span className="book-caret">{open ? '▾' : '▸'}</span>
                <span className="book-title">{book.title}</span>
                <span className="book-meta">{book.n_chapters}</span>
              </button>

              {open && (
                <div className="chapters">
                  {book.chapters.map((ch) => (
                    <button
                      key={ch.id}
                      type="button"
                      className={`chapter-btn${chapterId === ch.id ? ' active' : ''}`}
                      onClick={() => openChapter(ch.id)}
                      title={ch.subtitle ?? undefined}
                    >
                      <span className={`chapter-dot${read.has(ch.id) ? ' done' : ''}`} />
                      <span className="chapter-title">{ch.title}</span>
                      <span className="chapter-meta">{minutes(ch.n_chars)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="sidebar-footer">
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onUpload(f);
            e.target.value = '';
          }}
        />
        <button type="button" className="upload-btn" onClick={() => fileRef.current?.click()}>
          + Добавить книгу
        </button>
        {uploading && <div className="muted upload-status">{uploading}</div>}
      </div>
    </div>
  );
}
