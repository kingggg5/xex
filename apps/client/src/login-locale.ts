import { COPY } from "./login-copy";

export type LoginLanguage = "en" | "th";
const STORAGE_KEY = "xexoria_login_language";

export function readLoginLanguage(): LoginLanguage {
	try { const saved=localStorage.getItem(STORAGE_KEY); if(saved==="en"||saved==="th")return saved; } catch { /* Storage may be unavailable. */ }
	return navigator.language.toLowerCase().startsWith("th") ? "th" : "en";
}

export function setLoginButtonLabel(button: HTMLButtonElement, label: string): void {
	(button.querySelector<HTMLElement>(".login-action-label") ?? button).textContent = label;
}

/** Localizes only this auth surface; it does not rebuild it, reset fields or touch auth state. */
export function bindLoginLanguage(root: HTMLElement, initial: LoginLanguage, changed?: (language: LoginLanguage)=>void, persist=true): ()=>void {
	const select=root.querySelector<HTMLSelectElement>("#login-language");
	if(!select)throw new Error("Login language selector is missing");
	let language=initial;
	const apply=()=>{
		root.lang=language; select.value=language;
		root.querySelector(".login-card")?.setAttribute("aria-label",language==="th"?"วิธีเข้าสู่ระบบ":"Sign-in methods");
		const copy=COPY[language], th=language==="th";
		const text=(id:string,value:string)=>{const element=root.querySelector<HTMLElement>(`#${id}`);if(element)element.textContent=value;};
		text("login-title",copy.title);text("login-copy",copy.copy);text("login-note",copy.note);
		text("login-nav-home",th?"หน้าหลัก":"HOME");text("login-nav-preview",th?"ตัวอย่าง":"PREVIEW");text("login-nav-community",th?"คอมมูนิตี้":"COMMUNITY");
		text("login-story",th?"เรื่องราว\nของคุณ\nเริ่มต้น\nณ โลกใหม่":"YOUR\nSTORY\nBEGINS\nBEYOND");
		text("login-motto",th?"สำรวจ\nต่อสู้\nร่วมผจญภัย":"EXPLORE\nFIGHT\nBELONG");
		text("login-sky-motto",th?"ต่างเส้นทาง\nใต้ท้องฟ้าเดียวกัน":"DIFFERENT\nPATHS\nTHE SAME SKY");
		text("login-browser-label",th?"เล่นผ่านเว็บเบราว์เซอร์":"PLAY IN YOUR BROWSER");
		for(const [id,label] of [["login-google",copy.google],["login-discord",copy.discord],["login-guest",copy.guest]] as const){
			const button=root.querySelector<HTMLButtonElement>(`#${id}`);
			if(button){button.setAttribute("aria-label",label);setLoginButtonLabel(button,id==="login-guest"&&button.getAttribute("aria-busy")==="true"?copy.guestBusy:label);}
		}
		root.querySelector("#login-guest")?.setAttribute("aria-label",th?"เข้าสู่ระบบแบบผู้เยี่ยมชม":"Play as Guest");
		select.setAttribute("aria-label",th?"ภาษา":"Language");
		const languageLabel=root.querySelector<HTMLElement>(".login-language .login-sr-only");
		if(languageLabel)languageLabel.textContent=th?"ภาษา":"Language";
	};
	apply();
	const onChange=()=>{
		if(select.value!=="en"&&select.value!=="th"){select.value=language;return;}
		language=select.value;
		if(persist)try{localStorage.setItem(STORAGE_KEY,language);}catch{/* The selector still works without storage. */}
		apply();changed?.(language);
	};
	select.addEventListener("change",onChange);
	return()=>select.removeEventListener("change",onChange);
}
