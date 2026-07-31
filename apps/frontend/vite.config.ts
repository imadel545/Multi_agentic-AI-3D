import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        strictExecutionOrder: true,
        codeSplitting: {
          groups: [
            {
              name: "three-runtime",
              test: /node_modules[\\/](@react-three|three|camera-controls|maath|troika|zustand)/,
              minSize: 25 * 1024,
              maxSize: 450 * 1024,
              priority: 20
            }
          ]
        }
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: Object.fromEntries(
      ["/health", "/studio", "/assets", "/document-packs", "/requirements", "/designs"].map(
        (path) => [
          path,
          {
            target: "http://127.0.0.1:8000",
            changeOrigin: false
          }
        ]
      )
    )
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true
  }
});
