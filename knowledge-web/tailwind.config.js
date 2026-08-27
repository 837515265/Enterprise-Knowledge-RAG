/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class", // or 'media'
  content: ["./index.html", "./src/**/*.{vue,ts,js,jsx,tsx}"],
  theme: {
    extend: {
      backgroundColor: {
        primary: {
          DEFAULT: "var(--primary-color)", // 这样 text-primary 依然可用
          100: "var(--primary-color-100)",
          200: "var(--primary-color-200)",
          300: "var(--primary-color-300)",
          400: "var(--primary-color-400)",
          500: "var(--primary-color-500)",
          600: "var(--primary-color-600)",
          700: "var(--primary-color-700)",
          800: "var(--primary-color-800)",
          900: "var(--primary-color-900)"
        }
      },
      textColor: {
        primary: {
          DEFAULT: "var(--primary-color)", // 这样 text-primary 依然可用
          100: "var(--primary-color-100)",
          200: "var(--primary-color-200)",
          300: "var(--primary-color-300)",
          400: "var(--primary-color-400)",
          500: "var(--primary-color-500)",
          600: "var(--primary-color-600)",
          700: "var(--primary-color-700)",
          800: "var(--primary-color-800)",
          900: "var(--primary-color-900)"
        }
      }
    }
  },
  plugins: []
}
