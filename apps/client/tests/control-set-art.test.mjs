import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { controlSpriteGeometry } from '../src/control-art-geometry.mjs';
const directory = new URL('../src/assets/ui/control-sets-r01/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('manifest.json', directory), 'utf8'));
test('all eight vendored atlases retain supplied byte hashes, RGBA, and full 1536x1024 originals', async () => {
	assert.equal(manifest.styles.length, 8);
	for (const style of manifest.styles) {
		const bytes = await readFile(new URL(style.file, directory));
		assert.equal(createHash('sha256').update(bytes).digest('hex'), style.sha256, style.id);
		assert.equal(bytes.readUInt32BE(16), 1536); assert.equal(bytes.readUInt32BE(20), 1024); assert.equal(bytes[25], 6);
		for (const part of Object.values(style.components)) {
			const [x, y, w, h] = part.rect_xywh;
			assert.ok(x >= 0 && y >= 0 && w > 0 && h > 0 && x + w <= 1536 && y + h <= 1024, style.id);
			assert.ok(part.pivot_xy_in_rect[0] >= 0 && part.pivot_xy_in_rect[0] <= w);
			assert.ok(part.pivot_xy_in_rect[1] >= 0 && part.pivot_xy_in_rect[1] <= h);
		}
	}
});
test('joystick sprites retain source aspect and source-pixel pivot at actual mobile display widths', () => {
	for (const style of manifest.styles) for (const part of Object.values(style.components)) for (const width of [44, 101, 119, 136]) {
		const geometry = controlSpriteGeometry(part, width);
		assert.ok(Math.abs(geometry.width / geometry.height - part.rect_xywh[2] / part.rect_xywh[3]) < 1e-10);
		assert.ok(Math.abs(geometry.pivot.x / geometry.width - part.pivot_xy_in_rect[0] / part.rect_xywh[2]) < 1e-10);
		assert.ok(Math.abs(geometry.pivot.y / geometry.height - part.pivot_xy_in_rect[1] / part.rect_xywh[3]) < 1e-10);
	}
});
