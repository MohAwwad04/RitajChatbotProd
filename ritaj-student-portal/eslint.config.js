// ESLint 9 flat configuration.
//
// `npm run lint` was declared in package.json and wired into the release
// documentation, but no config file existed — so the "lint gate" exited
// non-zero on startup and had never actually checked anything. A gate that
// cannot run is worse than no gate: it appears in the checklist and gets ticked.
//
// Flat config (the default since ESLint 9) replaces .eslintrc: every shared
// config is an array that gets spread, and `languageOptions` carries what
// `env`/`parserOptions` used to.

import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    // Build output and dependencies. Linting `dist` reports on bundler output
    // nobody wrote and would fail on every build.
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Vite's fast refresh only works when a module exports components and
      // nothing else. Warn rather than error: some files legitimately export a
      // hook or a constant alongside, and breaking the build over HMR ergonomics
      // is the wrong trade.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // An unused variable is usually a leftover from a refactor — exactly the
      // kind of thing this project just did a lot of. The underscore prefix is
      // the escape hatch for a deliberately ignored binding.
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],

      // `any` erases the type checking this project relies on at the API
      // boundary, where the streamed event shapes are the contract. Warn so it
      // is visible without blocking work that legitimately needs an escape.
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
  {
    // Config files run in Node, not the browser.
    files: ['*.config.{js,ts}', 'vite.config.ts'],
    languageOptions: { globals: globals.node },
  },
)
