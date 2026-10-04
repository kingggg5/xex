import { Buffer, VertexBuffer } from '@babylonjs/core/Buffers/buffer.js';

/**
 * Pack the static dressing attributes in one geometry-owned allocation. Call after
 * all vertex authoring and makeGeometryUnique(), including on each clone: Babylon
 * Geometry.copy() deinterleaves attributes. The caller removes tangent/UV2.
 * Packing position/normal/UV/colour together also works when normal and colour
 * are not consecutive in the shader's attribute order. Matrix/fade stay separate.
 * After packing, author through a full interleaved buffer or repack; a tight
 * updateVerticesData(kind, ...) would overwrite the shared allocation.
 */
export function packDressingVertexBuffers(mesh) {
  if (mesh.isDisposed()) throw new TypeError('Cannot pack a disposed dressing mesh');
  const count = mesh.getTotalVertices();
  if (!Number.isSafeInteger(count) || count < 0) throw new TypeError('Invalid dressing vertex count');
  const kinds = [VertexBuffer.PositionKind, VertexBuffer.NormalKind, VertexBuffer.UVKind, VertexBuffer.ColorKind];
  const buffers = kinds.map(kind => mesh.getVertexBuffer(kind));
  if (count === 0) {
    if (kinds.some(kind => mesh.getVerticesData(kind)?.length)) throw new TypeError('Dressing attributes exist without positions');
    return { packed: false, reason: 'empty-mesh', vertexCount: 0 };
  }
  if (!buffers[3]) return { packed: false, reason: 'no-color', vertexCount: count };
  if (mesh.geometry.meshes.length > 1) throw new TypeError('Call makeGeometryUnique() before packing dressing clones');
  const colorSize = buffers[3].getSize();
  if (colorSize !== 3 && colorSize !== 4) throw new TypeError('Dressing colour must be RGB3 or RGBA4');
  const sizes = [3, 3, 2, colorSize], attributes = [];
  let stride = 0, updatable = false;
  for (let index = 0; index < kinds.length; index++) {
    const buffer = buffers[index];
    if (!buffer && index === 2) continue;
    if (!buffer || buffer.getSize() !== sizes[index] || buffer.getIsInstanced()) throw new TypeError(`Invalid dressing ${kinds[index]} attribute`);
    // Babylon's float readback can throw RangeError before returning malformed
    // short arrays, and can truncate extra tight elements. Validate capacity first.
    const raw = buffer.getData(), bytes = Array.isArray(raw) ? raw.length * 4 : raw?.byteLength;
    const componentBytes = buffer.getSize(true), available = bytes - buffer.byteOffset - componentBytes;
    const capacity = available >= 0 ? 1 + Math.floor(available / buffer.byteStride) : 0;
    if (!raw || !Number.isFinite(bytes) || capacity !== count) throw new TypeError(`Dressing ${kinds[index]} count mismatch`);
    const data = mesh.getVerticesData(kinds[index]);
    if (!data || data.length !== count * sizes[index]) throw new TypeError(`Dressing ${kinds[index]} count mismatch`);
    for (const value of data) if (!Number.isFinite(value)) throw new TypeError(`Non-finite dressing ${kinds[index]} value`);
    attributes.push({ kind: kinds[index], size: sizes[index], offset: stride, data });
    stride += sizes[index]; updatable ||= buffer.isUpdatable();
  }
  const data = new Float32Array(count * stride);
  for (let vertex = 0; vertex < count; vertex++) for (const attribute of attributes) {
    for (let component = 0; component < attribute.size; component++) {
      const value = attribute.data[vertex * attribute.size + component];
      data[vertex * stride + attribute.offset + component] = value;
      if (!Number.isFinite(data[vertex * stride + attribute.offset + component])) throw new TypeError('Dressing value exceeds Float32 range');
    }
  }
  const engine = mesh.getEngine(), allocation = new Buffer(engine, data, updatable, stride, false, false, false, 1, 'dressing-packed-geometry');
  // Geometry.setVerticesBuffer adds one reference for each owning view. First
  // view adopts the initial reference; the final view's disposal frees it.
  for (const attribute of attributes) mesh.setVerticesBuffer(new VertexBuffer(engine, allocation, attribute.kind, {
    stride, size: attribute.size, offset: attribute.offset, type: VertexBuffer.FLOAT,
    normalized: false, updatable, takeBufferOwnership: true,
  }));
  return { packed: true, vertexCount: count, colorSize, strideFloats: stride,
    attributes: attributes.map(attribute => attribute.kind), allocationCount: 1 };
}
