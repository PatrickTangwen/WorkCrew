import { mergeConfig } from "vitest/config"

import viteConfig from "./vite.config.ts"

export default mergeConfig(viteConfig, {
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
})
