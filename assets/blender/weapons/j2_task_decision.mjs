// Bounded generic planning input only; no private files, images, paths or transcript sent.
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { writeFile } from 'node:fs/promises';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const receipt = path.join(root, 'planning/evidence/hero-weapons-20261002/j2-jev-decision.json');
const started = performance.now();
let result;
try {
  const plugin = path.join(process.env.USERPROFILE, '.codex/plugins/cache/personal/fast-jev-codex/0.1.0+codex.20260923103804/vendor/fast-jev-core/dist/index.js');
  const { JevClient } = await import(pathToFileURL(plugin).href);
  const client = new JevClient({ fetch: (url, options) => fetch(url, { ...options, redirect: 'error', signal: AbortSignal.timeout(20000) }) });
  const response = await client.ask({ task: 'Add named effect attachment nodes to three already-validated weapons; retain geometry, materials, textures and earlier revisions. One weapon has rest and drawn string poses.' }, {
    route: { type: 'choice', instructions: 'Choose the most focused repair route for this metadata-only asset change.', criteria: {
      reuse_validated_sources: 'Update named nodes on immutable validated sources, re-export and verify ownership and both string poses.',
      regenerate_art: 'Regenerate all geometry and textures even though no visual change was requested.',
    } },
  });
  if (!['reuse_validated_sources', 'regenerate_art'].includes(response.answers?.route?.choice)) throw new Error('InvalidChoice');
  result = { status: 'USED_VERIFIED', model: response.model, usage: response.usage, answers: response.answers,
    scope: 'Generic asset-repair description only; no private project data.', savings: 'NOT_MEASURED', full_chat_compaction: 'UNVERIFIED' };
} catch (error) {
  result = { status: 'UNAVAILABLE', diagnostic: error.name, fallback: 'Deterministic versioned node update and export validation; no automatic retry.' };
}
result.elapsed_ms = Math.round(performance.now() - started);
await writeFile(receipt, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ status: result.status, usage: result.usage, elapsed_ms: result.elapsed_ms }));
