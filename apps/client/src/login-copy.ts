export const COPY = {
	en: {
		title: "Welcome back, traveler",
		copy: "The next chapter awaits.",
		guest: "LOG IN",
		google: "Continue with Google",
		discord: "Continue with Discord",
		note: "Guest progress is stored for this session only and resets when the room restarts.",
		unconfigured: "Sign-in is currently unavailable with:",
		guestBusy: "CONNECTING…",
		channelToggle: "Channel",
		channelValue: (channel: number | null): string => (channel === null ? "Auto" : `Room ${channel + 1}`),
		channelLoading: "Loading rooms…",
		channelUnavailable: "The room list is unavailable right now — Auto still works.",
	},
	th: {
		title: "ยินดีต้อนรับ นักเดินทาง",
		copy: "การเดินทางบทต่อไปกำลังรอคุณอยู่",
		guest: "LOG IN",
		google: "เข้าสู่ระบบด้วย Google",
		discord: "เข้าสู่ระบบด้วย Discord",
		note: "ความคืบหน้าของผู้เยี่ยมชมเก็บเฉพาะช่วงนี้ และจะรีเซ็ตเมื่อห้องรีสตาร์ท",
		unconfigured: "ยังเข้าสู่ระบบด้วยวิธีนี้ไม่ได้:",
		guestBusy: "กำลังเข้าสู่ระบบ…",
		channelToggle: "ช่องทาง",
		channelValue: (channel: number | null): string => (channel === null ? "อัตโนมัติ" : `ห้อง ${channel + 1}`),
		channelLoading: "กำลังโหลดรายชื่อห้อง…",
		channelUnavailable: "ยังดูรายชื่อห้องไม่ได้ แต่เลือกแบบอัตโนมัติได้ตามปกติ",
	},
} as const;

export interface LoginCopy {
	title: string;
	copy: string;
	guest: string;
	google: string;
	discord: string;
	note: string;
	unconfigured: string;
	guestBusy: string;
	channelToggle: string;
	channelValue(channel: number | null): string;
	channelLoading: string;
	channelUnavailable: string;
}

