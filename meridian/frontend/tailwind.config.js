/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "var(--base)",
        panel: "var(--panel)",
        elevated: "var(--elevated)",
        hairline: "var(--hairline)",
        up: "var(--up)",
        down: "var(--down)",
        accent: "var(--accent)",
        genie: "var(--genie)",
        warn: "var(--warn)",
        fg: "var(--fg)",
        "fg-2": "var(--fg-2)",
        "fg-3": "var(--fg-3)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
