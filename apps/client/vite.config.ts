import { defineConfig } from "vite";
import { svelte, vitePreprocess } from "@sveltejs/vite-plugin-svelte";

const websocketProxyTarget = process.env.AETHERFIELD_WS_PROXY_TARGET ?? "ws://127.0.0.1:3001";

export default defineConfig({
	plugins: [svelte({ preprocess: vitePreprocess(), compilerOptions: { runes: true } })],
	server: {
		host: "127.0.0.1",
		port: 5173,
		strictPort: true,
			proxy: {
				"/session": "http://127.0.0.1:3001",
				"/auth": "http://127.0.0.1:3001",
			"/rooms": "http://127.0.0.1:3001",
			"/tower": "http://127.0.0.1:3001",
			"/friends": "http://127.0.0.1:3001",
			"/group": "http://127.0.0.1:3001",
			"/presence": "http://127.0.0.1:3001",
				"/ws": {
					target: websocketProxyTarget,
					ws: true,
				},
				"/healthz": "http://127.0.0.1:3001",
			},
	},
});
