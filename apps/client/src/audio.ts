/**
 * Procedural Web Audio engine for combat and ability sound effects.
 * Synthesizes all sounds at runtime with oscillators and noise buffers:
 * zero external audio samples or network fetches (0 THB rule).
 */

function createNoiseBuffer(ctx: BaseAudioContext, seconds = 0.5): AudioBuffer {
	const length = Math.floor(ctx.sampleRate * seconds);
	const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
	const data = buffer.getChannelData(0);
	let last = 0;
	// Pink-ish noise filter for richer whoosh and impact bodies
	for (let i = 0; i < length; i++) {
		const white = Math.random() * 2 - 1;
		last = (last + 0.02 * white) / 1.02;
		data[i] = last * 3.5;
	}
	return buffer;
}

export class CombatAudio {
	private ctx: AudioContext | null = null;
	private masterGain: GainNode | null = null;
	private noiseBuffer: AudioBuffer | null = null;
	private muted = false;
	private unlocked = false;
	private disposed = false;
	private readonly activationEvents = new AbortController();
	private pendingResume: Promise<void> | null = null;
	private mageVoices=0;

	constructor() {
		if (typeof window === "undefined") return;
		const unlock = () => this.ensureUnlocked(true);
		// Touch down/start is not an activating gesture on iOS. Retain listeners so an interrupted context can recover.
		for (const type of ['touchend','pointerup','click','keydown']) window.addEventListener(type,unlock,{passive:true,signal:this.activationEvents.signal});
		window.addEventListener('pagehide',()=>this.dispose(),{signal:this.activationEvents.signal});
	}

	private ensureUnlocked(activation = false): void {
		if (this.disposed) return;
		if (this.unlocked && this.ctx && this.ctx.state === "running") return;
		try {
			const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
			if (!this.ctx) {
				this.ctx = new AudioContextClass({ latencyHint: "interactive" });
				this.masterGain = this.ctx.createGain();
				this.masterGain.gain.setValueAtTime(this.muted ? 0 : 0.7, this.ctx.currentTime);
				this.masterGain.connect(this.ctx.destination);
				this.noiseBuffer = createNoiseBuffer(this.ctx, 1.0);
			}
			if (this.ctx.state !== 'running' && this.ctx.state !== 'closed') {
				this.unlocked = false;
				if (this.pendingResume && !activation) return;
				const context=this.ctx;
				const request=context.resume().then(()=>{
					if(!this.disposed&&this.ctx===context)this.unlocked=context.state==='running';
				}).catch(()=>{
					if(this.ctx===context)this.unlocked=false;
				}).finally(()=>{if(this.pendingResume===request)this.pendingResume=null;});
				this.pendingResume=request;
				return;
			}
			this.unlocked = true;
		} catch {
			// Web Audio not permitted or supported
		}
	}

	setMuted(muted: boolean): void {
		this.muted = muted;
		if (this.masterGain && this.ctx) {
			this.masterGain.gain.setValueAtTime(muted ? 0 : 0.7, this.ctx.currentTime);
		}
	}

	toggleMuted(): boolean {
		this.setMuted(!this.muted);
		return this.muted;
	}

