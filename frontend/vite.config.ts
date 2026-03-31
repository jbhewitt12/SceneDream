import fs from "node:fs"
import path from "node:path"
import { TanStackRouterVite } from "@tanstack/router-vite-plugin"
import react from "@vitejs/plugin-react-swc"
import type { Connect } from "vite"
import { defineConfig, loadEnv } from "vite"

// Generated images are served by the backend in local dev via the Vite proxy.
// Only frontend-owned build assets should be short-circuited here.
const STATIC_PATH_PREFIXES = ["/assets/"]

const isStaticAssetRequest = (url: string) => {
  const pathname = new URL(url, "http://localhost").pathname
  return STATIC_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))
}

const createMissingAssetMiddleware = (
  rootDir: string,
  assetRoot: string,
): Connect.NextHandleFunction => {
  return (req, res, next) => {
    const url = req.url
    if (!url || !isStaticAssetRequest(url)) {
      next()
      return
    }

    const pathname = new URL(url, "http://localhost").pathname
    const filePath = path.join(rootDir, assetRoot, pathname)

    if (fs.existsSync(filePath)) {
      next()
      return
    }

    res.statusCode = 404
    res.setHeader("Content-Type", "text/plain")
    res.end("Not Found")
  }
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "")

  return {
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    plugins: [
      react(),
      TanStackRouterVite(),
      {
        name: "missing-static-assets-return-404",
        configureServer(server) {
          server.middlewares.use(
            createMissingAssetMiddleware(server.config.root, "public"),
          )
        },
        configurePreviewServer(server) {
          server.middlewares.use(
            createMissingAssetMiddleware(server.config.root, "dist"),
          )
        },
      },
    ],
    server: {
      proxy: {
        "/api": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
        "/img": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  }
})
