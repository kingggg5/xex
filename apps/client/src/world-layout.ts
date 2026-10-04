export interface TerrainNeighbors {
	north: string | null;
	east: string | null;
	south: string | null;
	west: string | null;
}

export interface TerrainCellDefinition {
	id: string;
	asset: string;
	bounds_xz: [number, number, number, number];
	surface_y: number;
	walkable: boolean;
	neighbors: TerrainNeighbors;
}

export interface WorldPropDefinition {
	id: string;
	cell: string;
	kind: "tree_a" | "tree_b" | "tree_c" | "bush" | "trail_marker" | "broken_cart" | "stone_pillar";
	x: number;
	z: number;
	height: number;
	scale: number;
	yaw: number;
	collider_size: [number, number, number];
}

export interface WorldRouteDefinition {
	id: string;
	width: number;
	points: Array<[number, number]>;
}
