import { visit } from 'unist-util-visit';
import type { Root, Element, Text, ElementContent } from 'hast';

export interface GlossaryConfig {
  regex: RegExp;
  // Возвращает definition или null для term.
  lookup: (term: string) => string | null;
}

// Оборачивает каждое вхождение терминов из глоссария в
// <span class="gloss-term" data-tooltip="..."> внутри text-узлов.
// Пропускает <code>, <pre>, <a> и уже обёрнутые .gloss-term.
export function rehypeGlossary(config: GlossaryConfig | null) {
  return function transformer(tree: Root) {
    if (!config) return;
    const { regex, lookup } = config;

    visit(tree, 'text', (node: Text, index, parent) => {
      if (!parent || index === undefined) return;
      // Пропускаем child'ов code/pre/a и уже обёрнутых терминов.
      const parentEl = parent as Element;
      if (parentEl.type === 'element') {
        const tag = parentEl.tagName;
        if (tag === 'code' || tag === 'pre' || tag === 'a') return;
        const classes = (parentEl.properties?.className as string[] | undefined) ?? [];
        if (classes.includes('gloss-term')) return;
      }

      const text = node.value;
      // Глобальный regex — сбрасываем lastIndex перед каждым прогоном.
      regex.lastIndex = 0;
      if (!regex.test(text)) return;
      regex.lastIndex = 0;

      const out: ElementContent[] = [];
      let last = 0;
      let m: RegExpExecArray | null;
      while ((m = regex.exec(text))) {
        if (m.index > last) {
          out.push({ type: 'text', value: text.slice(last, m.index) } as Text);
        }
        const def = lookup(m[0]);
        const span: Element = {
          type: 'element',
          tagName: 'span',
          properties: {
            className: ['gloss-term'],
            ...(def ? { 'data-tooltip': def } : {}),
          },
          children: [{ type: 'text', value: m[0] } as Text],
        };
        out.push(span);
        last = m.index + m[0].length;
      }
      if (last < text.length) {
        out.push({ type: 'text', value: text.slice(last) } as Text);
      }

      const parentChildren = parentEl.children;
      parentChildren.splice(index, 1, ...out);
      // visit вернёт следующий не-замещённый индекс автоматически
      return index + out.length;
    });
  };
}

// Сборка regex по словарю. \b ломается на кириллице — используем
// negative lookbehind/lookahead по символам слова с кириллицей.
export function buildGlossaryConfig(glossary: Record<string, string>): GlossaryConfig {
  const terms = Object.keys(glossary).sort((a, b) => b.length - a.length);
  const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern =
    '(?<![\\wа-яёА-ЯЁ])(' + terms.map(escape).join('|') + ')(?![\\wа-яёА-ЯЁ])';
  const regex = new RegExp(pattern, 'g');
  const lower = new Map<string, string>();
  for (const [k, v] of Object.entries(glossary)) lower.set(k.toLowerCase(), v);
  const lookup = (term: string): string | null => {
    if (glossary[term]) return glossary[term];
    return lower.get(term.toLowerCase()) ?? null;
  };
  return { regex, lookup };
}
