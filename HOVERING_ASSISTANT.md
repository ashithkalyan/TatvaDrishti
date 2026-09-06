# The Hovering Assistant — build notes

Implements the feature described in `KAVACH_vs_DRISHTI_Analysis.md`: a
floating, point-and-click UI assistant that explains any part of the
KAVACH interface instantly, without touching the LLM or the case-data
brain, plus a safety net for the same question typed into the ordinary
chat box.

## New files

Backend:
- `backend/brain/ui_help_registry.py` — reuses `alias_resolver.resolve_name()`
  to fuzzy-match a typed UI question against the current screen's
  registered elements.

Frontend:
- `frontend/src/hoverAssistant/helpRegistry.js` — the UI Knowledge Registry
- `frontend/src/hoverAssistant/uiIntentRouter.js` — classifier, spatial
  phrase parsing, instant local matching
- `frontend/src/hoverAssistant/screenContextStore.js` — current page/modal
- `frontend/src/hoverAssistant/coverageCheck.js` — dev-mode console warning
  for any interactive element with no `<HelpTarget>` ancestor
- `frontend/src/components/HelpTarget.jsx` — the retrofit wrapper
- `frontend/src/components/InspectorOverlay.jsx` — point-and-click mode
- `frontend/src/components/AssistantMascot.jsx` — original SVG mascot,
  4 states (idle/listening/thinking/speaking)
- `frontend/src/components/HoveringAssistant.jsx` — the floating widget

## Modified files

- `backend/brain/intent_engine.py` — UI-help pattern set + bilingual redirect text
- `backend/brain/brain.py` — safety-net check wired in before the
  general_knowledge fallback (same has_any_entity guard)
- `backend/main.py` — `POST /api/ui-help/resolve`
- `frontend/src/services/api.js` — `resolveUiHelp()`
- `frontend/src/App.jsx` — mounts `<HoveringAssistant>` + dev coverage check
- `frontend/src/i18n/translations.js` — `ha*` keys, EN + KN
- `frontend/src/components/{Sidebar,Header}.jsx` — full retrofit (chrome
  visible on every page)
- `frontend/src/pages/CrimeChat.jsx` — toolbar retrofit (attach, mic,
  send, history, export, clear, new-session)
- `frontend/src/pages/Dashboard.jsx` — all 8 KPI cards
- `frontend/src/pages/Cases.jsx` — search, filters, ingest button
- `frontend/src/pages/Network.jsx` — color mode, risk filter, zoom controls
- `frontend/src/pages/Analytics.jsx` — year/district filters
- `frontend/src/pages/Profiles.jsx` — search, risk filter, repeat-offender toggle

## Deliberate scope boundaries (not oversights)

- **No voice input on the assistant.** The design doc's own caveat
  applies: `webkitSpeechRecognition` sends raw audio to Google's cloud
  in most Chrome installs. Not wired in here; flagged instead.
- **Per-message dynamic buttons aren't tagged** (e.g. the "Reasoning"
  toggle inside each chat bubble). The registry model fits persistent
  chrome (toolbars, nav, KPIs); tagging every row of a growing list
  would flood the assistant's "here's everything on this screen"
  fallback with near-duplicate entries instead of helping.
- **Login.jsx isn't retrofitted.** `HoveringAssistant` is mounted
  inside `AppShell`, which only renders after authentication — there's
  no assistant present pre-login to consume a registry on that page.
- **Full click-through of every icon in the app isn't done.** The dev
  console warning (`coverageCheck.js`) is exactly the tool the design
  doc asks for to close the remaining gaps — it lists every untagged
  interactive element live, screen by screen, as a literal checklist.

## Verified this round

- `npm run build` — clean production build, 0 errors
- Backend `main.py` imports end-to-end (auth, brain, all routes) with
  no errors; `/api/ui-help/resolve` confirmed registered
- Live `TestClient` HTTP round trip through real registration/auth,
  hitting the new endpoint: exact match (100%), fuzzy typo match
  ("paprclip" → Attach File, 85%), and correct empty result for a
  genuine case question
- `intent_engine.is_ui_help_query()` correctly separates UI questions
  from real case questions on every test phrase tried
