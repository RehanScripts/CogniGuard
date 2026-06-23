/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cbi: {
          primary: "#176FC1",
          "primary-dark": "#125A9C",
          "primary-light": "#E8F1FA",
          accent: "#CE0F3E",
          "accent-dark": "#A60C32",
          surface: "#F4F6F8",
          text: "#1A2330",
        },
      },
      fontFamily: {
        sans: ["Inter", "Public Sans", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
