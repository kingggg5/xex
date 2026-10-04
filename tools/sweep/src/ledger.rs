use serde_json::{Value, json};
use std::{
    fs::{OpenOptions, create_dir_all},
    io::{Read, Seek, SeekFrom, Write},
    path::Path,
};

pub fn ledger_row(report: &Value) -> Result<Value, String> {
    for key in ["run_id", "ts", "scenario"] {
        if report[key].as_str().is_none() {
            return Err(format!("missing {key}"));
        }
    }
    let valid = report["preflight_valid"].as_bool().unwrap_or(false);
    let profile = report
        .get("server_profile")
        .filter(|p| p["verified"].as_bool() == Some(true));
    let cap = report["capacity_limited"].as_bool() == Some(true);
    Ok(
        json!({"schema":"xexoria.ledger/1","run_id":report["run_id"],"ts":report["ts"],
        "build":report["build"],"scenario":report["scenario"],"scene":null,"view":null,"time":null,
        "device_class":report["device_class"].as_str().unwrap_or("server-unknown"),"backend":"server",
        "viewport":null,"render":null,"tier":null,"upscaling":null,"browser":null,
        "settings":{"clock":"real","warmup_seconds":report["warmup_s"],"duration_seconds":report["duration_s"],"tick_hz":20},
        "preflight":{"valid":valid,"invalid":if valid{json!([])}else{json!([if cap{"CAPACITY_LIMIT"}else{"SWEEP_INVALID"}])},"warnings":report["warnings"]},
        "frames":{"n":profile.map(|p|&p["sample_count"]),"wall_ms":profile.map(|p|&p["wall_ms"]),"cpu_ms":profile.map(|p|&p["cpu_ms"]),"gpu_ms":null,"hitches50":null,"hitches100":null,"fps":null},
        "counts":{"draws":null,"tris":null,"active_meshes":null,"particles":null,"tex_mib":null,"heap_mib":null},"noise_floor":null,
        "verdict":{"capture":if valid{"OK"}else if cap{"CAPACITY_LIMIT"}else{"INVALID_RUN"},"pass":valid&&report["budgets_pass"].as_bool()==Some(true),"results":report["budget_results"]},
        "artifacts":{"image":null,"image_sha256":null,"shot_json":report["artifact"],"sheet":null},
        "network":report["network"],"sweep":{"requested":report["requested"],"admitted":report["admitted"],"connected_at_end":report["connected_at_end"],"protocol":report["protocol"],"zone":report["zone"]}}),
    )
}
pub fn append_row(path: &Path, row: &Value) -> Result<(), String> {
    if row["schema"].as_str() != Some("xexoria.ledger/1") {
        return Err("unsupported ledger schema".into());
    }
    let mut line = serde_json::to_vec(row).map_err(|_| "ledger serialization")?;
    if line.len() > 128 * 1024 {
        return Err("ledger row exceeds128KiB".into());
    }
    line.push(b'\n');
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .read(true)
        .open(path)
        .map_err(|e| e.to_string())?;
    if file.metadata().map_err(|e| e.to_string())?.len() > 0 {
        file.seek(SeekFrom::End(-1)).map_err(|e| e.to_string())?;
        let mut last = [0];
        file.read_exact(&mut last).map_err(|e| e.to_string())?;
        if last[0] != b'\n' {
            return Err("existing ledger has an incomplete final row; refused append".into());
        }
    }
    file.write_all(&line)
        .and_then(|_| file.flush())
        .map_err(|e| e.to_string())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn absent_tick_profile_is_never_network_latency() {
        let r=ledger_row(&json!({"run_id":"r","ts":"t","scenario":"idle","preflight_valid":true,"network":{"rtt_ms":1}})).unwrap();
        assert!(r["frames"]["cpu_ms"].is_null());
        assert!(r["frames"]["wall_ms"].is_null());
        assert!(r["frames"]["gpu_ms"].is_null());
    }
    #[test]
    fn failure_is_not_hidden() {
        let r =
            ledger_row(&json!({"run_id":"r","ts":"t","scenario":"idle","capacity_limited":true}))
                .unwrap();
        assert_eq!(r["verdict"]["capture"], "CAPACITY_LIMIT");
        assert_eq!(r["preflight"]["valid"], false);
    }
    #[test]
    fn append_only_and_truncated_tail_refused() {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("evidence/tests");
        create_dir_all(&dir).unwrap();
        let path = dir.join(format!("{}.jsonl", uuid::Uuid::new_v4()));
        let row = json!({"schema":"xexoria.ledger/1","message":"a\nb"});
        append_row(&path, &row).unwrap();
        append_row(&path, &row).unwrap();
        assert_eq!(std::fs::read_to_string(&path).unwrap().lines().count(), 2);
        std::fs::write(&path, b"broken").unwrap();
        assert!(append_row(&path, &row).is_err());
        std::fs::remove_file(path).unwrap();
    }
}
