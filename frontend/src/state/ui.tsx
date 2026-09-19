import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { loadSidebarCollapsed, saveSidebarCollapsed } from './persistence';

interface UiContextValue {
  // Десктоп: схлопывание сайдбара в 0px. Персистится в localStorage.
  desktopSidebarCollapsed: boolean;
  toggleDesktopSidebar: () => void;
  // Мобайл: outside-overlay sidebar (.open). Сбрасывается на каждый
  // выбор темы/режима, не персистится.
  mobileSidebarOpen: boolean;
  openMobileSidebar: () => void;
  closeMobileSidebar: () => void;
}

const UiContext = createContext<UiContextValue | null>(null);

export function UiProvider({ children }: { children: ReactNode }) {
  const [desktopCollapsed, setDesktopCollapsed] = useState<boolean>(loadSidebarCollapsed());
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    saveSidebarCollapsed(desktopCollapsed);
  }, [desktopCollapsed]);

  const toggleDesktopSidebar = useCallback(() => setDesktopCollapsed((v) => !v), []);
  const openMobileSidebar = useCallback(() => setMobileOpen(true), []);
  const closeMobileSidebar = useCallback(() => setMobileOpen(false), []);

  return (
    <UiContext.Provider
      value={{
        desktopSidebarCollapsed: desktopCollapsed,
        toggleDesktopSidebar,
        mobileSidebarOpen: mobileOpen,
        openMobileSidebar,
        closeMobileSidebar,
      }}
    >
      {children}
    </UiContext.Provider>
  );
}

export function useUi(): UiContextValue {
  const ctx = useContext(UiContext);
  if (!ctx) throw new Error('useUi must be used inside <UiProvider>');
  return ctx;
}
