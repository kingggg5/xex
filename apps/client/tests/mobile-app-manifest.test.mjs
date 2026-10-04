import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const manifest = JSON.parse(await fs.readFile(new URL('public/manifest.webmanifest',root),'utf8'));

test('installed game launches within its scope as a landscape standalone app', () => {
	const origin='https://xexoria.example';
	assert.equal(manifest.display,'standalone'); assert.equal(manifest.orientation,'landscape');
	const start=new URL(manifest.start_url,origin), scope=new URL(manifest.scope,origin);
	assert.equal(start.origin,scope.origin); assert.ok(start.pathname.startsWith(scope.pathname));
	assert.equal(new URL(manifest.id,origin).pathname,'/');
	assert.equal(start.searchParams.get('from'),'homescreen');
});

test('manifest icon declarations match real square PNG resources', async () => {
	assert.deepEqual(manifest.icons.map(icon=>icon.sizes).sort(),['192x192','512x512']);
	for (const icon of manifest.icons) {
		assert.equal(icon.type,'image/png'); assert.equal(icon.purpose,'any');
		assert.match(icon.src,/^\/app-icons\/[\w-]+\.png$/);
		const bytes=await fs.readFile(new URL(`public${icon.src}`,root));
		assert.equal(bytes.subarray(1,4).toString(),'PNG');
		const size=Number(icon.sizes.split('x')[0]);
		assert.equal(bytes.readUInt32BE(16),size); assert.equal(bytes.readUInt32BE(20),size);
	}
});

test('Safari legacy metadata and touch icon exist independently of JS startup', async () => {
	const html=await fs.readFile(new URL('index.html',root),'utf8');
	assert.match(html,/<link\s+rel="manifest"\s+href="\/manifest\.webmanifest"\s*\/>/);
	assert.match(html,/<meta\s+name="apple-mobile-web-app-capable"\s+content="yes"\s*\/>/);
	assert.match(html,/<meta\s+name="apple-mobile-web-app-title"\s+content="Xexoria"\s*\/>/);
	assert.match(html,/rel="apple-touch-icon"[^>]+href="\/app-icons\/apple-touch-icon180\.png"/);
	const png=await fs.readFile(new URL('public/app-icons/apple-touch-icon180.png',root));
	assert.equal(png.readUInt32BE(16),180); assert.equal(png.readUInt32BE(20),180);
});
