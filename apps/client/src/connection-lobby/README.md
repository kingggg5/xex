# Connection lobby

Scope: an Operate surface extending the existing Xexoria navy/gold login identity. The bounded ornamental channel register uses the approved logo and local Marcellus/Trirong fonts. The service owns all room facts and the caller owns actual startup readiness.

`createConnectionLobby({ language, worldName, host? })` mounts under `#game`. Its public methods are `chooseChannel(service)`, `beginLoading(phaseIds?)`, `updatePhase(event)`, `ready()`, `showError(message, retry?)`, and `dispose()`.

- `chooseChannel` resolves `{channel}` only after the service acknowledges the selected channel. Full rows cannot enter. Auto appears only when the service verifies it is available. Refresh and confirmation have bounded deadlines and never run concurrently.
- Channel numbers are displayed as padded one-based values; the service receives the original zero-based value. Occupancy values are exact, even if a server reports more players than capacity.
- `latencyMs` is one shared HTTP round-trip estimate, repeated in rows and labelled accordingly. Unknown latency is a dash.
- Loading progress counts completed phases. It never represents total downloaded bytes or a startup percentage. Only a named resource with actual `loaded` and `total` counters has measured transfer progress; other active operations remain indeterminate. Latest updates are bounded to six by the pure bootstrap model.
- Only sibling children are made inert; the parent remains available to the portrait gate. Owned inert state and focus are restored on ready/dispose. Overlay events stop before reaching bubbling game handlers while browser navigation defaults remain available. A bounded gameplay-key quarantine suppresses held repeats after ready/dispose until release or a fresh press, then removes its listeners.

Isolated visual review: `/src/connection-lobby/preview.html?lang=th`. The fixture has explicit synthetic-data labelling and no server or world requests. Add `scenario=loading`, `error`, `empty`, `full`, `load-error`, `apply-error`, or `slow`; add `unknown-ping` for unknown latency. Review at desktop and 812×375 landscape. `window.connectionLobbyFixture` exposes the controller for ready/dispose/input-isolation checks; body `data-key-leaks` and `data-pointer-leaks` count bubbling fixture game handlers.

Owned tests: `presentation.test.mjs` checks factual DTO projection and entry eligibility; `render.test.mjs` compiles and renders the actual Svelte component to verify channel/error/loading semantics in both languages. No packages are added.
