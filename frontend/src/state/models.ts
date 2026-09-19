// Цепочка синхронизирована с MODELS в llm.py. Расхождение безопасно —
// бэкенд стартует с первой живой, если выбранной в списке нет, — но
// селект тогда врёт про то, что реально отвечает.
export const MODELS = [
  { id: 'glm-4.7-flash', label: 'GLM 4.7 Flash' },
  { id: 'glm-4.5-flash', label: 'GLM 4.5 Flash' },
  { id: 'nvidia/nemotron-3-super-120b-a12b:free', label: 'Nemotron 3 Super' },
  { id: 'z-ai/glm-5.2:free', label: 'GLM 5.2' },
  { id: 'google/gemma-4-31b-it:free', label: 'Gemma 4 31B' },
] as const;

export const DEFAULT_MODEL = MODELS[0].id;

export function isKnownModel(id: string): boolean {
  return MODELS.some((m) => m.id === id);
}
