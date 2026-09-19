import { createContext, useContext, type ReactNode } from 'react';
import { useTts } from '../hooks/useTts';

type TtsApi = ReturnType<typeof useTts>;

const TtsContext = createContext<TtsApi | null>(null);

// Один useTts-инстанс на всё приложение: per-bubble TTS-кнопки и
// LectureView'шный auto-chain делят одно аудио — клик на одной кнопке
// гасит другое (правильное поведение, в legacy так же через глобальный
// ttsAudio/ttsBtn).
export function TtsProvider({ children }: { children: ReactNode }) {
  const tts = useTts();
  return <TtsContext.Provider value={tts}>{children}</TtsContext.Provider>;
}

export function useSharedTts(): TtsApi {
  const ctx = useContext(TtsContext);
  if (!ctx) throw new Error('useSharedTts must be used inside <TtsProvider>');
  return ctx;
}
