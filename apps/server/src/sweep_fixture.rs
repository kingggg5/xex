//! Explicit local 500-session fixture. No HTTP bypass or normal auth-limit change.
use crate::auth::AuthManager;
use std::{
    fs::OpenOptions,
    net::{IpAddr, Ipv4Addr, SocketAddr},
    path::{Component, Path, PathBuf},
    time::Instant,
};

pub struct FixtureConfig {
    path: PathBuf,
    allowed: PathBuf,
}
pub fn from_environment() -> Result<Option<FixtureConfig>, &'static str> {
    let count = std::env::var("AETHERFIELD_SWEEP_SESSIONS").ok();
    let file = std::env::var_os("AETHERFIELD_SWEEP_SESSION_FILE").map(PathBuf::from);
    if count.is_none() && file.is_none() {
        return Ok(None);
    }
    let profile = std::env::var("AETHERFIELD_SWEEP_PROFILE").as_deref() == Ok("1");
    let port = std::env::var("AETHERFIELD_PORT")
        .ok()
        .and_then(|p| p.parse::<u16>().ok())
        .unwrap_or(3001);
    let allowed = PathBuf::from(std::env::var_os("USERPROFILE").ok_or("missing_user_profile")?)
        .join("Downloads/Xexoria-Game/agent-output/20261002-go-server");
    FixtureConfig::validate(
        profile,
        count.as_deref(),
        file.as_deref(),
        std::env::var_os("AETHERFIELD_DATABASE_URL").is_some(),
        SocketAddr::from(([127, 0, 0, 1], port)),
        &allowed,
    )
}
impl FixtureConfig {
    fn validate(
        profile: bool,
        count: Option<&str>,
        file: Option<&Path>,
        database_configured: bool,
        bind: SocketAddr,
        allowed: &Path,
    ) -> Result<Option<Self>, &'static str> {
        if !profile {
            return Err("profile_flag_required");
        }
        if count != Some("500") {
            return Err("exact_count_required");
        }
        if database_configured {
            return Err("database_must_be_disabled");
        }
        if bind.ip() != IpAddr::V4(Ipv4Addr::LOCALHOST) || bind.port() != 3922 {
            return Err("private_bind_required");
        }
        let file = file.ok_or("explicit_file_required")?;
        if !file.is_absolute() || file.components().any(|c| matches!(c, Component::ParentDir)) {
            return Err("absolute_scoped_file_required");
        }
        let allowed = allowed
            .canonicalize()
            .map_err(|_| "private_directory_required")?;
        let parent = file
            .parent()
            .ok_or("file_parent_required")?
            .canonicalize()
            .map_err(|_| "existing_private_parent_required")?;
        if !parent.starts_with(&allowed) {
            return Err("file_outside_private_scope");
        }
        let path = parent.join(file.file_name().ok_or("file_name_required")?);
        if path.exists() {
            return Err("exclusive_new_file_required");
        }
        Ok(Some(Self { path, allowed }))
    }
    pub fn create_auth(&self) -> Result<AuthManager, &'static str> {
        // Exclusive creation precedes any credential generation or table seed.
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&self.path)
            .map_err(|_| "exclusive_file_create_failed")?;
        let result = (|| {
            let (manager, rows) = AuthManager::disposable_guests_for_local_sweep(Instant::now())
                .map_err(|_| "credential_generation_failed")?;
            serde_json::to_writer(&mut file, &rows).map_err(|_| "private_file_write_failed")?;
            file.sync_all().map_err(|_| "private_file_sync_failed")?;
            Ok(manager)
        })();
        drop(file);
        if result.is_err()
            && self
                .path
                .parent()
                .and_then(|p| p.canonicalize().ok())
                .is_some_and(|p| p.starts_with(&self.allowed))
        {
            let _ = std::fs::remove_file(&self.path);
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn base() -> PathBuf {
        let p = std::env::temp_dir()
            .join(format!("xexoria-fixture-guard-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&p).unwrap();
        p
    }
    #[test]
    fn fixture_guards_deny_before_seed_or_file_write() {
        let base = base();
        let path = base.join("new.json");
        let addr = "127.0.0.1:3922".parse().unwrap();
        for (profile, count, db, bind) in [
            (false, Some("500"), false, addr),
            (true, None, false, addr),
            (true, Some("499"), false, addr),
            (true, Some("500"), true, addr),
            (true, Some("500"), false, "0.0.0.0:3922".parse().unwrap()),
            (true, Some("500"), false, "127.0.0.1:3001".parse().unwrap()),
        ] {
            assert!(FixtureConfig::validate(profile, count, Some(&path), db, bind, &base).is_err());
            assert!(!path.exists());
        }
        assert!(
            FixtureConfig::validate(
                true,
                Some("500"),
                Some(Path::new("relative.json")),
                false,
                addr,
                &base
            )
            .is_err()
        );
        let outside = base.parent().unwrap().join("outside-new.json");
        assert!(
            FixtureConfig::validate(true, Some("500"), Some(&outside), false, addr, &base).is_err()
        );
        std::fs::write(&path, b"owned-test-sentinel").unwrap();
        assert!(
            FixtureConfig::validate(true, Some("500"), Some(&path), false, addr, &base).is_err()
        );
        assert!(std::fs::read(&path).unwrap() == b"owned-test-sentinel");
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(base).unwrap();
    }
    #[test]
    fn exclusive_create_race_never_seeds_or_overwrites_existing_file() {
        let base = base();
        let path = base.join("race.json");
        let config = FixtureConfig::validate(
            true,
            Some("500"),
            Some(&path),
            false,
            "127.0.0.1:3922".parse().unwrap(),
            &base,
        )
        .unwrap()
        .unwrap();
        std::fs::write(&path, b"owned-test-sentinel").unwrap();
        assert!(config.create_auth().is_err());
        assert!(std::fs::read(&path).unwrap() == b"owned-test-sentinel");
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(base).unwrap();
    }
}
