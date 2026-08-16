import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        zinc: {
          900: "#18181B",
          950: "#09090B",
        },
        orange: {
          500: "#FF6B00",
          600: "#E05E00",
        },
        canvas: "#09090B",
        panel: "#18181B",
        primary: "#FF6B00",
      },
      borderColor: {
        panel: "rgba(39, 39, 42, 0.8)",
      },
      boxShadow: {
        "orange-glow": "0 0 20px rgba(255, 107, 0, 0.25)",
      },
    },
  },
  plugins: [],
};
export default config;