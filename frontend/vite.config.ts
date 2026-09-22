import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    proxy: {
      // OPS-03 (analys_and_todo.md): настраиваемо через env, чтобы E2E (playwright.config.ts)
      // могли указать на отдельный backend на нестандартном порту, не конфликтуя с портом
      // 8000, который в деве обычно уже занят основным backend-контейнером.
      "/api": process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
    },
  },
});