	isMuted(): boolean {
		return this.muted;
	}
	/** Original, bounded magic chimes; only an already unlocked Web Audio context may play. */
	playMageCue(kind:'charge'|'release'|'impact'|'level'):void {
		if(this.disposed||this.muted||!this.unlocked||this.ctx?.state!=='running'||!this.masterGain||this.mageVoices>=8)return;
		const ctx=this.ctx,now=ctx.currentTime,duration=kind==='charge'?.18:kind==='level'?.35:.16;
		const notes=kind==='level'?[523,659,784]:kind==='charge'?[330,660]:kind==='release'?[784,1176]:[659,988];
		for(const [i,f] of notes.entries()){
			if(this.mageVoices>=8)break;this.mageVoices++;
			const oscillator=ctx.createOscillator(),gain=ctx.createGain(),at=now+i*.025;
			oscillator.type='sine';oscillator.frequency.setValueAtTime(f,at);oscillator.frequency.exponentialRampToValueAtTime(f*1.03,at+duration);
			gain.gain.setValueAtTime(.0001,at);gain.gain.linearRampToValueAtTime(.045/(i+1),at+.012);gain.gain.exponentialRampToValueAtTime(.0001,at+duration);
			oscillator.connect(gain);gain.connect(this.masterGain);oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();this.mageVoices=Math.max(0,this.mageVoices-1);};
			oscillator.start(at);oscillator.stop(at+duration);
		}
	}

	dispose():void{
		if(this.disposed)return;this.disposed=true;this.activationEvents.abort();
		const context=this.ctx;this.ctx=null;this.masterGain?.disconnect();this.masterGain=null;this.noiseBuffer=null;this.unlocked=false;
		if(context&&context.state!=='closed')void context.close().catch(()=>{});
	}

	/** Weapon swing whoosh: swept bandpass noise + subtle whistle. */
	playSwing(heavy = false): void {
		this.ensureUnlocked();
		if (!this.ctx || !this.masterGain || this.muted || !this.noiseBuffer) return;
		const now = this.ctx.currentTime;
		const duration = heavy ? 0.28 : 0.19;

		// Noise component
		const noiseSrc = this.ctx.createBufferSource();
		noiseSrc.buffer = this.noiseBuffer;
		const noiseFilter = this.ctx.createBiquadFilter();
		noiseFilter.type = "bandpass";
		const startFreq = heavy ? 450 : 700;
		const endFreq = heavy ? 1600 : 2600;
		noiseFilter.frequency.setValueAtTime(startFreq, now);
		noiseFilter.frequency.exponentialRampToValueAtTime(endFreq, now + duration * 0.6);
		noiseFilter.frequency.exponentialRampToValueAtTime(startFreq * 0.8, now + duration);
		noiseFilter.Q.setValueAtTime(2.5, now);

		const noiseGain = this.ctx.createGain();
		const volume = heavy ? 0.55 : 0.38;
		noiseGain.gain.setValueAtTime(0.001, now);
		noiseGain.gain.linearRampToValueAtTime(volume, now + duration * 0.2);
		noiseGain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		noiseSrc.connect(noiseFilter);
		noiseFilter.connect(noiseGain);
		noiseGain.connect(this.masterGain);

		noiseSrc.start(now);
		noiseSrc.stop(now + duration);

		// Blade air tone
		const osc = this.ctx.createOscillator();
		osc.type = "sine";
		osc.frequency.setValueAtTime(heavy ? 220 : 380, now);
		osc.frequency.exponentialRampToValueAtTime(heavy ? 420 : 780, now + duration * 0.5);
		osc.frequency.exponentialRampToValueAtTime(180, now + duration);

		const oscGain = this.ctx.createGain();
		oscGain.gain.setValueAtTime(0.001, now);
		oscGain.gain.linearRampToValueAtTime(volume * 0.35, now + duration * 0.2);
		oscGain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		osc.connect(oscGain);
		oscGain.connect(this.masterGain);

		osc.start(now);
		osc.stop(now + duration);
	}

	/** Hit impact on target: low body thump + crisp high snap. */
	playHit(crit = false): void {
		this.ensureUnlocked();
		if (!this.ctx || !this.masterGain || this.muted || !this.noiseBuffer) return;
		const now = this.ctx.currentTime;
		const duration = crit ? 0.32 : 0.22;

		// 1. Thump: pitch drop sub-oscillator
		const sub = this.ctx.createOscillator();
		sub.type = "triangle";
		const startPitch = crit ? 240 : 180;
		sub.frequency.setValueAtTime(startPitch, now);
		sub.frequency.exponentialRampToValueAtTime(45, now + duration);

		const subGain = this.ctx.createGain();
		subGain.gain.setValueAtTime(crit ? 0.9 : 0.7, now);
		subGain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		sub.connect(subGain);
		subGain.connect(this.masterGain);
		sub.start(now);
		sub.stop(now + duration);

		// 2. Click / punch transient
		const click = this.ctx.createOscillator();
		click.type = "sine";
		click.frequency.setValueAtTime(600, now);
		click.frequency.exponentialRampToValueAtTime(120, now + 0.04);

		const clickGain = this.ctx.createGain();
		clickGain.gain.setValueAtTime(0.8, now);
		clickGain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);

		click.connect(clickGain);
		clickGain.connect(this.masterGain);
		click.start(now);
		click.stop(now + 0.04);

		// 3. Impact crunch noise
		const noiseSrc = this.ctx.createBufferSource();
		noiseSrc.buffer = this.noiseBuffer;
		const filter = this.ctx.createBiquadFilter();
		filter.type = "bandpass";
		filter.frequency.setValueAtTime(crit ? 2800 : 1800, now);
		filter.Q.setValueAtTime(1.8, now);

		const noiseGain = this.ctx.createGain();
		noiseGain.gain.setValueAtTime(crit ? 0.65 : 0.45, now);
		noiseGain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);

		noiseSrc.connect(filter);
		filter.connect(noiseGain);
		noiseGain.connect(this.masterGain);
		noiseSrc.start(now);
		noiseSrc.stop(now + 0.12);
	}

	/** Quickstep dodge whoosh: crisp lateral air displacement. */
	playDodge(): void {
		this.ensureUnlocked();
		if (!this.ctx || !this.masterGain || this.muted || !this.noiseBuffer) return;
		const now = this.ctx.currentTime;
		const duration = 0.28;

		const noiseSrc = this.ctx.createBufferSource();
		noiseSrc.buffer = this.noiseBuffer;
		const filter = this.ctx.createBiquadFilter();
		filter.type = "lowpass";
		filter.frequency.setValueAtTime(1400, now);
		filter.frequency.exponentialRampToValueAtTime(450, now + duration);

		const gain = this.ctx.createGain();
		gain.gain.setValueAtTime(0.01, now);
		gain.gain.linearRampToValueAtTime(0.5, now + 0.06);
		gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		noiseSrc.connect(filter);
		filter.connect(gain);
		gain.connect(this.masterGain);
		noiseSrc.start(now);
		noiseSrc.stop(now + duration);
	}

	/** Puddlekin Splash Hop telegraph chime: rising harmonic glint. */
	playTelegraphChime(): void {
		this.ensureUnlocked();
		if (!this.ctx || !this.masterGain || this.muted) return;
		const now = this.ctx.currentTime;
		const duration = 0.9; // matches 900 ms windup

		const osc1 = this.ctx.createOscillator();
		const osc2 = this.ctx.createOscillator();
		osc1.type = "sine";
		osc2.type = "triangle";

		osc1.frequency.setValueAtTime(392, now); // G4
		osc1.frequency.exponentialRampToValueAtTime(784, now + duration); // G5
		osc2.frequency.setValueAtTime(396, now); // detuned shimmer
		osc2.frequency.exponentialRampToValueAtTime(792, now + duration);

		const gain = this.ctx.createGain();
		gain.gain.setValueAtTime(0.01, now);
		gain.gain.linearRampToValueAtTime(0.32, now + duration * 0.7);
		gain.gain.linearRampToValueAtTime(0.48, now + duration * 0.95);
		gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		osc1.connect(gain);
		osc2.connect(gain);
		gain.connect(this.masterGain);

		osc1.start(now);
		osc2.start(now);
		osc1.stop(now + duration);
		osc2.stop(now + duration);
	}

	/** Puddlekin Splash Hop impact slam: heavy watery bass thump. */
	playSplashImpact(): void {
		this.ensureUnlocked();
		if (!this.ctx || !this.masterGain || this.muted || !this.noiseBuffer) return;
		const now = this.ctx.currentTime;
		const duration = 0.45;

		// Heavy slam sub
		const osc = this.ctx.createOscillator();
		osc.type = "sine";
		osc.frequency.setValueAtTime(95, now);
		osc.frequency.exponentialRampToValueAtTime(28, now + duration);

		const oscGain = this.ctx.createGain();
		oscGain.gain.setValueAtTime(0.95, now);
		oscGain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		osc.connect(oscGain);
		oscGain.connect(this.masterGain);
		osc.start(now);
		osc.stop(now + duration);

		// Water/earth splash burst
		const noiseSrc = this.ctx.createBufferSource();
		noiseSrc.buffer = this.noiseBuffer;
		const filter = this.ctx.createBiquadFilter();
		filter.type = "lowpass";
		filter.frequency.setValueAtTime(800, now);
		filter.frequency.exponentialRampToValueAtTime(150, now + duration);

		const noiseGain = this.ctx.createGain();
		noiseGain.gain.setValueAtTime(0.7, now);
		noiseGain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		noiseSrc.connect(filter);
		filter.connect(noiseGain);
		noiseGain.connect(this.masterGain);
		noiseSrc.start(now);
		noiseSrc.stop(now + duration);
	}

	/** Player damaged: hurt impact. */
	playPlayerHurt(): void {
		this.ensureUnlocked();
		if (!this.ctx || !this.masterGain || this.muted) return;
		const now = this.ctx.currentTime;
		const duration = 0.25;

		const osc = this.ctx.createOscillator();
		osc.type = "sawtooth";
		osc.frequency.setValueAtTime(160, now);
		osc.frequency.exponentialRampToValueAtTime(60, now + duration);

		const filter = this.ctx.createBiquadFilter();
		filter.type = "lowpass";
		filter.frequency.setValueAtTime(700, now);

		const gain = this.ctx.createGain();
		gain.gain.setValueAtTime(0.6, now);
		gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

		osc.connect(filter);
		filter.connect(gain);
		gain.connect(this.masterGain);
		osc.start(now);
		osc.stop(now + duration);
	}
}

export const sound = new CombatAudio();
