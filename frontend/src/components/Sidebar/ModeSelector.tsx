import { useStore } from '../../state/store';
import { loadHistory } from '../../state/persistence';
import type { Mode } from '../../types';

// 'read' в MODES бэкенда нет: это не режим модели, а просто текст главы.
// Поэтому подпись и подсказка к нему живут здесь.
const READ: { id: Mode; title: string; emoji: string; hint: string } = {
  id: 'read',
  title: 'Чтение',
  emoji: '📄',
  hint: 'текст главы со сносками и озвучкой',
};

export function ModeSelector() {
  const { state, dispatch } = useStore();
  const { mode, chapterId, modes, modeOrder } = state;

  const list = [
    READ,
    ...modeOrder.filter((id) => modes[id]).map((id) => ({ id, ...modes[id] })),
  ];

  const onClick = (next: Mode) => {
    dispatch({ type: 'SET_MODE', mode: next, messages: loadHistory(chapterId, next) });
  };

  return (
    <div className="mode-section">
      <div className="section-label">Режим</div>
      {list.map((m) => {
        // Разбор, проверка и эпоха привязаны к главе; поиск идёт по всей
        // библиотеке и главы не требует.
        const needsChapter = m.id !== 'search';
        const disabled = needsChapter && chapterId == null;
        return (
          <button
            key={m.id}
            type="button"
            className={`mode-btn${mode === m.id ? ' active' : ''}`}
            disabled={disabled}
            title={disabled ? 'Сначала выбери главу' : m.hint}
            onClick={() => onClick(m.id)}
          >
            <span className="mode-icon">{m.emoji}</span> {m.title}
          </button>
        );
      })}
    </div>
  );
}
