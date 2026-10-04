use serde::Serialize;
use serde_json::{Value, json};

pub const MAX_SAMPLES: usize = 8192;
#[derive(Clone, Debug, Serialize)]
pub struct Summary {
    pub n: usize,
    pub p50: f64,
    pub p95: f64,
    pub p99: f64,
    pub max: f64,
    pub mean: f64,
}
#[derive(Clone, Debug, Default)]
pub struct Samples {
    values: Vec<f64>,
    dropped: u64,
}
impl Samples {
    pub fn push(&mut self, value: f64) {
        if !value.is_finite() || value < 0.0 || self.values.len() >= MAX_SAMPLES {
            self.dropped += 1;
            return;
        }
        self.values.push(value);
    }
    pub fn summary(&self) -> Option<Summary> {
        summary(&self.values)
    }
    pub fn values(&self) -> &[f64] {
        &self.values
    }
    pub fn dropped(&self) -> u64 {
        self.dropped
    }
}
pub fn summary(values: &[f64]) -> Option<Summary> {
    if values.is_empty() {
        return None;
    }
    let mut ordered = values.to_vec();
    ordered.sort_by(f64::total_cmp);
    let p =
        |q: f64| ordered[((q * ordered.len() as f64).ceil() as usize).clamp(1, ordered.len()) - 1];
    Some(Summary {
        n: ordered.len(),
        p50: p(0.5),
        p95: p(0.95),
        p99: p(0.99),
        max: ordered[ordered.len() - 1],
        mean: ordered.iter().sum::<f64>() / ordered.len() as f64,
    })
}
#[derive(Clone, Debug, Default, Serialize)]
pub struct Counters {
    pub rx_messages: u64,
    pub rx_bytes: u64,
    pub rx_ws_estimated_bytes: u64,
    pub tx_messages: u64,
    pub tx_bytes: u64,
    pub snapshots: u64,
    pub full_snapshots: u64,
    pub delta_snapshots: u64,
    pub resyncs: u64,
    pub codec_errors: u64,
    pub action_accepted: u64,
    pub action_rejected: u64,
    pub combat_events: u64,
}
#[derive(Clone, Debug, Serialize)]
pub struct SafeError {
    pub phase: String,
    pub code: String,
}
#[derive(Clone, Debug, Default)]
pub struct BotMetrics {
    pub counters: Counters,
    pub receive_gap: Samples,
    pub rtt: Samples,
    pub age: Samples,
    pub errors: Vec<SafeError>,
    pub negative_age_estimates: u64,
    pub zone_transfers: u64,
    pub party_joined: bool,
    pub control_lag: Samples,
}
impl BotMetrics {
    pub fn add_error(&mut self, phase: &str, code: &str) {
        if self.errors.len() < 32 {
            let clean = |s: &str| {
                s.chars()
                    .filter(|c| c.is_ascii_alphanumeric() || "_-.:".contains(*c))
                    .take(80)
                    .collect()
            };
            self.errors.push(SafeError {
                phase: clean(phase),
                code: clean(code),
            });
        }
    }
    pub fn report(&self, index: usize, admitted: bool) -> Value {
        let sample = |s: &Samples| json!({"summary":s.summary(),"dropped":s.dropped()});
        json!({"bot_index":index,"admitted":admitted,"counters":self.counters,"rtt_ms":sample(&self.rtt),
            "estimated_snapshot_age_ms":sample(&self.age),"snapshot_receive_gap_ms":sample(&self.receive_gap),
            "driver_control_lag_ms":sample(&self.control_lag),"negative_age_estimates":self.negative_age_estimates,
            "zone_transfers":self.zone_transfers,"party_joined":self.party_joined,"errors":self.errors})
    }
}
pub fn summarize_samples<'a>(samples: impl IntoIterator<Item = &'a Samples>) -> Value {
    let mut all = Vec::new();
    let mut dropped = 0;
    for (index, s) in samples.into_iter().enumerate() {
        if index >= 500 {
            dropped += s.values().len() as u64 + s.dropped();
            continue;
        }
        all.extend_from_slice(s.values());
        dropped += s.dropped();
    }
    json!({"summary":summary(&all),"dropped":dropped,"coverage_complete":dropped==0})
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn percentiles_and_empty() {
        assert!(Samples::default().summary().is_none());
        let mut s = Samples::default();
        for i in 1..=100 {
            s.push(i as f64)
        }
        let d = s.summary().unwrap();
        assert_eq!((d.p50, d.p95, d.p99), (50., 95., 99.));
    }
    #[test]
    fn cap_is_explicit() {
        let mut s = Samples::default();
        s.push(f64::NAN);
        for _ in 0..MAX_SAMPLES + 1 {
            s.push(1.)
        }
        assert_eq!(s.values().len(), MAX_SAMPLES);
        assert_eq!(s.dropped(), 2);
    }
    #[test]
    fn aggregation_does_not_silently_keep_only_first_bot() {
        let mut a = Samples::default();
        let mut b = Samples::default();
        for _ in 0..MAX_SAMPLES {
            a.push(1.);
            b.push(100.)
        }
        let r = summarize_samples([&a, &b]);
        assert_eq!(r["summary"]["n"], MAX_SAMPLES * 2);
        assert_eq!(r["summary"]["p95"], 100.);
    }
}
