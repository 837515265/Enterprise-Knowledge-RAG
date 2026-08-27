import path from "node:path"
import { defineConfig, loadEnv, UserConfig } from "vite"
import type { ConfigEnv } from "vite"
import createVitePlugins from "./build/createVitePlugin"
import wrapperEnv from "./build/utils/wrapperEnv"
import { optimizeDepsIncludes, optimizeDepsExcludes } from "./build/optimizeDeps"

export default defineConfig(({ mode }: ConfigEnv): UserConfig => {
  const root = process.cwd()

  // wrapperEnv-处理env转为正确的类型
  const env = wrapperEnv(loadEnv(mode, root))

  const isDev = mode === "development"

  return {
    base: env.VITE_BASE_PATH,
    server: {
      host: true,
      port: env.VITE_SERVER_PORT,
      strictPort: true,
      proxy: {
        // 本地开发：将 /knowledge/api-knowledge 代理到本地 knowledge 服务，剥掉网关前缀
        "/knowledge/api-knowledge": {
          target: "http://localhost:20748",
          ws: false,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/knowledge\/api-knowledge/, "")
        },
        "/knowledge/api-user": {
          target: env.VITE_PROXY_URL,
          ws: false,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/knowledge\//, "")
        },
        // 代理所有以 /api-xxx 或 /xxx/api-xxx 开头的请求（可带一级前缀），转发到 VITE_PROXY_URL
        "^(/[^/]+)?/api-": {
          target: env.VITE_PROXY_URL,
          ws: false,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/knowledge\//, "")
        }
      }
    },
    resolve: {
      alias: {
        "@": `${path.resolve(__dirname, "src")}`,
        "#": `${path.resolve(__dirname, "types")}`,
        // 替换依赖内部使用的lodash依赖为lodash-es, 减小打包体积
        lodash: "lodash-es"
      }
    },
    // ...其他配置
    define: {
      "process.env": {}
    },
    // ant-design-vue@1.x 的 ESM Upload 与 Dragger 互相 import。
    // 生产构建分包后会在 Upload 初始化时访问尚未初始化的 Dragger，导致 TDZ 报错。
    // 页面只需要独立的 AUpload / AUploadDragger 组件，不依赖 Upload.Dragger 静态属性。
    plugins: [
      ...createVitePlugins(env),
      {
        name: "fix-antdv-upload-dragger-cycle",
        enforce: "pre",
        transform(code, id) {
          if (!id.endsWith("ant-design-vue/es/upload/Upload.js")) return null
          return code
            .replace("import Dragger from './Dragger';\n", "")
            .replace("  Dragger: Dragger,\n", "")
        }
      }
    ],
    optimizeDeps: {
      include: optimizeDepsIncludes,
      exclude: optimizeDepsExcludes
    },
    build: {
      minify: true,
      target: "es2015" // 或 "esnext"、"modules" 等
    },
    // 生产环境打包去除console和debugger
    esbuild: {
      pure: isDev ? [] : ["console.log"],
      drop: isDev ? [] : ["debugger"]
    },
    css: {
      preprocessorOptions: {
        less: {
          javascriptEnabled: true
        }
      }
    }
  }
})
