import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { buildGlossaryConfig, type GlossaryConfig } from '../../lib/rehype-glossary';
import { fetchGlossary } from '../../api';
import { useStore } from '../../state/store';

const GlossaryContext = createContext<GlossaryConfig | null>(null);

/**
 * Глоссарий здесь свой на каждую главу, а не общий файл на весь проект.
 *
 * В тренажёре по MLOps словарь был статическим: сотня терминов, известных
 * заранее. У книги так не выйдет — какие слова окажутся непонятными,
 * зависит от того, какую книгу загрузили. Поэтому термины собирает модель
 * по тексту главы, а бэкенд кеширует результат по chapter_id: второй заход
 * в ту же главу уже не тратит запрос.
 */
export function GlossaryProvider({ children }: { children: ReactNode }) {
  const { state } = useStore();
  const chapterId = state.chapterId;
  const [config, setConfig] = useState<GlossaryConfig | null>(null);

  useEffect(() => {
    if (chapterId == null) {
      setConfig(null);
      return;
    }
    let cancelled = false;
    // Пока термины едут, rehype-плагин просто ничего не делает: текст
    // отрисуется сразу, подсказки проявятся следом.
    setConfig(null);
    fetchGlossary(chapterId)
      .then(({ terms }) => {
        if (cancelled || terms.length === 0) return;
        // Ключ словаря — каждая встреченная в главе форма, а не сам
        // термин: regex подсветки собирается по ним.
        const byForm: Record<string, string> = {};
        for (const t of terms) {
          for (const form of t.forms?.length ? t.forms : [t.term]) {
            byForm[form] = t.gloss;
          }
        }
        setConfig(buildGlossaryConfig(byForm));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [chapterId]);

  return <GlossaryContext.Provider value={config}>{children}</GlossaryContext.Provider>;
}

export function useGlossary(): GlossaryConfig | null {
  return useContext(GlossaryContext);
}
