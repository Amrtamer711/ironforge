/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular"],
      },
      boxShadow: {
        // subtle shadows only
        soft: "0 1px 2px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.04)",
        soft2: "0 1px 1px rgba(0,0,0,0.04), 0 12px 32px rgba(0,0,0,0.06)",
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};
