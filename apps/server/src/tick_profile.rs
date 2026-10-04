//! Opt-in exact-window profiling for normal channels; never an auth bypass.
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
#[derive(Clone, Copy, Default)]
pub struct TransportSample {
    pub confirmed_frame_bytes: u64,
    pub published_snapshot_bytes: u64,
    pub oldest_pending_queue_age_us: u64,
    pub pending_packets: usize,
    pub shared_encodes: u64,
    pub shared_hits: u64,
    pub record_encodes: u64,
    pub essential_event_overflows: u64,
    pub retained_baselines: usize,
    pub shared_states: usize,
    pub encode_stages_ms: [f64; 4],
    pub delta_comparisons: u64,
    pub unchanged_record_skips: u64,
    pub record_key_constructions: u64,
    pub key_bytes_copied: u64,
    pub ordinary_cache_hits: u64,
    pub ordinary_cache_refreshes: u64,
}

#[derive(Clone, Copy)]
struct Sample {
    seq: u64,
    work_ms: f64,
    interval_ms: Option<f64>,
    phases: [f64; 3],
    transport: TransportSample,
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
        self.record_with_transport(tick_started, work, phases, TransportSample::default());
    }
    pub fn record_with_transport(
        &self,
        tick_started: Instant,
        work: Duration,
        phases: [Duration; 3],
        transport: TransportSample,
    ) {
        let mut inner = self
            .inner
            .lock()
            .unwrap_or_else(|poison| poison.into_inner());
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
            transport,
        });
        while inner.samples.len() > 4096 {
            inner.samples.pop_front();
        }
    }
    /// A baseline GET has no `after`. A final GET uses baseline.end_seq.
    /// Endpoints are loopback-only and opt-in; validate run_token <=64 ASCII.
    pub fn window(&self, after: Option<u64>, run_token: &str) -> Value {
        let inner = self
            .inner
            .lock()
            .unwrap_or_else(|poison| poison.into_inner());
        let end = inner.seq;
        let begin = after.unwrap_or(end);
        let values = inner
            .samples
            .iter()
            .filter(|s| s.seq > begin)
            .copied()
            .collect::<Vec<_>>();
        drop(inner);
        let missing = begin > end || values.len() as u64 != end.saturating_sub(begin);
        let work = percentiles(values.iter().map(|s| s.work_ms).collect());
        let wall = percentiles(values.iter().filter_map(|s| s.interval_ms).collect());
        let phases = (0..3)
            .map(|i| percentiles(values.iter().map(|s| s.phases[i]).collect()))
            .collect::<Vec<_>>();
        let confirmed = values
            .iter()
            .map(|s| s.transport.confirmed_frame_bytes)
            .sum::<u64>();
        let published = values
            .iter()
            .map(|s| s.transport.published_snapshot_bytes)
            .sum::<u64>();
        let window_ms = values.iter().filter_map(|s| s.interval_ms).sum::<f64>();
        let encode_stages = (0..4)
            .map(|index| {
                percentiles(
                    values
                        .iter()
                        .map(|s| s.transport.encode_stages_ms[index])
                        .collect(),
                )
            })
            .collect::<Vec<_>>();
        let transport = json!({"confirmed_websocket_frame_bytes":confirmed,"published_snapshot_bytes":published,"elapsed_window_ms":window_ms,"egress_websocket_mbit_per_s":if window_ms>0.0{Some(confirmed as f64*8.0/window_ms/1000.0)}else{None},"oldest_pending_queue_age_us":values.iter().map(|s|s.transport.oldest_pending_queue_age_us).max(),"pending_outbound_packets_max":values.iter().map(|s|s.transport.pending_packets).max(),"shared_encodes":values.iter().map(|s|s.transport.shared_encodes).sum::<u64>(),"shared_hits":values.iter().map(|s|s.transport.shared_hits).sum::<u64>(),"record_encodes":values.iter().map(|s|s.transport.record_encodes).sum::<u64>(),"essential_event_overflows":values.iter().map(|s|s.transport.essential_event_overflows).sum::<u64>(),"retained_baselines_max":values.iter().map(|s|s.transport.retained_baselines).max(),"shared_states_max":values.iter().map(|s|s.transport.shared_states).max(),"encode_stages_ms":{"prepare":encode_stages[0],"selection":encode_stages[1],"packet":encode_stages[2],"publish_watch":encode_stages[3]},"delta_comparisons":values.iter().map(|s|s.transport.delta_comparisons).sum::<u64>(),"unchanged_record_skips":values.iter().map(|s|s.transport.unchanged_record_skips).sum::<u64>(),"record_key_constructions":values.iter().map(|s|s.transport.record_key_constructions).sum::<u64>(),"key_bytes_copied":values.iter().map(|s|s.transport.key_bytes_copied).sum::<u64>(),"ordinary_cache_hits":values.iter().map(|s|s.transport.ordinary_cache_hits).sum::<u64>(),"ordinary_cache_refreshes":values.iter().map(|s|s.transport.ordinary_cache_refreshes).sum::<u64>(),"allocation_scope":"logical key constructions and copied key bytes; not an allocator profiler","byte_scope":"completed socket writes, WebSocket payload plus frame header, all message types; TCP/IP overhead unmeasured"});
        json!({"schema":"xexoria.tick-profile/1","instance_id":self.instance,"room_index":self.room_index,"run_token":run_token,"after_seq":begin,"end_seq":end,"sample_count":values.len(),"lost_samples":missing,"cpu_ms":work,"wall_ms":wall,"phases_ms":{"commands":phases[0],"world_advance":phases[1],"publish_encode":phases[2]},"transport":transport,"cpu_method":"elapsed room-owner work excluding timer wait","wall_method":"interval between room-owner work starts","budget":{"p95_work_ms":33.3,"pass":!missing&&work["p95"].as_f64().is_some_and(|p|p<=33.3)}})
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
