/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Legacy CBI tokens (preserved for backward-compat)
        cbi: {
          primary: "#176FC1",
          "primary-dark": "#125A9C",
          "primary-light": "#E8F1FA",
          accent: "#CE0F3E",
          "accent-dark": "#A60C32",
          surface: "#F4F6F8",
          text: "#1A2330",
        },
        // SOC professional light palette — shared with web-app Heritage Trust Bank tokens
        soc: {
          bg: "#F2F5F8",
          surface: "#FFFFFF",
          elevated: "#F8FAFB",
          border: "#E2E8F0",
          text: "#1A2330",
          muted: "#64748B",
          primary: "#176FC1",
          "primary-light": "#E8F1FA",
          accent: "#CE0F3E",
          "accent-light": "#FDEEF2",
          success: "#15803D",
          "success-light": "#DCFCE7",
          warning: "#B45309",
          "warning-light": "#FEF3C7",
          danger: "#DC2626",
          "danger-light": "#FEE2E2",
          critical: "#9F1239",
          "critical-light": "#FFE4E6",
        },
        // Risk band semantic colors (light theme)
        band: {
          low: "#15803D",
          "low-bg": "#DCFCE7",
          medium: "#B45309",
          "medium-bg": "#FEF3C7",
          high: "#DC2626",
          "high-bg": "#FEE2E2",
          "very-high": "#9F1239",
          "very-high-bg": "#FFE4E6",
        },
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
