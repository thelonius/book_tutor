import { createContext, useContext, useState, type ReactNode } from 'react';

// Черновик поля ввода, приподнятый над Composer, чтобы QuickActions мог
// прочитать текст пользователя и подмешать его как контекст к действию
// («Объясни иначе», «Пример кода» и т.п.), а затем очистить поле.
interface ComposerDraftValue {
  draft: string;
  setDraft: (s: string) => void;
}

const ComposerDraftContext = createContext<ComposerDraftValue | null>(null);

export function ComposerDraftProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState('');
  return (
    <ComposerDraftContext.Provider value={{ draft, setDraft }}>
      {children}
    </ComposerDraftContext.Provider>
  );
}

export function useComposerDraft(): ComposerDraftValue {
  const ctx = useContext(ComposerDraftContext);
  if (!ctx) throw new Error('useComposerDraft must be used inside <ComposerDraftProvider>');
  return ctx;
}
