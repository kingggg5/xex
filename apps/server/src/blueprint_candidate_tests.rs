//! Cross-language candidate checks; never launches a room or changes live content.
use crate::grounded_city::{BlockerInput, CityTraversalInput, GroundedCity, Position};
use serde_json::Value;
use std::{fs, path::PathBuf};

fn input_and_receipt() -> (CityTraversalInput, Value) {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let zones: Value =
        serde_json::from_str(&fs::read_to_string(root.join("content/source/zones.json")).unwrap())
            .unwrap();
    let mut input: CityTraversalInput =
        serde_json::from_value(zones["zones"][0]["city_traversal"].clone()).unwrap();
    let receipt: Value = serde_json::from_str(
        &fs::read_to_string(
            root.join("planning/evidence/blueprint-p0-20261003/collision-addon-candidate.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let blockers: Vec<BlockerInput> = serde_json::from_value(receipt["blockers"].clone()).unwrap();
    input.blockers.extend(blockers);
    (input, receipt)
}

fn compare(p: Position, expected: &Value, label: &str) {
    for (axis, actual) in [("x", p.x), ("y", p.y), ("z", p.z)] {
        let expected = expected[axis].as_f64().unwrap() as f32;
        assert!(
            (actual - expected).abs() <= 0.00005,
            "{label}/{axis}: {actual} != {expected}"
        );
    }
}

#[test]
fn blueprint_candidate_matches_client_aprons_prop_faces_and_mound_edges() {
    let (input, receipt) = input_and_receipt();
    let field = GroundedCity::parse(&input, 308.0).unwrap();
    let checks = receipt["checks"].as_array().unwrap();
    assert_eq!(checks.len(), 18);
    for check in checks {
        let label = check["label"].as_str().unwrap();
        let radius = check["radius"].as_f64().unwrap() as f32;
        if label.ends_with("-side") {
            let x = if label.starts_with("market") {
                -12.0
            } else {
                24.0
            };
            let mut p = Position { x, y: 0.0, z: 7.0 };
            for _ in 0..20 {
                p = field.move_capsule(p, 0.0, 0.25, radius, 1.8, &[], 308.0);
            }
            compare(p, &check["approach"], label);
            for _ in 0..20 {
                p = field.move_capsule(p, 0.0, -0.25, radius, 1.8, &[], 308.0);
            }
            compare(p, &check["returned"], label);
        } else if label.ends_with("-front") {
            let x = if label.starts_with("market") {
                -17.0
            } else {
                21.0
            };
            let mut p = Position { x, y: 0.0, z: 5.0 };
            for _ in 0..25 {
                p = field.move_capsule(p, 0.0, 0.2, radius, 1.8, &[], 308.0);
            }
            compare(p, &check["blocked"], label);
            assert!(p.z < 9.0 - radius);
        } else {
            let edge = label
                .strip_prefix("mound-edge-")
                .unwrap()
                .parse::<usize>()
                .unwrap();
            let poly = [
                [18.0_f64, -84.0],
                [43.0, -80.0],
                [46.0, -104.0],
                [12.0, -104.0],
                [12.0, -92.0],
            ];
            let a = poly[edge];
            let b = poly[(edge + 1) % poly.len()];
            let mid = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0];
            let dx = 30.0 - mid[0];
            let dz = -94.0 - mid[1];
            let length = dx.hypot(dz);
            let ux = dx / length;
            let uz = dz / length;
            let exact_radius = check["radius"].as_f64().unwrap();
            let mut p = Position {
                x: (mid[0] - ux * (exact_radius + 0.6)) as f32,
                y: 0.0,
                z: (mid[1] - uz * (exact_radius + 0.6)) as f32,
            };
            for _ in 0..6 {
                p = field.move_capsule(
                    p,
                    (ux * 0.2) as f32,
                    (uz * 0.2) as f32,
                    radius,
                    1.8,
                    &[],
                    308.0,
                );
            }
            compare(p, &check["blocked"], label);
        }
    }
    println!(
        "BLUEPRINT_RUST_CLIENT_PARITY: 18/18 canonical candidate checks PASS; no live server qualification"
    );
}
