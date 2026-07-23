import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { freecivArtifactPlugin } from "./artifact-server";

export default defineConfig({
  plugins: [react(), freecivArtifactPlugin()],
  server: { port: 4178, strictPort: true, fs: { allow: ["../.."] } },
  preview: { port: 4178, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});
