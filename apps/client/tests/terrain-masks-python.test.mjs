// Terrain spec §8.4 test 6 inside the client suite: runs tools/terrain/test_terrain_masks.py (Python unittest:
// §3.5 mask validations on fixtures, encodings, border identity, check_terrain_textures.py --self-test).
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const python = process.env.PYTHON_BIN || 'python';
const probe = spawnSync(python, ['-c', 'import numpy, PIL'], { encoding: 'utf8' });

test('terrain mask fixtures and texture checker self-test (Python)', { skip: probe.status !== 0 ? 'python with numpy and PIL unavailable' : false }, () => {
	const run = spawnSync(python, ['-B', 'tools/terrain/test_terrain_masks.py'], { cwd: root, encoding: 'utf8', timeout: 300000 });
	assert.equal(run.status, 0, `${run.stdout}\n${run.stderr}`);
	assert.match(run.stderr, /\nOK\s*$/);
});
