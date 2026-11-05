import { request } from "http";

export default [
  {
    files: ['dist/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals:{
        $: 'readonly',
        document: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        window: 'readonly',
        localStorage: 'readonly',
        URLSearchParams: 'readonly',
        Notification: 'readonly',
        gettext: 'readonly',
        navigator: 'readonly',
        NProgress: 'readonly',
        htmx:'readonly',
        interpolate: 'readonly',
        PaystackPop:'readonly',
        WebSocket:'readonly',
        history:'readonly',
        fetch: 'readonly',
        URL: 'readonly',
        Image: 'readonly',
        File: 'readonly',
        DataTransfer:'readonly',
        FormData: 'readonly',
        requestAnimationFrame: 'readonly'
      }
    },

    rules: {
      'no-unused-vars': 'warn',
      'no-undef': 'warn',
      'no-console': 'warn',
      'no-cond-assign': 'error',
      'no-unreachable': 'error',
      camelcase: 'warn',
      curly: 'error',
      quotes: ['error', 'single'],
    },
  },
];
