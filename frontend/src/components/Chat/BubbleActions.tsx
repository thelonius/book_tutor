import { useSharedTts } from '../TtsProvider';

interface Props {
  text: string;
  /** «Дальше» — только на последнем ответе и только в диалоговых режимах. */
  showNext: boolean;
  onNext: () => void;
}

export function BubbleActions({ text, showNext, onNext }: Props) {
  const tts = useSharedTts();

  const ttsLabel =
    tts.state === 'loading'
      ? '✕ Отменить'
      : tts.state === 'playing'
        ? '⏸ Пауза'
        : tts.state === 'paused'
          ? '▶ Продолжить'
          : '🔊 Слушать';
  const ttsCls =
    'tts-btn' +
    (tts.state === 'loading' ? ' tts-loading' : '') +
    (tts.state === 'playing' ? ' tts-playing' : '') +
    (tts.state === 'paused' ? ' tts-paused' : '');

  const onTtsClick = () => {
    // Если уже играем/пауза — просто toggle. Если loading — это уже наш
    // трек, повторный клик отменяет. Если idle — стартуем новый.
    if (tts.state === 'playing' || tts.state === 'paused') {
      tts.toggle();
    } else if (tts.state === 'loading') {
      tts.reset();
    } else {
      void tts.speak(text);
    }
  };

  return (
    <div style={{ marginLeft: 56, marginTop: -4, marginBottom: 16, display: 'flex', gap: 8 }}>
      <button type="button" className={ttsCls} onClick={onTtsClick} title="Прочитать вслух">
        {ttsLabel}
      </button>
      {showNext && (
        <button type="button" className="next-q-btn" onClick={onNext}>
          ➡️ Дальше
        </button>
      )}
    </div>
  );
}
