# Frozen native city review

This tool builds the current client once into an isolated cache directory, then serves that fixed output locally. Concurrent source edits cannot trigger HMR or silently replace a walking review's JavaScript/GLB files. It is a local QA tool, not deployment or a production server.

Prepared only: wait for the parent task's explicit **GO** before building.

```powershell
node tools/native-city-review.mjs plan
node tools/native-city-review.mjs build --go --id baseline-v1
node tools/native-city-review.mjs verify --id baseline-v1
node tools/native-city-review.mjs serve --id baseline-v1 --port 4173
```

For a fresh isolated backend started separately by the parent:

```powershell
node tools/native-city-review.mjs build --go --id baseline-v1 --server-origin http://127.0.0.1:3917
node tools/native-city-review.mjs serve --id baseline-v1 --port 4173
```

`--server-origin` rewrites every copied HTTP proxy target to the given local origin and derives the equivalent WS/WSS target for `/ws`. Proxy route keys and other options are preserved. The override is recorded in the build receipt and reused when serving; an explicit serve-time override gets a separate start receipt tied to the same frozen output digest. Without the option, the original configuration remains on port 3001.

Use a new ID for every rebuild. The tool refuses to overwrite an existing receipt or nonempty output directory. It never deletes a previous review and never writes `apps/client/dist` or product source/configuration. The default output is `.harness/.cache/city-native-review/baseline-v1`, with its receipt beside it. It verifies resolved path containment and rejects symlink output directories.

It uses the installed Vite 8 JavaScript API and the original `apps/client/vite.config.ts`, loaded with the native module runner to avoid temporary bundled config writes in product directories. Inline build overrides retain the authored DEV QA controls (`import.meta.env.DEV=true`, `PROD=false`) and redirect output/cache paths. Public fixtures and the content bundle are copied into the frozen build. Existing generated codec files must already be current; this tool intentionally does not run product prebuild scripts that write source files.

The source inventory is hashed before and after the build, and the bundler's project input read-set is checked again afterward. Concurrent writes make the build unsealed and unservable. Receipts record dependency versions, Node version, source hash roster, actual input hash roster, emitted output hash roster, and explicit JavaScript/GLB lists. An unchanged output roster is required before serving. Original source files may change after the sealed build: that is the point of the frozen review.

The preview binds only `127.0.0.1`, defaults to port 4173 and uses strict port selection. Original HTTP/auth/session/WebSocket proxy rules are captured from `server.proxy` and copied into `preview.proxy`. Only credential-free localhost proxy targets are accepted. The tool does not perform game HTTP interactions; use the approved browser tooling for login, walking and captures. Ctrl+C closes the preview server through Vite's `close()` API.

The backend process and its authoritative content state are **not** frozen. Record the matching server/content identity separately when reviewing movement. Deliberately included DEV controls make this build unsuitable for production publication. Output hashes establish byte identity, not visual quality, gameplay correctness or performance.

API sources: [Vite JavaScript API](https://vite.dev/guide/api-javascript.html), [preview options](https://vite.dev/config/preview-options.html), and installed Vite 8.3.0 declarations. Context7 documentation was resolved and queried before implementation.
