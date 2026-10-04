// Login screen controller (D-13): guest play plus optional Google/Discord
// sign-in. Runs before the game connects; the offline preview boots with no
// gate at all when the server cannot be reached.
import { decideLoginGate, loginErrorText, parseIdentity, type LoginIdentity } from "./login-gate.mjs";
import { COPY } from "./login-copy";
import type { LoginCopy } from "./login-copy";
import { bindLoginLanguage, readLoginLanguage, setLoginButtonLabel } from "./login-locale";
import { mountLoginBackground } from "./login-background";
import { fetchRooms, loadStoredChannel, renderChannelPicker, saveStoredChannel, type RoomRow } from "./rooms-ui";

interface ProviderAvailability {
	google: boolean;
	discord: boolean;
}

function loginElement<T extends HTMLElement>(id: string, check: (value: unknown) => value is T, label: string): T {
	const element: unknown = document.getElementById(id);
	if (!check(element)) throw new Error(`Login element #${id} is missing or is not a ${label}.`);
	return element;
}

const isHtml = <T extends HTMLElement>(type: new () => T) => (value: unknown): value is T => value instanceof type;

/** Shows the login screen when needed, resolves with the chosen identity. */
export async function runLoginGate(options: {deferChannelSelection?: boolean; signal?: AbortSignal} = {}): Promise<LoginIdentity | null> {
	const health = await loginFetch("/healthz", {}, options.signal).catch(() => null);
	if (!health?.ok) return null; // Offline preview boots ungated, as before.
	const whoami = await loginFetch("/session/whoami", {}, options.signal).catch(() => null);
	if (whoami?.ok) {
		const identity = parseIdentity(await whoami.json());
		if (!identity && options.deferChannelSelection) throw new Error('Your sign-in could not be verified. Please reload and try again.');
		return identity;
	}
	const providersResponse = await loginFetch("/auth/providers", {}, options.signal).catch(() => null);
	const providers: ProviderAvailability | null = providersResponse?.ok ? await readProviders(providersResponse) : null;
	const urlError = new URLSearchParams(window.location.search).get("login");
	if (decideLoginGate({ serverAlive: true, signedIn: false, providers, urlError }) !== "show" || !providers) {
		if (options.deferChannelSelection) throw new Error('Sign-in options could not be loaded. Please reload and try again.');
		return null;
	}

	let lang = readLoginLanguage();
	let copy: LoginCopy = COPY[lang];
	const screen = loginElement("login-screen", isHtml(HTMLElement), "element");
	const errorLine = loginElement("login-error", isHtml(HTMLParagraphElement), "p");
	const unconfigured = loginElement("login-unconfigured", isHtml(HTMLParagraphElement), "p");
	const googleButton = loginElement("login-google", isHtml(HTMLButtonElement), "button");
	const discordButton = loginElement("login-discord", isHtml(HTMLButtonElement), "button");
	const guestButton = loginElement("login-guest", isHtml(HTMLButtonElement), "button");
	loginElement("login-title", isHtml(HTMLHeadingElement), "h2").textContent = copy.title;
	loginElement("login-copy", isHtml(HTMLParagraphElement), "p").textContent = copy.copy;
	loginElement("login-note", isHtml(HTMLParagraphElement), "p").textContent = copy.note;
	setLoginButtonLabel(googleButton, copy.google);
	setLoginButtonLabel(discordButton, copy.discord);
	setLoginButtonLabel(guestButton, copy.guest);
	guestButton.disabled = false;

	let currentError = urlError;
	const initialError = loginErrorText(currentError, lang);
	errorLine.textContent = initialError ?? "";
	errorLine.hidden = initialError === null;
	if (urlError) {
		// Clean the failed-login parameter out of the address bar so a reload
		// does not replay the error.
		const cleaned = new URL(window.location.href);
		cleaned.searchParams.delete("login");
		window.history.replaceState(null, "", cleaned);
	}

	googleButton.disabled = !providers.google;
	discordButton.disabled = !providers.discord;
	unconfigured.hidden = providers.google && providers.discord;
	if (!unconfigured.hidden) {
		const missing = [providers.google ? null : "Google", providers.discord ? null : "Discord"].filter(Boolean).join(", ");
		unconfigured.textContent = `${copy.unconfigured} ${missing}`;
	}

	screen.hidden = false;
	const stopBackground = mountLoginBackground(screen);
	guestButton.focus();

	// Channel / ช่องทาง (rooms slice): a collapsible section, default Auto.
	// The room list is fetched once, off the critical path; when /rooms 404s
	// (server still booting) the section hides and Auto takes over — the gate
	// never blocks on it.
	let chosenChannel = options.deferChannelSelection ? null : loadStoredChannel();
	let latestRooms: RoomRow[] | null = null;
	let roomsStarted = false;
	let roomsFinished = false;
	const channelSection = document.createElement("div");
	channelSection.className = "login-channel";
	channelSection.hidden = options.deferChannelSelection === true;
	const channelToggle = document.createElement("button");
	channelToggle.type = "button";
	channelToggle.className = "login-channel-toggle";
	const channelBody = document.createElement("div");
	channelBody.className = "login-channel-body";
	channelBody.hidden = true;
	const updateToggleLabel = (): void => {
		channelToggle.textContent = `${copy.channelToggle}: ${copy.channelValue(chosenChannel)}`;
	};
	updateToggleLabel();
	const pickChannel = (channel: number | null): void => {
		chosenChannel = channel;
		saveStoredChannel(channel);
		updateToggleLabel();
		if (latestRooms !== null) renderChannelPicker(channelBody, channel, pickChannel, latestRooms, lang);
	};
	channelToggle.addEventListener("click", () => {
		channelBody.hidden = !channelBody.hidden;
		if (channelBody.hidden) return;
		if (latestRooms === null && channelBody.childElementCount === 0) {
			const loading = document.createElement("p");
			loading.className = "channel-picker-note";
			loading.textContent = copy.channelLoading;
			channelBody.append(loading);
		}
	});
	channelSection.append(channelToggle, channelBody);
	unconfigured.before(channelSection);
	const loadChannelRooms = async (): Promise<void> => {
		if (options.deferChannelSelection) return;
		if (roomsStarted) return;
		roomsStarted = true;
		const rows = await fetchRooms();
		roomsFinished = true;
		if (rows === null) {
			if (chosenChannel === null) {
				channelSection.hidden = true; // /rooms failed while booting: Auto fallback.
			} else {
				channelBody.replaceChildren();
				const note = document.createElement("p");
				note.className = "channel-picker-note";
				note.textContent = copy.channelUnavailable;
				channelBody.append(note);
			}
			return;
		}
		latestRooms = rows;
		channelSection.hidden = false;
		renderChannelPicker(channelBody, chosenChannel, pickChannel, rows, lang);
	};
	void loadChannelRooms();

	const stopLanguage = bindLoginLanguage(screen, lang, (language) => {
        lang = language;
        copy = COPY[lang];
        if (currentError) errorLine.textContent = loginErrorText(currentError, lang) ?? "";
        if (guestButton.getAttribute("aria-busy") === "true") setLoginButtonLabel(guestButton, copy.guestBusy);
        if (!unconfigured.hidden) {
            const missing = [providers.google ? null : "Google", providers.discord ? null : "Discord"].filter(Boolean).join(", ");
            unconfigured.textContent = `${copy.unconfigured} ${missing}`;
        }
        updateToggleLabel();
		if (options.deferChannelSelection) channelSection.hidden = true;
        if (latestRooms !== null) renderChannelPicker(channelBody, chosenChannel, pickChannel, latestRooms, lang);
        else {
            const statusNote = channelBody.querySelector<HTMLElement>(".channel-picker-note");
            if (statusNote) statusNote.textContent = roomsFinished ? copy.channelUnavailable : copy.channelLoading;
        }
    });

	const entered = await new Promise<LoginIdentity>((resolve) => {
		googleButton.addEventListener("click", () => window.location.assign("/auth/google/start"), { once: true });
		discordButton.addEventListener("click", () => window.location.assign("/auth/discord/start"), { once: true });
		const attemptGuest = (): void => {
			guestButton.disabled = true;
			guestButton.setAttribute("aria-busy", "true");
			errorLine.hidden = true;
			setLoginButtonLabel(guestButton, copy.guestBusy);
			void (async () => {
				const identity = await enterAsGuest(chosenChannel, options.signal).catch(() => null);
				if (identity) {
					resolve(identity);
					return;
				}
				// Failed: show why and let the player try again.
				guestButton.disabled = false;
				guestButton.setAttribute("aria-busy", "false");
				setLoginButtonLabel(guestButton, copy.guest);
				currentError = "failed";
				errorLine.textContent = loginErrorText(currentError, lang) ?? "";
				errorLine.hidden = false;
				guestButton.addEventListener("click", attemptGuest, { once: true });
			})();
		};
		guestButton.addEventListener("click", attemptGuest, { once: true });
	});

	stopLanguage();
	stopBackground();
	guestButton.setAttribute("aria-busy", "false");
	screen.hidden = true;
	return entered;
}

