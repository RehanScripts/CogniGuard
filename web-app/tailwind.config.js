/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Legacy CBI tokens -- kept so any class we don't touch in this pass
        // keeps rendering instead of falling back to unstyled black/white.
        cbi: {
          primary: "#176FC1",
          "primary-dark": "#125A9C",
          "primary-light": "#E8F1FA",
          accent: "#CE0F3E",
          "accent-dark": "#A60C32",
          surface: "#F4F6F8",
          text: "#1A2330",
        },
        // Central Bank of India design system (from the Stitch/AI-Studio export in
        // central-bank-of-india/src/index.css) -- flat keys so Stitch's own
        // className strings (bg-primary, text-on-surface-variant, ...) work verbatim.
        primary: "#00569c",
        "primary-container": "#176fc1",
        "on-primary": "#ffffff",
        "on-primary-container": "#ebf1ff",
        secondary: "#ba0035",
        "secondary-container": "#e02349",
        "on-secondary": "#ffffff",
        "background-custom": "#f8f9fb",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#f2f4f6",
        "surface-container": "#eceef0",
        "surface-container-high": "#e6e8ea",
        "surface-container-highest": "#e0e3e5",
        "on-surface": "#191c1e",
        "on-surface-variant": "#414751",
        outline: "#717783",
        "outline-variant": "#c1c7d3",
        "error-custom": "#ba1a1a",
        "success-custom": "#15803d",
        "primary-fixed": "#d4e3ff",
        "secondary-fixed": "#ffdada",
        "tertiary-fixed": "#d4e3ff",
      },
      fontFamily: {
        sans: ["Inter", "Public Sans", "system-ui", "sans-serif"],
        headline: ["Hanken Grotesk", "Inter", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
