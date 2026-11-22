import { defineConfig } from 'vitest/config';

// Unit tests for the browser interface (docs/engine-plan.md §8.1, "Frontend" layer).
export default defineConfig({
  oxc: { jsx: { runtime: 'automatic', importSource: 'preact' } },
  test: {
    include: ['tests/interfaces/**/*.test.ts'],
    environment: 'node',
  },
});
