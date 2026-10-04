// Bounded public-source context selection; this is not the app's full-chat hook.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const plugin = path.join(process.env.USERPROFILE, '.codex/plugins/cache/personal/fast-jev-codex/0.1.0+codex.20260923103804');
const { compact, JevClient } = await import(pathToFileURL(path.join(plugin, 'vendor/fast-jev-core/dist/index.js')).href);
const chunks = JSON.parse(await readFile(path.join(root, 'planning/research/public-asset-sources-20260930.json'), 'utf8'));
const messages = [{ role: 'user', text: 'Select public source context for LOD, texture and asset visual review. Keep provenance and evidence limits.', toolUses: [] }];
for (const [index, chunk] of chunks.entries()) {
  const id = `public-source-${index}`;
  messages.push({ role: 'assistant', text: '', toolUses: [{ tool_use_id: id, tool: 'read_public_source', input: { url: chunk.url } }] });
  messages.push({ role: 'user', text: '', toolUses: [], toolResults: [{ tool_use_id: id, text: chunk.content }] });
}
messages.push({ role: 'user', text: 'Next: compare screen coverage LOD, foliage overdraw, compression and multi-angle QA. Preserve primary-source attribution. Do not authorize writes or purchases.', toolUses: [] });
const usage = [];
const client = new JevClient({ fetch: (url, options) => fetch(url, { ...options, redirect: 'error', signal: AbortSignal.timeout(20000) }) });
const asker = { ask: async (state, questions) => {
  const result = await client.ask(state, questions);
  usage.push({ model: result.model ?? null, usage: result.usage ?? null });
  return result;
} };
const directory = path.join(root, '.harness/.cache/jev');
await mkdir(directory, { recursive: true });
try {
  const result = await compact(messages, asker, { preserveRecentMessages: 1,
    maxStateTokens: 3000, maxRequestTokens: 5000, truncateHeadChars: 120 });
  await writeFile(path.join(directory, 'nature-public-selected.json'), JSON.stringify(result.messages, null, 2) + '\n');
  const receipt = { status: 'PASS', scope: 'Five bounded public source summaries only; no private project files, chat transcript or credentials in the request.',
    full_chat_compaction_hook_verified: false, cache_affinity: 'UNAVAILABLE', billed_savings: 'NOT_MEASURED',
    stats: result.stats, decisions: result.decisions, provider_reports: usage,
    selected_context: '.harness/.cache/jev/nature-public-selected.json' };
  await writeFile(path.join(root, 'planning/evidence/jev-public-asset-context-20260930.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({ status: receipt.status, requests: result.stats.requests, chars_before: result.stats.charsBefore,
    chars_after: result.stats.charsAfter, provider_reports: usage, billed_savings: receipt.billed_savings }));
} catch (error) {
  // Never include transport bodies or credentials in diagnostic output.
  await writeFile(path.join(root, 'planning/evidence/jev-public-asset-context-20260930.json'), JSON.stringify({
    status: 'UNAVAILABLE', scope: 'Bounded public-source compaction', automatic_retry: false,
    full_chat_compaction_hook_verified: false, cache_affinity: 'UNAVAILABLE', diagnostic: error.name }, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'UNAVAILABLE', diagnostic: error.name, fallback: 'Local source records retained.' }));
}
