import { defineConfig } from 'vitest/config'

export default defineConfig({
  // Component tests are .tsx; the automatic runtime keeps them free of
  // `import React` boilerplate, matching the app's Next.js setup.
  esbuild: { jsx: 'automatic' },
  test: {
    // Node environment stays the default for pure-module tests; component
    // tests opt into jsdom with a `// @vitest-environment jsdom` docblock.
    environment: 'node',
    include: ['__tests__/**/*.test.{ts,tsx}'],
  },
})
