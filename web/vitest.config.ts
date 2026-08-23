import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    // Node environment is enough: the tests cover pure modules, not components.
    environment: 'node',
    include: ['__tests__/**/*.test.ts'],
  },
})
