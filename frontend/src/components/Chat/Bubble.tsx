import { memo, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { rehypeGlossary } from '../../lib/rehype-glossary';
import { useGlossary } from '../Glossary/GlossaryProvider';
import type { Role } from '../../types';

interface Props {
  role: Role;
  content: string;
  /** Три точки, пока стрим стартовал, но первая буква ещё не пришла. */
  typing?: boolean;
}

// Подсветки кода здесь нет намеренно: в разговоре про архивные документы
// блоков кода не бывает, а highlight.js с lowlight тянут за собой около
// 300 КБ. В тренажёре по MLOps они были нужны, здесь — нет.
function BubbleInner({ role, content, typing }: Props) {
  const glossary = useGlossary();

  // Стабильный массив: иначе react-markdown перепарсивает дерево на каждый
  // ререндер, а во время стрима их сотни. Пересоздаётся один раз — когда
  // приезжает глоссарий главы.
  const rehypePlugins = useMemo(
    () => (glossary ? [() => rehypeGlossary(glossary)] : []),
    [glossary],
  );

  return (
    <div className={`msg${role === 'user' ? ' user' : ''}`}>
      <div className={`avatar ${role === 'user' ? 'user' : 'ai'}`}>
        {role === 'user' ? '👤' : '📚'}
      </div>
      <div className="bubble">
        {typing && content === '' ? (
          <div className="typing">
            <span />
            <span />
            <span />
          </div>
        ) : role === 'user' ? (
          <>{content}</>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={rehypePlugins}>
            {content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}

// Мемо по role+content: «спокойные» пузыри не ререндерятся за весь стрим,
// нагрузка остаётся на последнем.
export const Bubble = memo(BubbleInner);
