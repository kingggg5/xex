/** Project one world coordinate into the existing fixed-scale circular minimap. */
export function projectMinimapCoordinate(value, extent, radius, edgeMargin = 12) {
	const safeExtent = Number.isFinite(extent) && extent > 0 ? extent : 28;
	const safeRadius = Number.isFinite(radius) && radius > 0 ? radius : 0;
	const safeMargin = Number.isFinite(edgeMargin) ? Math.max(0, Math.min(safeRadius, edgeMargin)) : 12;
	const coordinate = Number.isFinite(value) ? Math.max(-safeExtent, Math.min(safeExtent, value)) : 0;
	return safeRadius + coordinate / safeExtent * (safeRadius - safeMargin);
}
