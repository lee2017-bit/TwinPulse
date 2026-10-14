// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react(), {
    name: 'twinpulse-build-manifest',
    enforce: 'post',
    async generateBundle(_options, bundle) {
      const files = Object.fromEntries(await Promise.all(Object.entries(bundle).map(async ([name, item]) => {
        const source = item.type === 'chunk' ? item.code : item.source;
        const bytes = typeof source === 'string' ? new TextEncoder().encode(source) : Uint8Array.from(source);
        const digest = await crypto.subtle.digest('SHA-256', bytes);
        return [name, Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2,'0')).join('')];
      })));
      this.emitFile({type:'asset', fileName:'twinpulse-build-manifest.json',
        source:JSON.stringify({schema_version:'1.0',files})});
    },
  }],
  build: { target: "es2022", sourcemap: false },
  // Node-only acceptance/ownership drivers use node --test separately.
  test: { environment: "jsdom", setupFiles: "./src/test-setup.ts", include: ["src/**/*.{test,spec}.{ts,tsx}"] },
});
