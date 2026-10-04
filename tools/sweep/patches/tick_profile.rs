//! PROPOSAL ONLY: root may copy into apps/server/src/tick_profile.rs.
//! Record elapsed room-owner spans, not process CPU time or network latency.
use serde_json::{Value, json};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
#[derive(Clone)]
pub struct TickProfile {
    inner: Arc<Mutex<Inner>>,
    room_index: u16,
    instance: String,
}
struct Inner {
    seq: u64,
    last_tick: Option<Instant>,
    samples: VecDeque<Sample>,
}
struct Sample {
    seq: u64,
    work_ms: f64,
    interval_ms: Option<f64>,
    phases: [f64; 3],
}
impl TickProfile {
    pub fn new(room_index: u16) -> Self {
        Self {
            inner: Arc::new(Mutex::new(Inner {
                seq: 0,
                last_tick: None,
                samples: VecDeque::new(),
            })),
            room_index,
            instance: uuid::Uuid::new_v4().to_string(),
        }
    }
    /// Caller owns one room; phase spans: command drain, world.advance,
    /// publish/encode. Never include the 50ms timer wait in work_ms.
    pub fn record(&self, tick_started: Instant, work: Duration, phases: [Duration; 3]) {
        let mut inner = self.inner.lock().unwrap();
        inner.seq += 1;
        let interval = inner
            .last_tick
            .and_then(|t| tick_started.checked_duration_since(t))
            .map(|d| d.as_secs_f64() * 1000.0);
        inner.last_tick = Some(tick_started);
        let seq = inner.seq;
        inner.samples.push_back(Sample {
            seq,
            work_ms: work.as_secs_f64() * 1000.0,
            interval_ms: interval,
            phases: phases.map(|d| d.as_secs_f64() * 1000.0),
        });
        while inner.samples.len() > 4096 {
            inner.samples.pop_front();
        }
    }
    /// A baseline GET has no `after`. A final GET uses baseline.end_seq.
    /// Endpoints are loopback-only and opt-in; validate run_token <=64 ASCII.
    pub fn window(&self, after: Option<u64>, run_token: &str) -> Value {
        let inner = self.inner.lock().unwrap();
        let end = inner.seq;
        let begin = after.unwrap_or(end);
        let values = inner
            .samples
            .iter()
            .filter(|s| s.seq > begin)
            .collect::<Vec<_>>();
        let missing = begin > end || values.len() as u64 != end.saturating_sub(begin);
        let work = percentiles(values.iter().map(|s| s.work_ms).collect());
        let wall = percentiles(values.iter().filter_map(|s| s.interval_ms).collect());
        let phases = (0..3)
            .map(|i| percentiles(values.iter().map(|s| s.phases[i]).collect()))
            .collect::<Vec<_>>();
        json!({"schema":"xexoria.tick-profile/1","instance_id":self.instance,"room_index":self.room_index,"run_token":run_token,"after_seq":begin,"end_seq":end,"sample_count":values.len(),"lost_samples":missing,"cpu_ms":work,"wall_ms":wall,"phases_ms":{"commands":phases[0],"world_advance":phases[1],"publish_encode":phases[2]},"cpu_method":"elapsed room-owner work excluding timer wait","wall_method":"interval between room-owner work starts","budget":{"p95_work_ms":33.3,"pass":!missing&&work["p95"].as_f64().is_some_and(|p|p<=33.3)}})
    }
}
fn percentiles(mut values: Vec<f64>) -> Value {
    if values.is_empty() {
        return Value::Null;
    }
    values.sort_by(f64::total_cmp);
    let p = |q: f64| values[((q * values.len() as f64).ceil() as usize).clamp(1, values.len()) - 1];
    json!({"p50":p(0.5),"p95":p(0.95),"p99":p(0.99)})
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_window_and_loss() {
        let p = TickProfile::new(0);
        let start = Instant::now();
        let mark = p.window(None, "t");
        for i in 0..4 {
            p.record(
                start + Duration::from_millis(i * 50),
                Duration::from_millis(i + 1),
                [Duration::ZERO; 3],
            );
        }
        let window = p.window(mark["end_seq"].as_u64(), "t");
        assert_eq!(window["sample_count"], 4);
        assert_eq!(window["cpu_ms"]["p95"], 4.0);
        assert_eq!(window["wall_ms"]["p95"], 50.0);
        assert_eq!(window["lost_samples"], false);
        for i in 4..4102 {
            p.record(
                start + Duration::from_millis(i * 50),
                Duration::ZERO,
                [Duration::ZERO; 3],
            );
        }
        assert_eq!(p.window(Some(0), "t")["lost_samples"], true);
    }
}
