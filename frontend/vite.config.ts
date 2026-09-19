import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  // Flask отдаёт сборку из static/dist и туда же указывает SPA-роут.
  base: '/static/dist/',
  build: {
    outDir: path.resolve(__dirname, '../static/dist'),
    emptyOutDir: true,
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          // react-markdown тянет за собой micromark/mdast/hast/unist —
          // это отдельный чанк, он нужен только на чат-пути, а чтение
          // главы обходится без него.
          if (
            id.includes('react-markdown') ||
            /node_modules\/(remark-|rehype-|mdast-|hast-|unist-|micromark|trim-lines|space-separated-tokens|comma-separated-tokens|property-information|zwitch|ccount|escape-string-regexp|character-entities|decode-named-character-reference|html-url-attributes|devlop|estree-util|html-void-elements|vfile|bail|is-plain-obj|trough|unified|fault)/.test(
              id,
            )
          ) {
            return 'markdown';
          }
          if (id.includes('react-dom')) return 'react-dom';
          if (/node_modules\/(react|scheduler)\//.test(id)) return 'react';
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5175,
    strictPort: true,
    // Dev: vite на 5175, Flask на 5003 (см. .claude/launch.json).
    proxy: { '/api': 'http://127.0.0.1:5003' },
  },
});
