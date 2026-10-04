//! Ground-only traversal of authored city supports. Arithmetic order matches
//! `apps/client/src/grounded-city.mjs`; no render offsets or fused multiply-add.
use crate::coordinate_fixture::StaticCollider;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

const CELL_M: f32 = 16.0;
const MAX_VERTICES: usize = 100_000;
const MAX_TRIANGLES: usize = 50_000;
const MAX_SURFACES: usize = 4_096;
const MAX_BLOCKERS: usize = 2_048;
const MAX_INDEX_REFERENCES: usize = 300_000;
const MAX_INDEX_CELLS: usize = 8_192;
const MAX_SLOPE_TAN_SQUARED: f32 = 1.420_276_6;

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CityTraversalInput {
    pub schema: String,
    pub units: String,
    pub city_bounds: CityBounds,
    pub contract: MovementContract,
    pub surfaces: Vec<SupportInput>,
    #[serde(default)]
    pub blockers: Vec<BlockerInput>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CityBounds {
    pub min_x: f32,
    pub max_x: f32,
    pub min_z: f32,
    pub max_z: f32,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MovementContract {
    pub max_step_m: f32,
    pub max_slope_degrees: f32,
    pub feet_offset_m: f32,
    pub query_epsilon_m: f32,
    pub max_movement_substep_m: f32,
    #[serde(default, skip_serializing_if = "world_support_is_false")]
    pub world_support: bool,
}

fn world_support_is_false(value: &bool) -> bool {
    !*value
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SupportInput {
    pub id: String,
    pub kind: String,
    pub vertices: Vec<[f32; 3]>,
    pub triangles: Vec<[usize; 3]>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BlockerInput {
    pub id: String,
    pub kind: String,
    pub polygon_xz: Vec<[f32; 2]>,
    pub y_min: f32,
    pub y_max: f32,
}

#[derive(Debug, Clone, Copy)]
struct Bounds {
    min_x: f32,
    max_x: f32,
    min_z: f32,
    max_z: f32,
}

#[derive(Debug)]
struct Triangle {
    a: [f32; 3],
    ab: [f32; 3],
    ac: [f32; 3],
    area: f32,
    bounds: Bounds,
}

#[derive(Debug)]
struct Blocker {
    polygon: Vec<[f32; 2]>,
    min_y: f32,
    max_y: f32,
    bounds: Bounds,
}

#[derive(Debug, Clone, Copy, Serialize)]
pub struct TraversalStats {
    pub vertex_count: usize,
    pub triangle_count: usize,
    pub skipped_triangles: usize,
    pub blocker_count: usize,
    pub index_references: usize,
    pub index_cells: usize,
}

/// Immutable after parsing; one Arc is shared by all field rooms.
#[derive(Debug)]
pub struct GroundedCity {
    pub schema: String,
    bounds: CityBounds,
    contract: MovementContract,
    triangles: Vec<Triangle>,
    blockers: Vec<Blocker>,
    triangle_index: HashMap<(i32, i32), Vec<usize>>,
    blocker_index: HashMap<(i32, i32), Vec<usize>>,
    pub stats: TraversalStats,
}

fn number(value: f32, extent: f32) -> bool {
    value.is_finite() && value.abs() <= extent
}

fn valid_name(value: &str) -> bool {
    !value.is_empty() && value.len() <= 240
}

fn bounds_xz(vertices: impl Iterator<Item = [f32; 2]>) -> Bounds {
    let mut bounds = Bounds {
        min_x: f32::INFINITY,
        max_x: f32::NEG_INFINITY,
        min_z: f32::INFINITY,
        max_z: f32::NEG_INFINITY,
    };
    for [x, z] in vertices {
        bounds.min_x = bounds.min_x.min(x);
        bounds.max_x = bounds.max_x.max(x);
        bounds.min_z = bounds.min_z.min(z);
        bounds.max_z = bounds.max_z.max(z);
    }
    bounds
}

fn cell(value: f32) -> i32 {
    (value / CELL_M).floor() as i32
}

fn insert(
    index: &mut HashMap<(i32, i32), Vec<usize>>,
    id: usize,
    bounds: Bounds,
    references: &mut usize,
    cells: &mut usize,
) -> Result<(), String> {
    let (min_x, max_x, min_z, max_z) = (
        cell(bounds.min_x),
        cell(bounds.max_x),
        cell(bounds.min_z),
        cell(bounds.max_z),
    );
    let count = ((max_x - min_x + 1) as usize) * ((max_z - min_z + 1) as usize);
    *references = references
        .checked_add(count)
        .ok_or("spatial index reference overflow")?;
    if *references > MAX_INDEX_REFERENCES {
        return Err("spatial index reference budget".into());
    }
    for x in min_x..=max_x {
        for z in min_z..=max_z {
            if !index.contains_key(&(x, z)) {
                *cells += 1;
                if *cells > MAX_INDEX_CELLS {
                    return Err("spatial index cell budget".into());
                }
            }
            index.entry((x, z)).or_default().push(id);
        }
    }
    Ok(())
}

impl GroundedCity {
    pub fn parse(input: &CityTraversalInput, world_extent: f32) -> Result<Self, String> {
        if !matches!(input.schema.as_str(), "xexoria.city-traversal/1" | "xexoria.city-traversal/2") || input.units != "metres" {
            return Err("schema/units".into());
        }
        if !world_extent.is_finite() || world_extent <= 0.0 || world_extent > 4_096.0 {
            return Err("world extent".into());
        }
        let policy = &input.contract;
        if (input.schema == "xexoria.city-traversal/2") != policy.world_support {
            return Err("world_support requires schema2; schema2 requires true".into());
        }
        if !policy.max_step_m.is_finite()
            || policy.max_step_m <= 0.0
            || policy.max_step_m > 0.36
            || policy.max_slope_degrees != 50.0
            || !policy.query_epsilon_m.is_finite()
            || policy.query_epsilon_m <= 0.0
            || policy.query_epsilon_m > 0.00005
            || !policy.max_movement_substep_m.is_finite()
            || !(0.025..=0.1).contains(&policy.max_movement_substep_m)
            || !policy.feet_offset_m.is_finite()
            || !(0.0..=0.03).contains(&policy.feet_offset_m)
        {
            return Err("movement contract".into());
        }
        let bounds = &input.city_bounds;
        if ![bounds.min_x, bounds.max_x, bounds.min_z, bounds.max_z]
            .into_iter()
            .all(|v| number(v, world_extent))
            || bounds.min_x >= bounds.max_x
            || bounds.min_z >= bounds.max_z
        {
            return Err("city bounds".into());
        }
        if input.surfaces.len() > MAX_SURFACES || input.blockers.len() > MAX_BLOCKERS {
            return Err("surface/blocker count budget".into());
        }
        let mut field = Self {
            schema: input.schema.clone(),
            bounds: bounds.clone(),
            contract: policy.clone(),
            triangles: Vec::new(),
            blockers: Vec::new(),
            triangle_index: HashMap::new(),
            blocker_index: HashMap::new(),
            stats: TraversalStats {
                vertex_count: 0,
                triangle_count: 0,
                skipped_triangles: 0,
                blocker_count: 0,
                index_references: 0,
                index_cells: 0,
            },
        };
        let mut ids = HashSet::new();
        for support in &input.surfaces {
            if !matches!(
                support.kind.as_str(),
                "ground"
                    | "path"
                    | "plaza"
                    | "plaza_base"
                    | "terrace"
                    | "stairs"
                    | "bridge"
                    | "castle_forecourt"
                    | "ramp"
            ) {
                return Err("surface kind (roof/non-support excluded)".into());
            }
            if !valid_name(&support.id) || !ids.insert(&support.id) {
                return Err("bad/duplicate surface id".into());
            }
            field.stats.vertex_count += support.vertices.len();
            field.stats.triangle_count += support.triangles.len();
            if field.stats.vertex_count > MAX_VERTICES || field.stats.triangle_count > MAX_TRIANGLES
            {
                return Err("vertex/triangle budget".into());
            }
            if support
                .vertices
                .iter()
                .flatten()
                .any(|v| !number(*v, world_extent))
            {
                return Err("vertex outside finite world bounds".into());
            }
            for indices in &support.triangles {
                if indices.iter().any(|i| *i >= support.vertices.len()) {
                    return Err("triangle indices".into());
                }
                let [a, b, c] = indices.map(|i| support.vertices[i]);
                let ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
                let ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
                let area = (ab[0] * ac[2]) - (ab[2] * ac[0]);
                let nx = (ab[1] * ac[2]) - (ab[2] * ac[1]);
                let nz = (ab[0] * ac[1]) - (ab[1] * ac[0]);
                let horizontal_normal_squared = (nx * nx) + (nz * nz);
                if area.abs() < 0.00000001
                    || horizontal_normal_squared > ((area * area) * MAX_SLOPE_TAN_SQUARED)
                {
                    field.stats.skipped_triangles += 1;
                    continue;
                }
                let tri_bounds = bounds_xz([a, b, c].into_iter().map(|v| [v[0], v[2]]));
                let id = field.triangles.len();
                field.triangles.push(Triangle {
                    a,
                    ab,
                    ac,
                    area,
                    bounds: tri_bounds,
                });
                insert(
                    &mut field.triangle_index,
                    id,
                    tri_bounds,
                    &mut field.stats.index_references,
                    &mut field.stats.index_cells,
                )?;
            }
        }
        ids.clear();
        let mut polygon_vertices = 0;
        for blocker in &input.blockers {
            if !matches!(
                blocker.kind.as_str(),
                "solid_structure" | "tree_trunk" | "wall" | "street_object" | "water_hazard"
            ) {
                return Err("blocker kind".into());
            }
            if !valid_name(&blocker.id) || !ids.insert(&blocker.id) {
                return Err("bad/duplicate blocker id".into());
            }
            polygon_vertices += blocker.polygon_xz.len();
            if !(3..=64).contains(&blocker.polygon_xz.len()) || polygon_vertices > MAX_VERTICES {
                return Err("polygon vertex budget".into());
            }
            if blocker
                .polygon_xz
                .iter()
                .flatten()
                .any(|v| !number(*v, world_extent))
                || !number(blocker.y_min, world_extent)
                || !number(blocker.y_max, world_extent)
                || blocker.y_min >= blocker.y_max
            {
                return Err("blocker coordinate/height bounds".into());
            }
            if !valid_convex_polygon(&blocker.polygon_xz) {
                return Err("blocker polygon must be nondegenerate convex boundary".into());
            }
            let poly_bounds = bounds_xz(blocker.polygon_xz.iter().copied());
            let id = field.blockers.len();
            field.blockers.push(Blocker {
                polygon: blocker.polygon_xz.clone(),
                min_y: blocker.y_min,
                max_y: blocker.y_max,
                bounds: poly_bounds,
            });
            insert(
                &mut field.blocker_index,
                id,
                poly_bounds,
                &mut field.stats.index_references,
                &mut field.stats.index_cells,
            )?;
        }
        field.stats.blocker_count = field.blockers.len();
        Ok(field)
    }

    /// Highest authored support; missing support inside the city is a gap.
    pub fn height_at(&self, x: f32, z: f32) -> Option<f32> {
        if !x.is_finite() || !z.is_finite() {
            return None;
        }
        let b = &self.bounds;
        let outside = x < b.min_x || x > b.max_x || z < b.min_z || z > b.max_z;
        if outside && !self.contract.world_support {
            return Some(0.0);
        }
        let mut highest = None;
        let epsilon = self.contract.query_epsilon_m;
        for id in self
            .triangle_index
            .get(&(cell(x), cell(z)))
            .into_iter()
            .flatten()
        {
            let tri = &self.triangles[*id];
            let b = tri.bounds;
            if x < b.min_x - epsilon
                || x > b.max_x + epsilon
                || z < b.min_z - epsilon
                || z > b.max_z + epsilon
            {
                continue;
            }
            let ax = x - tri.a[0];
            let az = z - tri.a[2];
            let u = ((ax * tri.ac[2]) - (az * tri.ac[0])) / tri.area;
            let v = ((tri.ab[0] * az) - (tri.ab[2] * ax)) / tri.area;
            if u < -epsilon || v < -epsilon || (u + v) > (1.0 + epsilon) {
                continue;
            }
            let y = tri.a[1] + ((u * tri.ab[1]) + (v * tri.ac[1]));
            if highest.is_none_or(|previous| y > previous) {
                highest = Some(y);
            }
        }
        if highest.is_none() && outside { Some(0.0) } else { highest }
    }

    pub(crate) fn position_is_clear(
        &self,
        x: f32,
        y: f32,
        z: f32,
        radius: f32,
        height: f32,
        boxes: &[StaticCollider],
    ) -> bool {
        [x, y, z, radius, height].into_iter().all(f32::is_finite)
            && radius > 0.0
            && height > 0.0
            && self.height_at(x, z).is_some()
            && !self.blocked(x, y, z, radius, height, boxes)
    }

    /// Exact segment checks against the same authored solid polygons as movement.
    pub(crate) fn line_is_clear(&self, a:[f32;3], b:[f32;3]) -> bool {
        if !a.into_iter().chain(b).all(f32::is_finite) {return false;}
        !self.blockers.iter().any(|blocker| {
            if a[1].min(b[1])>=blocker.max_y || a[1].max(b[1])<=blocker.min_y {return false;}
            let lo=a[0].min(b[0]);let hi=a[0].max(b[0]);let low=a[2].min(b[2]);let high=a[2].max(b[2]);
            if hi<blocker.bounds.min_x || lo>blocker.bounds.max_x || high<blocker.bounds.min_z || low>blocker.bounds.max_z {return false;}
            // Clip to the wall's vertical slab first. A descending ray can enter
            // above the wall and leave below it while crossing its solid middle.
            let dy=b[1]-a[1];let(t0,t1)=if dy.abs()<1e-7{(0.0,1.0)}else{
                let x=(blocker.min_y-a[1])/dy;let y=(blocker.max_y-a[1])/dy;
                (x.min(y).max(0.0),x.max(y).min(1.0))
            };
            if t0>t1{return false;}
            let p=[a[0]+(b[0]-a[0])*t0,a[2]+(b[2]-a[2])*t0];
            let end=[a[0]+(b[0]-a[0])*t1,a[2]+(b[2]-a[2])*t1];
            if overlaps_polygon(p[0],p[1],0.0,&blocker.polygon)||overlaps_polygon(end[0],end[1],0.0,&blocker.polygon){return true;}
            let r=[end[0]-p[0],end[1]-p[1]];
            blocker.polygon.iter().zip(blocker.polygon.iter().cycle().skip(1)).take(blocker.polygon.len()).any(|(c,d)|{
                let s=[d[0]-c[0],d[1]-c[1]];let den=r[0]*s[1]-r[1]*s[0];
                if den.abs()<1e-7 {return false;}
                let q=[c[0]-p[0],c[1]-p[1]];let t=(q[0]*s[1]-q[1]*s[0])/den;let u=(q[0]*r[1]-q[1]*r[0])/den;
                (0.0..=1.0).contains(&t)&&(0.0..=1.0).contains(&u)
            })
        })
    }

    fn blocked(
        &self,
        x: f32,
        y: f32,
        z: f32,
        radius: f32,
        height: f32,
        boxes: &[StaticCollider],
    ) -> bool {
        if boxes
            .iter()
            .any(|b| overlaps_box(x, y, z, radius, height, b))
        {
            return true;
        }
        for cx in cell(x - radius)..=cell(x + radius) {
            for cz in cell(z - radius)..=cell(z + radius) {
                for id in self.blocker_index.get(&(cx, cz)).into_iter().flatten() {
                    let blocker = &self.blockers[*id];
                    if blocker.max_y <= y || blocker.min_y >= (y + height) {
                        continue;
                    }
                    let b = blocker.bounds;
                    if x < (b.min_x - radius)
                        || x > (b.max_x + radius)
                        || z < (b.min_z - radius)
                        || z > (b.max_z + radius)
                    {
                        continue;
                    }
                    if overlaps_polygon(x, z, radius, &blocker.polygon) {
                        return true;
                    }
                }
            }
        }
        false
    }

    /// At most sixteen 0.1m subdivisions. Oversized movement is rejected.
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn move_capsule(
        &self,
        position: Position,
        dx: f32,
        dz: f32,
        radius: f32,
        height: f32,
        boxes: &[StaticCollider],
        world_limit: f32,
    ) -> Position {
        if ![
            position.x,
            position.y,
            position.z,
            dx,
            dz,
            radius,
            height,
            world_limit,
        ]
        .into_iter()
        .all(f32::is_finite)
            || radius <= 0.0
            || radius > 2.0
            || height <= 0.0
            || height > 10.0
            || world_limit <= radius
            || world_limit > 4_096.0
            || !valid_boxes(boxes)
        {
            return position;
        }
        let Some(sampled) = self.height_at(position.x, position.z) else {
            return position;
        };
        let step_limit = self.contract.max_step_m + self.contract.query_epsilon_m;
        if (sampled - position.y).abs() > step_limit {
            return position;
        }
        let distance = ((dx * dx) + (dz * dz)).sqrt();
        let steps = (distance / self.contract.max_movement_substep_m)
            .ceil()
            .max(1.0);
        if steps > 16.0 {
            return position;
        }
        let limit = world_limit - radius;
        let mut p = Position {
            x: position.x.clamp(-limit, limit),
            y: position.y,
            z: position.z.clamp(-limit, limit),
        };
        let sx = dx / steps;
        let sz = dz / steps;
        for _ in 0..steps as usize {
            let nx = (p.x + sx).clamp(-limit, limit);
            if let Some(y) = self.target_height(nx, p.y, p.z, radius, height, boxes, step_limit) {
                p.x = nx;
                p.y = y;
            }
            let nz = (p.z + sz).clamp(-limit, limit);
            if let Some(y) = self.target_height(p.x, p.y, nz, radius, height, boxes, step_limit) {
                p.z = nz;
                p.y = y;
            }
        }
        p
    }

    #[allow(clippy::too_many_arguments)]
    fn target_height(
        &self,
        x: f32,
        y: f32,
        z: f32,
        radius: f32,
        height: f32,
        boxes: &[StaticCollider],
        step_limit: f32,
    ) -> Option<f32> {
        let support = self.height_at(x, z)?;
        if (support - y).abs() > step_limit || self.blocked(x, support, z, radius, height, boxes) {
            None
        } else {
            Some(support)
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct Position {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

fn valid_boxes(boxes: &[StaticCollider]) -> bool {
    boxes.len() <= 4_096
        && boxes.iter().all(|b| {
            [b.min_x, b.max_x, b.min_y, b.max_y, b.min_z, b.max_z]
                .into_iter()
                .all(|v| number(v, 4_096.0))
                && b.min_x <= b.max_x
                && b.min_y <= b.max_y
                && b.min_z <= b.max_z
        })
}

fn overlaps_box(x: f32, y: f32, z: f32, radius: f32, height: f32, b: &StaticCollider) -> bool {
    if b.max_y <= y || b.min_y >= y + height {
        return false;
    }
    let dx = x - x.clamp(b.min_x, b.max_x);
    let dz = z - z.clamp(b.min_z, b.max_z);
    ((dx * dx) + (dz * dz)) <= (radius * radius)
}

pub(crate) fn overlaps_polygon(x: f32, z: f32, radius: f32, polygon: &[[f32; 2]]) -> bool {
    let mut inside = false;
    let mut j = polygon.len() - 1;
    for i in 0..polygon.len() {
        let a = polygon[j];
        let b = polygon[i];
        let ab_x = b[0] - a[0];
        let ab_z = b[1] - a[1];
        let length_squared = (ab_x * ab_x) + (ab_z * ab_z);
        let ap_x = x - a[0];
        let ap_z = z - a[1];
        let t = if length_squared > 0.0 {
            (((ap_x * ab_x) + (ap_z * ab_z)) / length_squared).clamp(0.0, 1.0)
        } else {
            0.0
        };
        let dx = x - (a[0] + (t * ab_x));
        let dz = z - (a[1] + (t * ab_z));
        if ((dx * dx) + (dz * dz)) <= (radius * radius) {
            return true;
        }
        if (a[1] > z) != (b[1] > z) && x < (a[0] + (((z - a[1]) * ab_x) / ab_z)) {
            inside = !inside;
        }
        j = i;
    }
    inside
}

pub(crate) fn valid_convex_polygon(polygon: &[[f32; 2]]) -> bool {
    let mut orientation = 0.0_f32;
    for i in 0..polygon.len() {
        let a = polygon[i];
        let b = polygon[(i + 1) % polygon.len()];
        let dx = b[0] - a[0];
        let dz = b[1] - a[1];
        if dx == 0.0 && dz == 0.0 {
            return false;
        }
        for point in polygon {
            let cross = dx * (point[1] - a[1]) - dz * (point[0] - a[0]);
            if cross.abs() <= 0.00001 {
                continue;
            }
            if orientation == 0.0 {
                orientation = cross.signum();
            } else if cross.signum() != orientation {
                return false;
            }
        }
    }
    orientation != 0.0
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    fn rect(id: &str, min_x: f32, max_x: f32, min_z: f32, max_z: f32, y: f32) -> SupportInput {
        SupportInput {
            id: id.into(),
            kind: "ground".into(),
            vertices: vec![
                [min_x, y, min_z],
                [max_x, y, min_z],
                [max_x, y, max_z],
                [min_x, y, max_z],
            ],
            triangles: vec![[0, 1, 2], [0, 2, 3]],
        }
    }
    pub(crate) fn fixture() -> CityTraversalInput {
        CityTraversalInput {
            schema: "xexoria.city-traversal/1".into(),
            units: "metres".into(),
            city_bounds: CityBounds {
                min_x: -10.0,
                max_x: 10.0,
                min_z: -10.0,
                max_z: 10.0,
            },
            contract: MovementContract {
                max_step_m: 0.36,
                max_slope_degrees: 50.0,
                feet_offset_m: 0.015,
                query_epsilon_m: 0.00005,
                max_movement_substep_m: 0.1,
                world_support: false,
            },
            surfaces: vec![rect("floor", -10.0, 10.0, -10.0, 10.0, 0.0)],
            blockers: vec![],
        }
    }
    fn build(input: &CityTraversalInput) -> GroundedCity {
        GroundedCity::parse(input, 308.0).unwrap()
    }
    fn walk(
        field: &GroundedCity,
        p: Position,
        dx: f32,
        dz: f32,
        boxes: &[StaticCollider],
    ) -> Position {
        field.move_capsule(p, dx, dz, 0.35, 1.8, boxes, 308.0)
    }
    fn p(x: f32, y: f32, z: f32) -> Position {
        Position { x, y, z }
    }
    fn near(a: f32, b: f32) {
        assert!((a - b).abs() < 0.0001, "{a} != {b}");
    }

    #[test]
    fn exact_f32_client_golden_and_highest_support() {
        let field = build(&fixture());
        assert_eq!(
            walk(&field, p(0.125, 0.0, -0.5), 0.25, 0.0, &[]),
            p(0.37500003, 0.0, -0.5)
        );
        let mut input = fixture();
        input
            .surfaces
            .push(rect("upper", -2.0, 2.0, -2.0, 2.0, 0.15));
        near(build(&input).height_at(0.0, 0.0).unwrap(), 0.15);
    }
    #[test]
    fn stairs_climb_descend_without_visual_feet_offset() {
        let mut input = fixture();
        for i in 0..6 {
            input.surfaces.push(rect(
                &format!("step{i}"),
                i as f32 * 0.5,
                (i + 1) as f32 * 0.5,
                -1.0,
                1.0,
                (i + 1) as f32 * 0.15,
            ));
        }
        let field = build(&input);
        let mut position = p(-0.25, 0.0, 0.0);
        for _ in 0..6 {
            position = walk(&field, position, 0.5, 0.0, &[]);
        }
        near(position.x, 2.75);
        near(position.y, 0.9);
        for _ in 0..6 {
            position = walk(&field, position, -0.5, 0.0, &[]);
        }
        near(position.x, -0.25);
        assert_eq!(position.y, 0.0);
    }
    #[test]
    fn gaps_cliffs_and_wrong_start_height_reject_teleport() {
        let mut input = fixture();
        input.surfaces = vec![rect("west", -10.0, -1.0, -10.0, 10.0, 0.0)];
        let field = build(&input);
        assert_eq!(field.height_at(0.0, 0.0), None);
        assert_eq!(field.height_at(-11.0, 0.0), Some(0.0));
        assert!(walk(&field, p(-1.25, 0.0, 0.0), 0.8, 0.0, &[]).x <= -1.0);
        input = fixture();
        input
            .surfaces
            .push(rect("bridge", 0.0, 4.0, -1.0, 1.0, 0.9));
        let field = build(&input);
        assert!(walk(&field, p(-0.2, 0.0, 0.0), 0.8, 0.0, &[]).x < 0.0);
        assert!(walk(&field, p(0.2, 0.9, 0.0), -0.8, 0.0, &[]).x >= 0.0);
        assert_eq!(
            walk(&field, p(0.2, 0.0, 0.0), 0.1, 0.0, &[]),
            p(0.2, 0.0, 0.0)
        );
    }
    #[test]
    fn slopes_filter_and_interpolate_continuously() {
        let mut input = fixture();
        input.surfaces = vec![SupportInput {
            id: "ramp".into(),
            kind: "ramp".into(),
            vertices: vec![
                [-1.0, 0.0, -1.0],
                [1.0, 0.0, -1.0],
                [1.0, 1.0, 1.0],
                [-1.0, 1.0, 1.0],
            ],
            triangles: vec![[0, 1, 2], [0, 2, 3]],
        }];
        let field = build(&input);
        near(field.height_at(0.0, 0.0).unwrap(), 0.5);
        near(walk(&field, p(0.0, 0.25, -0.5), 0.0, 1.0, &[]).y, 0.75);
        input.surfaces[0].vertices[2][1] = 4.0;
        input.surfaces[0].vertices[3][1] = 4.0;
        let steep = build(&input);
        assert_eq!(steep.stats.skipped_triangles, 2);
        assert_eq!(steep.height_at(0.0, 0.0), None);
    }
    #[test]
    fn boxes_and_rotated_polygons_use_support_y_and_slide() {
        let mut input = fixture();
        input.surfaces[0] = rect("terrace", -10.0, 10.0, -10.0, 10.0, 3.0);
        let field = build(&input);
        let mut wall = StaticCollider {
            min_x: 0.0,
            max_x: 0.2,
            min_y: 0.0,
            max_y: 2.0,
            min_z: -3.0,
            max_z: 3.0,
        };
        near(walk(&field, p(-0.5, 3.0, 0.0), 1.0, 0.0, &[wall]).x, 0.5);
        wall.min_y = 3.1;
        wall.max_y = 5.0;
        let slide = walk(&field, p(-0.5, 3.0, 0.0), 1.0, 0.5, &[wall]);
        assert!(slide.x <= -0.35);
        near(slide.z, 0.5);
        input = fixture();
        input.blockers.push(BlockerInput {
            id: "rotated".into(),
            kind: "wall".into(),
            polygon_xz: vec![[0.0, -1.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]],
            y_min: 0.0,
            y_max: 2.0,
        });
        let field = build(&input);
        assert!(walk(&field, p(-1.5, 0.0, 0.0), 1.0, 0.0, &[]).x <= -1.35);
        let corner = field.move_capsule(p(0.9, 0.0, 0.9), 0.2, 0.0, 0.1, 1.8, &[], 308.0);
        near(corner.x, 1.1);
    }
    #[test]
    fn excessive_distance_and_bad_inputs_cannot_tunnel() {
        let field = build(&fixture());
        let position = p(-2.0, 0.0, 0.0);
        assert_eq!(walk(&field, position, 9.0, 0.0, &[]), position);
        assert_eq!(walk(&field, position, f32::NAN, 0.0, &[]), position);
        let thin = StaticCollider {
            min_x: 0.0,
            max_x: 0.005,
            min_y: 0.0,
            max_y: 2.0,
            min_z: -3.0,
            max_z: 3.0,
        };
        assert!(walk(&field, p(-1.0, 0.0, 0.0), 1.5, 0.0, &[thin]).x <= -0.35);
    }
    #[test]
    fn closed_schema_rejects_roofs_bounds_and_work_amplification() {
        let mut input = fixture();
        input.surfaces[0].kind = "roof".into();
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.surfaces[0].vertices[0][0] = f32::NAN;
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.surfaces[0].vertices[0][0] = 309.0;
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.surfaces[0].triangles = vec![[0, 1, 2]; 50_001];
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.surfaces = vec![rect("wide", -308.0, 308.0, -308.0, 308.0, 0.0)];
        input.surfaces[0].triangles = vec![[0, 1, 2]; 200];
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        let mut value = serde_json::to_value(fixture()).unwrap();
        value["roof_hack"] = true.into();
        assert!(serde_json::from_value::<CityTraversalInput>(value).is_err());
    }

    #[test]
    fn real_art_candidate_operational_fields_match_landmark_support() {
        // Candidate metadata is explicitly excluded from the operational schema.
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../planning/city-traversal-v1.json");
        let candidate: serde_json::Value =
            serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        let surfaces:Vec<_>=candidate["surfaces"].as_array().unwrap().iter().map(|surface|serde_json::json!({"id":surface["id"],"kind":surface["kind"],"vertices":surface["vertices"],"triangles":surface["triangles"]})).collect();
        let policy = &candidate["contract"];
        let operational = serde_json::json!({"schema":candidate["schema"],"units":candidate["units"],"city_bounds":candidate["city_bounds"],"contract":{"max_step_m":policy["max_step_m"],"max_slope_degrees":policy["max_slope_degrees"],"feet_offset_m":policy["feet_offset_m"],"query_epsilon_m":policy["query_epsilon_m"],"max_movement_substep_m":policy["max_movement_substep_m"]},"surfaces":surfaces,"blockers":candidate["blockers"]});
        let input: CityTraversalInput = serde_json::from_value(operational).unwrap();
        let field = build(&input);
        for landmark in candidate["landmarks"].as_array().unwrap() {
            near(
                field
                    .height_at(
                        landmark["x"].as_f64().unwrap() as f32,
                        landmark["z"].as_f64().unwrap() as f32,
                    )
                    .unwrap(),
                landmark["support_y"].as_f64().unwrap() as f32,
            );
        }
        assert!(field.stats.index_references <= MAX_INDEX_REFERENCES);
    }

    #[test]
    fn malformed_blockers_contract_and_budget_inputs_are_rejected() {
        let wall = BlockerInput {
            id: "wall".into(),
            kind: "wall".into(),
            polygon_xz: vec![[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            y_min: 0.0,
            y_max: 2.0,
        };
        let mut input = fixture();
        input.blockers = vec![wall.clone(); 2_049];
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.blockers = vec![wall.clone()];
        input.blockers[0].polygon_xz = vec![[0.0, 0.0]; 65];
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input.blockers[0] = wall.clone();
        input.blockers[0].polygon_xz = vec![[0.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 0.0]];
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input.blockers[0] = wall;
        input.blockers[0].y_max = f32::INFINITY;
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.contract.max_step_m = 1.0;
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.surfaces[0].vertices = vec![[0.0, 0.0, 0.0]; 100_001];
        assert!(GroundedCity::parse(&input, 308.0).is_err());
        input = fixture();
        input.surfaces.push(input.surfaces[0].clone());
        assert!(GroundedCity::parse(&input, 308.0).is_err());
    }

    fn world_support_fixture() -> CityTraversalInput {
        let mut input = fixture();
        input.schema = "xexoria.city-traversal/2".into();
        input.contract.world_support = true;
        input.surfaces = vec![rect("city-west", -10.0, -1.0, -10.0, 10.0, 0.0),
            SupportInput { id: "remote-six-metre-ramp".into(), kind: "ramp".into(),
                vertices: vec![[20.0, 0.0, -40.0], [22.0, 0.0, -40.0], [22.0, 6.0, -16.0], [20.0, 6.0, -16.0]],
                triangles: vec![[0, 1, 2], [0, 2, 3]] },
            rect("remote-six-metre-top", 20.0, 22.0, -16.0, -14.0, 6.0)];
        input
    }

    #[test]
    fn world_support_version_gate_and_malformed_flags_fail_closed() {
        let mut legacy = fixture(); legacy.contract.world_support = true;
        assert!(GroundedCity::parse(&legacy, 308.0).is_err());
        let mut wrong = fixture(); wrong.schema = "xexoria.city-traversal/2".into();
        assert!(GroundedCity::parse(&wrong, 308.0).is_err());
        let mut missing = serde_json::to_value(wrong).unwrap();missing["contract"].as_object_mut().unwrap().remove("world_support");
        let absent: CityTraversalInput = serde_json::from_value(missing).unwrap();assert!(GroundedCity::parse(&absent,308.0).is_err());
        for bad in [serde_json::Value::Null, serde_json::json!("true"), serde_json::json!(0), serde_json::json!(1), serde_json::json!([]), serde_json::json!({})] {
            let mut value = serde_json::to_value(fixture()).unwrap();value["contract"]["world_support"] = bad;
            assert!(serde_json::from_value::<CityTraversalInput>(value).is_err());
        }
        assert_eq!(build(&world_support_fixture()).schema, "xexoria.city-traversal/2");
    }

    #[test]
    fn world_support_false_is_omitted_without_changing_legacy_serialized_contract() {
        #[derive(Serialize)]
        struct LegacyContract { max_step_m: f32, max_slope_degrees: f32, feet_offset_m: f32, query_epsilon_m: f32, max_movement_substep_m: f32 }
        let contract = fixture().contract;
        let legacy = LegacyContract { max_step_m: contract.max_step_m, max_slope_degrees: contract.max_slope_degrees, feet_offset_m: contract.feet_offset_m, query_epsilon_m: contract.query_epsilon_m, max_movement_substep_m: contract.max_movement_substep_m };
        assert_eq!(serde_json::to_vec(&contract).unwrap(), serde_json::to_vec(&legacy).unwrap());
        let absent: MovementContract = serde_json::from_slice(&serde_json::to_vec(&legacy).unwrap()).unwrap();assert!(!absent.world_support);
        let mut value = serde_json::to_value(&contract).unwrap();value["world_support"] = serde_json::json!(false);
        let explicit: MovementContract = serde_json::from_value(value).unwrap();assert_eq!(serde_json::to_vec(&explicit).unwrap(),serde_json::to_vec(&legacy).unwrap());
    }

    #[test]
    fn world_support_default_preserves_current_canonical_bundle_bytes() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../content");
        let current = crate::content::build_from_source(&root.join("source")).unwrap();
        let built = root.join("build").join(current.hash_hex()).join("bundle.json");
        let bytes = std::fs::read(built).expect("Current source must match its existing canonical build hash");
        assert_eq!(current.bundle_json.as_bytes(), bytes.as_slice());
    }

    #[test]
    fn world_support_remote_height_climb_return_and_gap_semantics() {
        let input = world_support_fixture();let field = build(&input);
        near(field.height_at(21.0,-28.0).unwrap(),3.0);near(field.height_at(21.0,-15.0).unwrap(),6.0);
        assert_eq!(field.height_at(30.0,-28.0),Some(0.0));assert_eq!(field.height_at(0.0,0.0),None);
        let mut position=p(21.0,0.0,-40.25);for _ in 0..99 { position=walk(&field,position,0.0,0.25,&[]); }
        near(position.z,-15.5);near(position.y,6.0);for _ in 0..99 { position=walk(&field,position,0.0,-0.25,&[]); }
        near(position.z,-40.25);near(position.y,0.0);
        let wrong=p(21.0,0.0,-15.0);assert_eq!(walk(&field,wrong,0.0,0.1,&[]),wrong);
        let cliff=walk(&field,p(21.0,6.0,-14.05),0.0,0.3,&[]);assert!(cliff.z<=-14.0);near(cliff.y,6.0);
        let mut old=input;old.schema="xexoria.city-traversal/1".into();old.contract.world_support=false;assert_eq!(build(&old).height_at(21.0,-15.0),Some(0.0));
    }

    #[test]
    fn mage_los_uses_wall_height_interior_and_thin_polygon_edges() {
        let mut input=fixture();input.blockers=vec![BlockerInput{id:"spell-wall".into(),kind:"wall".into(),polygon_xz:vec![[-1.0,1.49],[1.0,1.49],[1.0,1.51],[-1.0,1.51]],y_min:0.0,y_max:2.0}];
        let field=build(&input);
        assert!(!field.line_is_clear([0.0,1.0,0.0],[0.0,1.0,3.0]));
        assert!(field.line_is_clear([0.0,3.0,0.0],[0.0,3.0,3.0]));
        assert!(!field.line_is_clear([0.0,3.0,1.5],[0.0,-1.0,1.5]));
        assert!(!field.line_is_clear([0.0,f32::NAN,0.0],[0.0,1.0,3.0]));
    }

    #[test]
    fn world_support_still_rejects_roofs_and_skips_unsafe_remote_slopes() {
        let mut roof=world_support_fixture();let mut surface=rect("remote-roof",24.0,26.0,-30.0,-28.0,5.0);surface.kind="roof".into();roof.surfaces.push(surface);assert!(GroundedCity::parse(&roof,308.0).is_err());
        let mut steep=world_support_fixture();steep.surfaces.push(SupportInput { id:"unsafe-remote-face".into(),kind:"ramp".into(),vertices:vec![[24.0,0.0,-30.0],[26.0,0.0,-30.0],[26.0,6.0,-29.0],[24.0,6.0,-29.0]],triangles:vec![[0,1,2],[0,2,3]] });let field=build(&steep);assert_eq!(field.stats.skipped_triangles,2);assert_eq!(field.height_at(25.0,-29.5),Some(0.0));assert_eq!(field.height_at(0.0,0.0),None);
    }
}
