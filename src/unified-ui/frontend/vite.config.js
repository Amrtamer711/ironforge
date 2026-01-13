import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react()
  ],
  server: {
    port: 5173,
    // Force HMR to work properly
    hmr: {
      overlay: true
    },
    proxy: {
      "/api": {
        target: "http://localhost:3005",
        changeOrigin: true,
        secure: false
      }
    }
  },
  // Clear output directory on build
  build: {
    emptyOutDir: true
  }
});
