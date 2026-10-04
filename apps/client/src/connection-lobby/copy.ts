import type { BootstrapPhaseId } from '../bootstrap-progress.mjs';

const phasesEn: Record<BootstrapPhaseId, string> = {
	content: 'World content', renderer: 'Graphics engine', codecs: 'Configure asset decoders', assets: 'World assets',
	shaders: 'Preparing shaders', room: 'Channel connection', snapshot: 'World state', first_frame: 'First rendered frame',
};
const phasesTh: Record<BootstrapPhaseId, string> = {
	content: 'ข้อมูลโลก', renderer: 'ระบบกราฟิก', codecs: 'ตั้งค่าตัวถอดรหัส', assets: 'ทรัพยากรโลก',
	shaders: 'เตรียม shader', room: 'เชื่อมต่อช่องทาง', snapshot: 'สถานะโลก', first_frame: 'ภาพแรกของโลก',
};
export const LOBBY_COPY = {
	en: {
		title: 'Choose your channel', subtitle: 'A new journey begins here.', world: 'World',
		channel: 'Channel', population: 'Adventurers', latency: 'Connection', latencyNote: 'Shared server round-trip estimate',
		refresh: 'Refresh', refreshing: 'Refreshing…', fetching: 'Fetching channels…',
		auto: 'Choose automatically', autoNote: 'The server finds an available channel.',
		available: 'Available', full: 'Full', selected: 'Selected', confirm: 'Enter world', applying: 'Confirming channel…',
		empty: 'No channels are available right now.', emptyDetail: 'Refresh the list to check again.',
		listUnavailable: 'The channel list is unavailable.', autoFallback: 'Use automatic selection to continue.',
		warningGeneric: 'Some channel information is unavailable. Refresh to check again.',
		warningMessages: {
			channel_unavailable: 'The channel list is temporarily unavailable. Refresh to check again.',
			invalid_response: 'Channel information could not be verified. Refresh to check again.',
			timeout: 'The channel list took too long to respond. Refresh to try again.',
			network_error: 'The channel request could not reach the server. Refresh to try again.',
		},
		allFull: 'All listed channels are full. Refresh to check for space.',
		loadError: 'The channel list could not be loaded. Refresh to try again.',
		applyError: 'This channel could not be confirmed. Choose another channel or try again.',
		loadingTitle: 'Opening the way', loadingSubtitle: 'Preparing your journey',
		phaseCount: 'phases complete', checkpoints: 'Startup checkpoints', updates: 'Latest updates',
		preparing: 'Preparing the next step…', paused: 'Preparation paused', waiting: 'Waiting', active: 'In progress', complete: 'Complete', failed: 'Needs attention',
		loadingError: 'Your journey was interrupted', retry: 'Try again', retrying: 'Trying again…',
		phaseError: 'This step could not finish. Try again.', phases: phasesEn,
	},
	th: {
		title: 'เลือกช่องทางของคุณ', subtitle: 'การเดินทางครั้งใหม่เริ่มต้นที่นี่', world: 'โลก',
		channel: 'ช่องทาง', population: 'นักเดินทาง', latency: 'การเชื่อมต่อ', latencyNote: 'ค่าประมาณไปกลับของเซิร์ฟเวอร์ร่วม',
		refresh: 'รีเฟรช', refreshing: 'กำลังรีเฟรช…', fetching: 'กำลังค้นหาช่องทาง…',
		auto: 'เลือกช่องทางอัตโนมัติ', autoNote: 'เซิร์ฟเวอร์จะเลือกช่องทางที่มีพื้นที่ว่าง',
		available: 'ว่าง', full: 'เต็ม', selected: 'เลือกแล้ว', confirm: 'เข้าสู่โลก', applying: 'กำลังยืนยันช่องทาง…',
		empty: 'ยังไม่มีช่องทางที่พร้อมให้บริการ', emptyDetail: 'รีเฟรชรายชื่อเพื่อตรวจสอบอีกครั้ง',
		listUnavailable: 'ยังดูรายชื่อช่องทางไม่ได้', autoFallback: 'เลือกช่องทางอัตโนมัติเพื่อเดินทางต่อได้',
		warningGeneric: 'ข้อมูลช่องทางบางส่วนยังไม่พร้อม โปรดรีเฟรชเพื่อตรวจสอบอีกครั้ง',
		warningMessages: {
			channel_unavailable: 'รายชื่อช่องทางไม่พร้อมชั่วคราว โปรดรีเฟรชเพื่อตรวจสอบอีกครั้ง',
			invalid_response: 'ยังยืนยันข้อมูลช่องทางไม่ได้ โปรดรีเฟรชเพื่อตรวจสอบอีกครั้ง',
			timeout: 'รายชื่อช่องทางใช้เวลาตอบกลับนานเกินไป โปรดรีเฟรชเพื่อลองอีกครั้ง',
			network_error: 'คำขอรายชื่อช่องทางเชื่อมต่อเซิร์ฟเวอร์ไม่ได้ โปรดรีเฟรชเพื่อลองอีกครั้ง',
		},
		allFull: 'ทุกช่องทางเต็มแล้ว รีเฟรชเพื่อตรวจสอบพื้นที่ว่าง',
		loadError: 'โหลดรายชื่อช่องทางไม่ได้ โปรดรีเฟรชเพื่อลองอีกครั้ง',
		applyError: 'ยืนยันช่องทางนี้ไม่ได้ โปรดเลือกช่องทางอื่นหรือลองอีกครั้ง',
		loadingTitle: 'กำลังเปิดเส้นทาง', loadingSubtitle: 'เตรียมพร้อมสำหรับการเดินทาง',
		phaseCount: 'ขั้นตอนเสร็จแล้ว', checkpoints: 'ขั้นตอนเตรียมโลก', updates: 'ความคืบหน้าล่าสุด',
		preparing: 'กำลังเตรียมขั้นตอนถัดไป…', paused: 'หยุดการเตรียมชั่วคราว', waiting: 'รอดำเนินการ', active: 'กำลังดำเนินการ', complete: 'เสร็จแล้ว', failed: 'ต้องตรวจสอบ',
		loadingError: 'การเดินทางหยุดชั่วคราว', retry: 'ลองอีกครั้ง', retrying: 'กำลังลองอีกครั้ง…',
		phaseError: 'ขั้นตอนนี้ไม่สำเร็จ โปรดลองอีกครั้ง', phases: phasesTh,
	},
} as const;
