import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const certPath = path.resolve(__dirname, "../data/devcert/nellie-devcert.pem");
const keyPath = path.resolve(__dirname, "../data/devcert/nellie-devcert.key");
const useHttps = process.env.NELLIE_WEB_HTTPS === "1" && fs.existsSync(certPath) && fs.existsSync(keyPath);

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    https: useHttps
      ? {
          cert: fs.readFileSync(certPath),
          key: fs.readFileSync(keyPath),
        }
      : undefined,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8877",
        changeOrigin: true,
      },
      "/stt": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/stt/, ""),
      },
    },
    fs: {
      allow: [".."],
    },
  },
});
