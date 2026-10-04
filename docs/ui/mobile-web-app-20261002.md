# Mobile web-app launch and landscape-only play

User request: play without browser navigation bars, require landscape, and show the Safari Home Screen installation flow. Existing main logo and UI-owner components remain intact; a separate mobile-web-app Svelte layer owns the instruction/gate.

## Player instructions

**iPhone / iPad:** เปิดเว็บไซต์เกมใน Safari → กดแชร์ → เพิ่มไปยังหน้าจอโฮม → เปิด “Open as Web App / เปิดเป็นเว็บแอป” ถ้ามี → กดเพิ่ม → เปิดเกมจากไอคอน Xexoria บนหน้าจอโฮม → หมุนเครื่องเป็นแนวนอน

English: Open the game in Safari → Share → Add to Home Screen → enable Open as Web App, if shown → Add → launch Xexoria from its Home Screen icon → rotate to landscape.

If the screen does not rotate, turn off Portrait Orientation Lock in Control Centre. A normal Safari tab can still show its browser bars. Standalone launch removes browser navigation UI; the OS status area and Home indicator are separate. The installation guide does not pretend that a website button can perform Apple's installation steps.

## Implementation contract

- `public/manifest.webmanifest`: stable app ID/scope, standalone display, landscape preference, safe Home Screen start URL and square 192/512 icons. Legacy Apple-capable/title/status metadata and 180 px touch icon are declared in `index.html` for older iOS versions.
- New `src/mobile-web-app/*`: primitive Svelte state only; no Scene/Mesh in UI state. The same orientation predicate drives the visible gate, game inertness and authoritative input checks. Standalone detection uses the actual display-mode or iOS navigator flag, never the start URL alone.
- Initial portrait defers world/content/3D loading until the gate clears. Portrait or an open guide rejects gameplay actions and forces movement to zero after any QA override. The normal input scheduler keeps sending neutral inputs, with an immediate neutral step on a blocking transition; prediction sequence and already-sent action acknowledgements remain intact. Resume resets accumulation and requires fresh keys/pointers.
- Existing held inputs are cancelled through their original DOM keyup/pointercancel/capture-release contracts. The controller does not spoof renderer loss, connection status or global blur, and does not reach into private HUD fields.
- `orientation: landscape` is a browser preference, not universal OS enforcement. Optional lock attempts use capability detection and existing fullscreen entry; unsupported platforms fall back to the visible portrait gate. Safari on iPhone cannot be assumed to implement DOM fullscreen/orientation lock.
- The existing game disposes on pagehide. A persisted BFCache pageshow reloads rather than reviving disposed renderer/network controllers.
- No service worker or cache of the entire game is introduced. Installed launch is not a promise of offline gameplay, saved guest progress or certified phone performance.

## Verification to record

Current checks: 237 Node tests pass; TypeScript/Svelte has zero errors/warnings. Four production-controller DOM contracts pass in Chrome (synthetic routing/release state, not physical touch/orientation). Native responsive startup at 390×844 shows the portrait gate, `#game` inert and no player HUD/world initialization; its Safari guide shows all six steps. The sealed manifest returns 200 with `application/manifest+json`, standalone/landscape fields and valid icons. At 812×375, the normal 5173 origin joins the guest room; rotation to portrait blocks W/F presses with the sampled position unchanged, and return restores game interactivity. The temporary viewport was reset. Native captures and the receipt are under `planning/evidence/mobile-web-app-20261002/`. Actual iPhone Safari Home Screen launch, browser-bar removal and hardware rotation remain device checks, not simulated pass claims.

Check portrait startup before world fetch, normal landscape startup, rotation during held movement/action, fresh input after return, guide focus/close, standalone prompt suppression, keyboard-short viewport in physical portrait, tablet/mouse and narrow desktop cases. Validate manifest links and PNG dimensions in the served build. Native desktop responsive checks are separate from actual Safari Home Screen installation and physical orientation-lock behaviour.

Sources: [Apple Home Screen web-app instructions](https://support.apple.com/guide/iphone/open-as-web-app-iphea86e5236/ios), [Apple web-app meta tags](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariHTMLRef/Articles/MetaTags.html), [MDN standalone display](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/display), [MDN orientation preference](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/orientation), [MDN orientation lock](https://developer.mozilla.org/en-US/docs/Web/API/ScreenOrientation/lock). Current platform documentation was resolved through Context7 and checked against primary sources.
