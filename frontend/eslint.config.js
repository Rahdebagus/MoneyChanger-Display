import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'public/sw.js']),
  { files: ['tests/**/*.js'], languageOptions: { globals: globals.node } },
  { files: ['scripts/**/*.mjs'], extends: [js.configs.recommended], languageOptions: { globals: globals.node } },
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // Reported as a warning rather than an error.
      //
      // This React Compiler rule flags the ordinary "fetch on mount and show a
      // spinner" pattern: an effect that calls a loader which sets a loading
      // flag synchronously. React's own documentation sanctions effects for
      // data fetching when no framework-level loader is in use, and the rule
      // is about avoiding cascading renders, not about a correctness bug.
      //
      // Rewriting the admin pages around Suspense or an external store to
      // satisfy it would be a large architectural change with real regression
      // risk and no behavioural benefit here, so the signal is kept visible as
      // a warning instead of being switched off.
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
])
