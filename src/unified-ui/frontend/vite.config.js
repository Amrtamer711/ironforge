import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      injectRegister: null,
      registerType: "autoUpdate",
      devOptions: {
        enabled: false,  // CRITICAL: Disable PWA in dev to avoid cache issues
        suppressWarnings: true
      },
      workbox: {
        skipWaiting: true,           // New SW takes over immediately
        clientsClaim: true,          // Claim all clients right away
        cleanupOutdatedCaches: true, // Remove old caches
        // Don't cache API requests in production
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            // Cache images but with network-first strategy
            urlPattern: /\.(?:png|jpg|jpeg|gif|webp|svg)$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'images',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 24 * 60 * 60 // 24 hours
              }
            }
          }
        ]
      },
      manifest: {
        name: "MMG Nova",
        short_name: "MMG Nova",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: "#ffffff",
        theme_color: "#1C1C1E",
        icons: [
          { src: "/pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "/pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "/pwa-512x512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" }
        ]
      }
    })
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
