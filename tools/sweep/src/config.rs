use reqwest::Url;
use std::{net::IpAddr, path::PathBuf};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Scenario {
    Idle,
    Wander,
    PartyCombat,
    ZoneChange,
}
impl Scenario {
    pub fn name(self) -> &'static str {
        match self {
            Self::Idle => "idle",
            Self::Wander => "wander",
            Self::PartyCombat => "party-combat",
            Self::ZoneChange => "zone-change",
        }
    }
}
#[derive(Clone, Debug)]
pub struct Config {
    pub server: Url,
    pub origin: String,
    pub counts: Vec<usize>,
    pub scenarios: Vec<Scenario>,
    pub duration_s: u64,
    pub warmup_s: u64,
    pub channel: u16,
    pub protocol: u8,
    pub auto_protocol: bool,
    pub ramp_ms: u64,
    pub ledger: PathBuf,
    pub output: PathBuf,
    pub sessions: Option<PathBuf>,
    pub profile_path: Option<String>,
    pub run_label: String,
    pub ignore_gpu_lock: bool,
}
pub const HELP: &str = "xexoria-sweep --server http://127.0.0.1:3921 --origin http://127.0.0.1:5173\n  --counts 10,50,100,250,500 --scenarios idle,wander,party-combat,zone-change\n  --duration 15 --warmup 3 --channel 0 --protocol auto|7|8 --ramp-ms 250\n  --ledger planning/perf-ledger.jsonl --out tools/sweep/evidence\n  --sessions-file <local JSON test-cookie array> --profile-path /__sweep/profile\n  --label <safe-name> --allow-gpu-lock (explicitly permits CPU load during another capture)\nLoopback only. Defaults never disable server auth/admission limits. Scenario sweeps reuse bots; no hundreds of new sessions after each case.";
pub fn local_url(value: &str) -> Result<Url, String> {
    let url = Url::parse(value).map_err(|_| "invalid server URL")?;
    if url.scheme() != "http"
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != "/"
    {
        return Err("server must be a plain loopback http base URL".into());
    }
    let h = url.host_str().ok_or("server host missing")?;
    if h != "localhost"
        && !h
            .trim_matches(['[', ']'])
            .parse::<IpAddr>()
            .is_ok_and(|ip| ip.is_loopback())
    {
        return Err("non-loopback server refused".into());
    }
    Ok(url)
}
impl Config {
    pub fn parse(args: impl IntoIterator<Item = String>) -> Result<Option<Self>, String> {
        let mut c = Self {
            server: local_url("http://127.0.0.1:3921")?,
            origin: "http://127.0.0.1:5173".into(),
            counts: vec![10, 50, 100, 250, 500],
            scenarios: vec![
                Scenario::Idle,
                Scenario::Wander,
                Scenario::PartyCombat,
                Scenario::ZoneChange,
            ],
            duration_s: 15,
            warmup_s: 3,
            channel: 0,
            protocol: 8,
            auto_protocol: true,
            ramp_ms: 250,
            ledger: PathBuf::from("planning/perf-ledger.jsonl"),
            output: PathBuf::from("tools/sweep/evidence"),
            sessions: None,
            profile_path: None,
            run_label: "sweep".into(),
            ignore_gpu_lock: false,
        };
        let mut args = args.into_iter();
        while let Some(flag) = args.next() {
            if flag == "--help" || flag == "-h" {
                return Ok(None);
            }
            if flag == "--allow-gpu-lock" {
                c.ignore_gpu_lock = true;
                continue;
            }
            let value = args
                .next()
                .ok_or_else(|| format!("missing value for{flag}"))?;
            match flag.as_str() {
                "--server" => c.server = local_url(&value)?,
                "--origin" => {
                    let u = local_url(&value)?;
                    c.origin = u.origin().ascii_serialization();
                }
                "--counts" => {
                    c.counts = value
                        .split(',')
                        .map(|v| v.parse::<usize>().map_err(|_| "invalid count".to_string()))
                        .collect::<Result<_, _>>()?;
                    if c.counts.is_empty()
                        || c.counts.len() > 5
                        || c.counts.iter().any(|n| *n == 0 || *n > 500)
                        || c.counts.windows(2).any(|v| v[0] >= v[1])
                    {
                        return Err(
                            "counts must be ascending distinct integers1..500, at most5".into()
                        );
                    }
                }
                "--scenarios" => {
                    c.scenarios = value
                        .split(',')
                        .map(|v| match v {
                            "idle" => Ok(Scenario::Idle),
                            "wander" => Ok(Scenario::Wander),
                            "party-combat" => Ok(Scenario::PartyCombat),
                            "zone-change" => Ok(Scenario::ZoneChange),
                            _ => Err("invalid scenario".to_string()),
                        })
                        .collect::<Result<_, _>>()?;
                    if c.scenarios.is_empty() || c.scenarios.len() > 4 {
                        return Err("at most4 scenarios".into());
                    }
                }
                "--duration" => c.duration_s = value.parse().map_err(|_| "invalid duration")?,
                "--warmup" => c.warmup_s = value.parse().map_err(|_| "invalid warmup")?,
                "--channel" => c.channel = value.parse().map_err(|_| "invalid channel")?,
                "--protocol" => {
                    c.auto_protocol = value == "auto";
                    if !c.auto_protocol {
                        c.protocol = value.parse().map_err(|_| "invalid protocol")?;
                    }
                }
                "--ramp-ms" => c.ramp_ms = value.parse().map_err(|_| "invalid ramp")?,
                "--ledger" => c.ledger = PathBuf::from(value),
                "--out" => c.output = PathBuf::from(value),
                "--sessions-file" => c.sessions = Some(PathBuf::from(value)),
                "--profile-path" => {
                    if !value.starts_with('/')
                        || value.starts_with("//")
                        || value.contains(['?', '#'])
                    {
                        return Err("profile must be a local absolute path".into());
                    }
                    c.profile_path = Some(value)
                }
                "--label" => {
                    if value.is_empty()
                        || value.len() > 64
                        || !value
                            .bytes()
                            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
                    {
                        return Err("label must be64 safe ASCII characters".into());
                    }
                    c.run_label = value;
                }
                _ => return Err(format!("unknown option{flag}")),
            }
        }
        if !(1..=120).contains(&c.duration_s)
            || c.warmup_s > 30
            || c.channel >= 20
            || !(7..=8).contains(&c.protocol)
            || !(50..=5000).contains(&c.ramp_ms)
        {
            return Err(
                "duration1..120,warmup0..30,channel0..19,protocol7/8,ramp50..5000ms required"
                    .into(),
            );
        }
        Ok(Some(c))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn external_and_credentials_refused() {
        for u in [
            "https://127.0.0.1/",
            "http://example.com/",
            "http://u:p@localhost/",
            "http://localhost/?key=x",
        ] {
            assert!(local_url(u).is_err());
        }
        assert!(local_url("http://[::1]:3921").is_ok());
    }
    #[test]
    fn bounds() {
        assert!(Config::parse(["--counts", "500,10"].map(str::to_string)).is_err());
        assert!(
            Config::parse(["--counts", "10", "--duration", "1"].map(str::to_string))
                .unwrap()
                .is_some()
        );
    }
}
