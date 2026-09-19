import { useEffect, useRef, useState } from 'react';

// Универсальный тултип-контроллер: hover на десктопе, tap-to-pin на тач.
// Слушаем document-level события и реагируем на любые .gloss-term[data-tooltip].
// Аналог setupTooltip из legacy app.js.
export function TooltipController() {
  const [text, setText] = useState<string | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number }>({ left: 0, top: 0 });
  const isTouch = useRef<boolean>(false);
  const pinnedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    isTouch.current = window.matchMedia('(hover: none)').matches;
  }, []);

  useEffect(() => {
    const showFor = (el: HTMLElement) => {
      const t = el.dataset.tooltip;
      if (!t) return;
      const rect = el.getBoundingClientRect();
      // Центрируем по горизонтали, на 8px ниже элемента; обрезаем по краям окна.
      const tooltipWidth = 320;
      const left = Math.max(
        8,
        Math.min(rect.left + rect.width / 2 - tooltipWidth / 2, window.innerWidth - tooltipWidth - 8),
      );
      setPos({ left, top: rect.bottom + 8 });
      setText(t);
    };
    const hide = () => {
      setText(null);
      pinnedRef.current = null;
    };

    const onMouseOver = (e: MouseEvent) => {
      if (isTouch.current) return;
      const el = (e.target as HTMLElement)?.closest?.('.gloss-term') as HTMLElement | null;
      if (el) showFor(el);
    };
    const onMouseOut = (e: MouseEvent) => {
      if (isTouch.current) return;
      const el = (e.target as HTMLElement)?.closest?.('.gloss-term');
      const next = (e.relatedTarget as HTMLElement | null)?.closest?.('.gloss-term');
      if (el && el !== next) hide();
    };
    const onClick = (e: MouseEvent) => {
      const el = (e.target as HTMLElement)?.closest?.('.gloss-term') as HTMLElement | null;
      if (!el) {
        if (pinnedRef.current) hide();
        return;
      }
      // Click-to-pin/unpin. На тач это единственный режим.
      if (pinnedRef.current === el) {
        hide();
      } else {
        pinnedRef.current = el;
        showFor(el);
      }
    };
    const onScroll = () => {
      if (pinnedRef.current) {
        showFor(pinnedRef.current);
      } else {
        setText(null);
      }
    };

    document.addEventListener('mouseover', onMouseOver);
    document.addEventListener('mouseout', onMouseOut);
    document.addEventListener('click', onClick);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('mouseover', onMouseOver);
      document.removeEventListener('mouseout', onMouseOut);
      document.removeEventListener('click', onClick);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, []);

  if (!text) return null;
  return (
    <div
      id="tooltip"
      style={{
        position: 'fixed',
        left: pos.left,
        top: pos.top,
        maxWidth: 320,
        padding: '8px 12px',
        background: '#1f2937',
        color: '#e5e7eb',
        border: '1px solid #374151',
        borderRadius: 6,
        fontSize: 13,
        lineHeight: 1.45,
        zIndex: 999,
        pointerEvents: 'none',
        boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
      }}
    >
      {text}
    </div>
  );
}
