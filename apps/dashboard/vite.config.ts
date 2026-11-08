import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const fromHere = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Use the shared contract source directly so typecheck, test and build do
      // not depend on packages/contracts being built first.
      "@hawlak/contracts": fromHere("../../packages/contracts/src/index.ts"),
      "@fixtures": fromHere("../../fixtures"),
    },
  },
  server: {
    // The API only accepts the exact DASHBOARD_ORIGIN (http://localhost:5173).
    host: "localhost",
    port: 5173,
    strictPort: true,
  },
  preview: {
    host: "localhost",
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