async function readProviders(response: Response): Promise<ProviderAvailability> {
	const body: unknown = await response.json();
	const source = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
	return {
		google: source.google === true,
		discord: source.discord === true,
	};
}

/** POST /session (the same guest endpoint as before), then read the identity. */
async function enterAsGuest(channel: number | null, signal?: AbortSignal): Promise<LoginIdentity | null> {
	const created = await loginFetch("/session", { method: "POST" }, signal).catch(() => null);
	if (!created?.ok) return null;
	await applyGuestChannel(channel);
	const whoami = await loginFetch("/session/whoami", {}, signal).catch(() => null);
	if (!whoami?.ok) return { provider: "guest", name: "Traveler" };
	return parseIdentity(await whoami.json());
}

/** The timeout stays active through body consumption; navigation also cancels discovery. */
function loginFetch(path: string, init: RequestInit = {}, callerSignal?: AbortSignal): Promise<Response> {
	const timeout = AbortSignal.timeout(3500);
	const signal = callerSignal ? AbortSignal.any([callerSignal, timeout]) : timeout;
	return fetch(path, {...init, cache:'no-store', signal});
}

/**
 * Pins the picked channel onto the fresh guest session before the gate
 * resolves. Best effort: failures are ignored (the session keeps its default
 * auto channel), a stale stored choice (400 unknown_channel) reverts to auto,
 * and a slow server can delay the gate by at most 3.5 s.
 */
async function applyGuestChannel(channel: number | null): Promise<void> {
	if (channel === null) return;
	const request = (async (): Promise<void> => {
		try {
			const response = await fetch("/session/channel", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ channel }),
				cache: "no-store",
			});
			if (response.status === 400) saveStoredChannel(null);
		} catch {
			// Network hiccup: the session keeps its default (auto) channel.
		}
	})();
	let timer = 0;
	const timeout = new Promise<void>((resolve) => {
		timer = window.setTimeout(resolve, 3500);
	});
	await Promise.race([request, timeout]);
	window.clearTimeout(timer);
}
