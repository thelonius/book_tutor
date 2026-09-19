import { useStore } from '../../state/store';
import { MODELS } from '../../state/models';

export function ModelSelect() {
  const { state, dispatch } = useStore();
  return (
    <select
      id="model-select"
      title="Модель"
      value={state.preferredModel}
      onChange={(e) => dispatch({ type: 'SET_MODEL', model: e.target.value })}
    >
      {MODELS.map((m) => (
        <option key={m.id} value={m.id}>
          {m.label}
        </option>
      ))}
    </select>
  );
}
