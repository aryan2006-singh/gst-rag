import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/query": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/variants": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
