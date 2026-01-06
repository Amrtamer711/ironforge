import js from "@eslint/js";

const ignores = ["dist/**", "Old Code Archive/**", "**/Old Code Archive/**"];

export default [
  { ignores },
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        window: "readonly",
        document: "readonly",
        localStorage: "readonly",
        sessionStorage: "readonly",
        fetch: "readonly",
        Headers: "readonly",
        FormData: "readonly",
        URLSearchParams: "readonly",
        TextDecoder: "readonly",
        FileReader: "readonly",
        Image: "readonly",
        navigator: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        confirm: "readonly",
        URL: "readonly",
        crypto: "readonly",
        CustomEvent: "readonly",
      },
    },
  },
];
