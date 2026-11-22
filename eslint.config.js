// @ts-check
// Lints only the browser interface and its tooling; `npm run lint` passes these paths
// explicitly (aiautonomy/interfaces, tests/interfaces and the root JS/TS config files).
import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// Model-written text arrives in later milestones and must stay plain text
// (docs/engine-plan.md §5.12): these selectors forbid every way of turning a string into markup.
const PLAIN_TEXT_ONLY =
  'Render text with Preact text nodes or textContent (docs/engine-plan.md §5.12).';
const unsafeHtml = [
  {
    selector: 'MemberExpression[property.name=/^(innerHTML|outerHTML)$/]',
    message: PLAIN_TEXT_ONLY,
  },
  {
    selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
    message: PLAIN_TEXT_ONLY,
  },
  {
    selector: "CallExpression[callee.property.name='createContextualFragment']",
    message: PLAIN_TEXT_ONLY,
  },
  {
    selector: "CallExpression[callee.object.name='document'][callee.property.name=/^writeln?$/]",
    message: PLAIN_TEXT_ONLY,
  },
  { selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']", message: PLAIN_TEXT_ONLY },
];

export default defineConfig([
  globalIgnores([
    'dist/',
    'test-results/',
    'playwright-report/',
    'blob-report/',
    'aiautonomy/interfaces/net/protocol.gen.ts',
  ]),
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
      globals: { ...globals.browser },
    },
    rules: {
      'no-restricted-syntax': ['error', ...unsafeHtml],
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
      '@typescript-eslint/no-confusing-void-expression': ['error', { ignoreArrowShorthand: true }],
    },
  },
  {
    files: ['**/*.js', '**/*.mjs'],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: [
      'vite.config.ts',
      'vitest.config.ts',
      'playwright.config.ts',
      'tests/interfaces/e2e/**',
    ],
    languageOptions: { globals: { ...globals.node } },
  },
]);
