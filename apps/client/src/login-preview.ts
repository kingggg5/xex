import { bindLoginLanguage } from "./login-locale";
import { mountLoginBackground } from "./login-background";
/** Isolated visual review: the same markup, with no auth, world or session requests. */
async function previewLogin(): Promise<void> {
	const response = await fetch("/", {cache:"no-store"});
	if (!response.ok) throw new Error("Login markup could not be loaded");
	const source = new DOMParser().parseFromString(await response.text(), "text/html");
	const screen = source.getElementById("login-screen");
	const host = document.getElementById("game");
	if (!screen || !host) throw new Error("Login preview is missing its markup");
	screen.hidden = false;
	host.replaceChildren(document.importNode(screen, true));
	const mountedScreen = document.getElementById("login-screen")!;
	const lang=new URLSearchParams(location.search).get("lang")==="th"?"th":"en";
	bindLoginLanguage(mountedScreen,lang,undefined,false);
	const stopBackground = mountLoginBackground(mountedScreen);
	if (import.meta.hot) import.meta.hot.dispose(stopBackground);
	const guest = document.getElementById("login-guest") as HTMLButtonElement;
	guest.addEventListener("click", () => {
		const note = document.getElementById("login-note");
		if (note) note.textContent = "Visual preview only. Open the game to play as guest.";
	});

}
void previewLogin().catch(() => {
	const host = document.getElementById("game");
	if (host) host.textContent="The login preview could not load. Refresh to try again.";
});
