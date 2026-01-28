# React Migration Notes — Restart Container

## Legacy Behavior
- The restart action lives on the legacy `/settings` Jinja page as a special tile at the bottom of the grid.
- Tile styling: red border, two confirm dialogs via `confirm()` before calling `/api/settings/restart` using `fetch`.
- After POST succeeds, DOM overlay is injected manually: full-screen dark backdrop, emoji, countdown from 10 seconds, then `window.location.reload()`.
- No backend progress indicator; if the request fails, `alert()` displays the failure.

## API Surface
- Endpoint: `POST /api/settings/restart` (no body).
- Response example: `{ "message": "Restart initiated" }`.
- Endpoint restarts the Docker container (or underlying process) and returns immediately.

## UX Requirements to Mirror
1. **Double confirmation**:
   - First confirmation warns about downtime and pauses in telemetry.
   - Second confirmation is the final “can’t undo” step.
2. **Countdown overlay**:
   - After sending the POST, show a blocking overlay with a countdown from 10 seconds.
   - Auto reload when the countdown hits zero.
3. **Transparency around impact**:
   - Communicate that miners keep hashing but API/UI will be offline for ~10s.
   - Advise running during low-activity windows.
4. **Failure handling**:
   - If the POST fails, display an error and reset confirmations so the user can retry.

## React Conversion Considerations
- Provide inline warnings instead of `alert()` popups; leverage cards/banners for context.
- Use a mutation hook to call the restart endpoint and reflect pending state on the main button.
- Maintain local countdown state; use `useEffect` to tick every second and reload when reaching zero.
- Overlay / modal components should trap clicks (use `aria-modal` + `role="dialog"`).
- Ensure hitting Escape or cancel resets to the idle state.
- Keep styling aligned with existing React settings pages (cards, `Button`, etc.).
