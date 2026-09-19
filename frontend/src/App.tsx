import { useStore } from './state/store';
import { useUi } from './state/ui';
import { Sidebar } from './components/Sidebar/Sidebar';
import { MessageList } from './components/Chat/MessageList';
import { Composer } from './components/Chat/Composer';
import { ComposerDraftProvider } from './components/Chat/ComposerDraftContext';
import { ModelSelect } from './components/Chat/ModelSelect';
import { ReaderView } from './components/Reader/ReaderView';
import { TooltipController } from './components/Glossary/Tooltip';

export default function App() {
  const { state } = useStore();
  const ui = useUi();
  const { mode, modes, chapter, chapterId } = state;
  const info = modes[mode];

  return (
    <>
      <TooltipController />
      <div
        className={`overlay${ui.mobileSidebarOpen ? ' show' : ''}`}
        onClick={ui.closeMobileSidebar}
      />
      <Sidebar />
      <div className="main">
        <div className="chat-header">
          <button
            type="button"
            className="sidebar-toggle"
            title="Свернуть оглавление"
            onClick={ui.toggleDesktopSidebar}
          >
            {ui.desktopSidebarCollapsed ? '▶' : '◀'}
          </button>
          <button
            type="button"
            className="hamburger"
            aria-label="Оглавление"
            onClick={ui.openMobileSidebar}
          >
            ☰
          </button>
          <span className="header-topic">
            {mode === 'search'
              ? 'Поиск по библиотеке'
              : chapterId && chapter
                ? `${chapter.title}`
                : 'Выбери главу →'}
          </span>
          {mode !== 'read' && <ModelSelect />}
          <span className={`mode-badge badge-${mode}`}>
            {mode === 'read' ? 'Чтение' : (info?.title ?? mode)}
          </span>
        </div>

        {mode === 'read' ? (
          <ReaderView />
        ) : (
          <ComposerDraftProvider>
            <MessageList />
            <Composer />
          </ComposerDraftProvider>
        )}
      </div>
    </>
  );
}
