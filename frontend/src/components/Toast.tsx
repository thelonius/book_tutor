import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

interface ToastContextValue {
  show: (text: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [text, setText] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);

  const show = useCallback((t: string) => {
    setText(t);
    setVisible(true);
  }, []);

  useEffect(() => {
    if (!visible) return;
    const id = window.setTimeout(() => setVisible(false), 2200);
    return () => window.clearTimeout(id);
  }, [visible, text]);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div
        id="share-toast"
        style={{
          position: 'fixed',
          bottom: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          padding: '10px 18px',
          borderRadius: 8,
          background: '#1f2937',
          color: '#fff',
          fontSize: 14,
          zIndex: 1000,
          opacity: visible ? 1 : 0,
          transition: 'opacity 0.2s',
          pointerEvents: 'none',
        }}
      >
        {text ?? ''}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
