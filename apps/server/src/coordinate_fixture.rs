use serde::Deserialize;

const FIXTURE_JSON: &str = include_str!("../../protocol/coordinate-fixture-v1.json");

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CoordinateFixture {
    schema_version: u8,
    units: String,
    handedness: String,
    axes: Axes,
    tolerance_m: f32,
    unit_cube: UnitCube,
    player_capsule: PlayerCapsule,
    doorway: Doorway,
    ramp: Ramp,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Axes {
    right: String,
    up: String,
    forward: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct UnitCube {
    center: [f32; 3],
    dimensions: [f32; 3],
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PlayerCapsule {
    feet: [f32; 3],
    radius: f32,
    height: f32,
    axis: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Doorway {
    floor_center: [f32; 3],
    clear_width: f32,
    clear_height: f32,
    wall_thickness: f32,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Ramp {
    lower_origin: [f32; 3],
    width: f32,
    run: f32,
    rise: f32,
}

impl CoordinateFixture {
    fn parse(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }

    fn validate(&self) -> Result<(), &'static str> {
        if self.schema_version != 1 || self.units != "m" || self.handedness != "left" {
            return Err("unsupported coordinate convention");
        }
        if self.axes.right != "+x" || self.axes.up != "+y" || self.axes.forward != "+z" {
            return Err("unexpected axis convention");
        }
        if !self.tolerance_m.is_finite() || self.tolerance_m <= 0.0 || self.tolerance_m > 0.01 {
            return Err("invalid coordinate tolerance");
        }
        if !all_finite(&self.unit_cube.center)
            || !all_positive(&self.unit_cube.dimensions)
            || self
                .unit_cube
                .dimensions
                .iter()
                .any(|dimension| (*dimension - 1.0).abs() > self.tolerance_m)
        {
            return Err("unit cube must measure one meter on every axis");
        }
        if !all_finite(&self.player_capsule.feet)
            || !positive(self.player_capsule.radius)
            || !positive(self.player_capsule.height)
            || self.player_capsule.axis != "+y"
            || self.player_capsule.height + self.tolerance_m < 2.0 * self.player_capsule.radius
        {
            return Err("invalid player capsule");
        }
        if !all_finite(&self.doorway.floor_center)
            || !positive(self.doorway.clear_width)
            || !positive(self.doorway.clear_height)
            || !positive(self.doorway.wall_thickness)
            || !capsule_fits_doorway(&self.player_capsule, &self.doorway, self.tolerance_m)
        {
            return Err("player capsule does not fit the doorway");
        }
        if !all_finite(&self.ramp.lower_origin)
            || !positive(self.ramp.width)
            || !positive(self.ramp.run)
            || !positive(self.ramp.rise)
        {
            return Err("invalid ramp dimensions");
        }
        Ok(())
    }

    pub(crate) fn embedded() -> Self {
        let fixture = Self::parse(FIXTURE_JSON).expect("embedded coordinate fixture parses");
        fixture
            .validate()
            .expect("embedded coordinate fixture is valid");
        fixture
    }

    pub(crate) fn player_radius(&self) -> f32 {
        self.player_capsule.radius
    }

    pub(crate) fn player_height(&self) -> f32 {
        self.player_capsule.height
    }

    #[cfg(test)]
    pub(crate) fn static_colliders(&self) -> Vec<StaticCollider> {
        let mut colliders = vec![StaticCollider::from_center_dimensions(
            self.unit_cube.center,
            self.unit_cube.dimensions,
        )];

        let doorway = &self.doorway;
        for side in [-1.0_f32, 1.0] {
            let center = [
                doorway.floor_center[0]
                    + side * (doorway.clear_width * 0.5 + doorway.wall_thickness * 0.5),
                doorway.floor_center[1] + doorway.clear_height * 0.5,
                doorway.floor_center[2],
            ];
            colliders.push(StaticCollider::from_center_dimensions(
                center,
                [
                    doorway.wall_thickness,
                    doorway.clear_height,
                    doorway.wall_thickness,
                ],
            ));
        }
        colliders
    }
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct StaticCollider {
    pub(crate) min_x: f32,
    pub(crate) max_x: f32,
    pub(crate) min_y: f32,
    pub(crate) max_y: f32,
    pub(crate) min_z: f32,
    pub(crate) max_z: f32,
}

impl StaticCollider {
    pub(crate) fn from_center_dimensions(center: [f32; 3], dimensions: [f32; 3]) -> Self {
        Self {
            min_x: center[0] - dimensions[0] * 0.5,
            max_x: center[0] + dimensions[0] * 0.5,
            min_y: center[1] - dimensions[1] * 0.5,
            max_y: center[1] + dimensions[1] * 0.5,
            min_z: center[2] - dimensions[2] * 0.5,
            max_z: center[2] + dimensions[2] * 0.5,
        }
    }
}

fn positive(value: f32) -> bool {
    value.is_finite() && value > 0.0
}

fn all_finite(values: &[f32; 3]) -> bool {
    values.iter().all(|value| value.is_finite())
}

fn all_positive(values: &[f32; 3]) -> bool {
    values.iter().all(|value| positive(*value))
}

fn capsule_fits_doorway(capsule: &PlayerCapsule, doorway: &Doorway, tolerance_m: f32) -> bool {
    2.0 * capsule.radius <= doorway.clear_width + tolerance_m
        && capsule.height <= doorway.clear_height + tolerance_m
}

fn capsule_overlaps_collider(
    collider: &StaticCollider,
    capsule_radius: f32,
    capsule_height: f32,
    x: f32,
    z: f32,
) -> bool {
    if collider.max_y <= 0.0 || collider.min_y >= capsule_height {
        return false;
    }
    let closest_x = x.clamp(collider.min_x, collider.max_x);
    let closest_z = z.clamp(collider.min_z, collider.max_z);
    let dx = x - closest_x;
    let dz = z - closest_z;
    dx * dx + dz * dz <= capsule_radius * capsule_radius
}

pub(crate) fn capsule_position_is_clear(
    x: f32,
    z: f32,
    capsule_radius: f32,
    capsule_height: f32,
    colliders: &[StaticCollider],
) -> bool {
    [x, z, capsule_radius, capsule_height]
        .into_iter()
        .all(f32::is_finite)
        && capsule_radius > 0.0
        && capsule_height > 0.0
        && !colliders.iter().any(|collider| {
            capsule_overlaps_collider(collider, capsule_radius, capsule_height, x, z)
        })
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn move_capsule(
    start_x: f32,
    start_z: f32,
    delta_x: f32,
    delta_z: f32,
    capsule_radius: f32,
    capsule_height: f32,
    colliders: &[StaticCollider],
    world_limit: f32,
) -> (f32, f32) {
    if ![
        start_x,
        start_z,
        delta_x,
        delta_z,
        capsule_radius,
        capsule_height,
        world_limit,
    ]
    .into_iter()
    .all(f32::is_finite)
        || capsule_radius <= 0.0
        || capsule_height <= 0.0
        || world_limit <= capsule_radius
    {
        return (start_x, start_z);
    }

    let max_step = (capsule_radius * 0.5).max(0.05);
    let distance = delta_x.abs().max(delta_z.abs());
    let steps = ((distance / max_step).ceil() as usize).clamp(1, 16);
    let step_x = delta_x / steps as f32;
    let step_z = delta_z / steps as f32;
    let coordinate_limit = world_limit - capsule_radius;
    let mut x = start_x.clamp(-coordinate_limit, coordinate_limit);
    let mut z = start_z.clamp(-coordinate_limit, coordinate_limit);

    for _ in 0..steps {
        let next_x = (x + step_x).clamp(-coordinate_limit, coordinate_limit);
        if !colliders.iter().any(|collider| {
            capsule_overlaps_collider(collider, capsule_radius, capsule_height, next_x, z)
        }) {
            x = next_x;
        }

        let next_z = (z + step_z).clamp(-coordinate_limit, coordinate_limit);
        if !colliders.iter().any(|collider| {
            capsule_overlaps_collider(collider, capsule_radius, capsule_height, x, next_z)
        }) {
            z = next_z;
        }
    }
    (x, z)
}

#[cfg(test)]
fn ramp_height_at(ramp: &Ramp, world_z: f32) -> Option<f32> {
    let local_z = world_z - ramp.lower_origin[2];
    if !local_z.is_finite() || !(0.0..=ramp.run).contains(&local_z) {
        return None;
    }
    Some(ramp.lower_origin[1] + ramp.rise * local_z / ramp.run)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> CoordinateFixture {
        let fixture = CoordinateFixture::parse(FIXTURE_JSON).expect("shared fixture parses");
        fixture.validate().expect("shared fixture is valid");
        fixture
    }

    #[test]
    fn shared_fixture_has_one_meter_y_up_world_units() {
        let fixture = fixture();
        assert_eq!(fixture.units, "m");
        assert_eq!(fixture.axes.up, "+y");
        assert_eq!(fixture.axes.forward, "+z");
        assert_eq!(fixture.unit_cube.dimensions, [1.0, 1.0, 1.0]);
    }

    #[test]
    fn capsule_clears_the_doorway_but_does_not_fit_when_offset_too_far() {
        let fixture = fixture();
        assert!(capsule_fits_doorway(
            &fixture.player_capsule,
            &fixture.doorway,
            fixture.tolerance_m
        ));
        let max_center_offset = fixture.doorway.clear_width * 0.5 - fixture.player_capsule.radius;
        assert!((max_center_offset - 0.4).abs() < fixture.tolerance_m);
        assert!(max_center_offset > 0.0);
    }

    #[test]
    fn capsule_collision_uses_meter_scale_in_xz() {
        let fixture = fixture();
        let radius = fixture.player_capsule.radius;
        let cube = StaticCollider::from_center_dimensions(
            fixture.unit_cube.center,
            fixture.unit_cube.dimensions,
        );
        assert!(capsule_overlaps_collider(
            &cube,
            radius,
            fixture.player_capsule.height,
            -0.35,
            0.5
        ));
        assert!(!capsule_overlaps_collider(
            &cube,
            radius,
            fixture.player_capsule.height,
            -0.36,
            0.5
        ));
        assert!(capsule_overlaps_collider(
            &cube,
            radius,
            fixture.player_capsule.height,
            0.5,
            0.5
        ));
    }

    #[test]
    fn capsule_position_clearance_query_detects_fixture_obstacles() {
        let fixture = fixture();
        let colliders = fixture.static_colliders();
        let radius = fixture.player_radius();
        let height = fixture.player_height();

        assert!(capsule_position_is_clear(
            -3.0, -3.0, radius, height, &colliders
        ));
        assert!(!capsule_position_is_clear(
            -0.35, 0.5, radius, height, &colliders
        ));
        assert!(!capsule_position_is_clear(
            f32::NAN,
            0.0,
            radius,
            height,
            &colliders
        ));
    }

    #[test]
    fn movement_stops_at_cube_and_slides_through_doorway() {
        let fixture = fixture();
        let colliders = fixture.static_colliders();
        let radius = fixture.player_radius();
        let height = fixture.player_height();

        let (x, z) = move_capsule(-1.0, 0.5, 2.0, 0.0, radius, height, &colliders, 28.0);
        assert!(
            x > -0.55 && x <= -0.35 + fixture.tolerance_m,
            "blocked at x={x}"
        );
        assert_eq!(z, 0.5);

        let (x, z) = move_capsule(6.0, -1.0, 0.0, 2.0, radius, height, &colliders, 28.0);
        assert_eq!(x, 6.0);
        assert!(z > 1.0, "clear doorway did not pass: z={z}");

        let (_, z) = move_capsule(5.4, -1.0, 0.0, 2.0, radius, height, &colliders, 28.0);
        assert!(z < 0.0, "doorpost did not block: z={z}");
    }

    #[test]
    fn movement_slides_around_cube_corner_without_penetrating() {
        let fixture = fixture();
        let colliders = fixture.static_colliders();
        let radius = fixture.player_radius();
        let height = fixture.player_height();

        let (x, z) = move_capsule(-1.0, 0.5, 1.5, 1.0, radius, height, &colliders, 28.0);

        assert!(capsule_position_is_clear(x, z, radius, height, &colliders));
        assert!(x > -0.35, "movement did not slide past the corner: x={x}");
        assert!(z > 1.35, "movement did not progress along the wall: z={z}");
    }

    #[test]
    fn capsule_does_not_collide_with_geometry_above_its_head() {
        let collider = StaticCollider {
            min_x: -1.0,
            max_x: 1.0,
            min_y: 2.2,
            max_y: 2.5,
            min_z: -1.0,
            max_z: 1.0,
        };
        assert!(!capsule_overlaps_collider(&collider, 0.35, 1.8, 0.0, 0.0));
    }

    #[test]
    fn ramp_collision_height_matches_declared_run_and_rise() {
        let fixture = fixture();
        let start_z = fixture.ramp.lower_origin[2];
        assert_eq!(ramp_height_at(&fixture.ramp, start_z), Some(0.0));
        assert_eq!(ramp_height_at(&fixture.ramp, start_z + 1.5), Some(0.5));
        assert_eq!(ramp_height_at(&fixture.ramp, start_z + 3.0), Some(1.0));
        assert_eq!(ramp_height_at(&fixture.ramp, start_z - 0.01), None);
        assert_eq!(ramp_height_at(&fixture.ramp, start_z + 3.01), None);
    }

    #[test]
    fn fixture_rejects_non_positive_ramp_dimensions() {
        let mut fixture = fixture();
        fixture.ramp.run = 0.0;
        assert_eq!(fixture.validate(), Err("invalid ramp dimensions"));
    }
}
