# React Migration Notes — Legacy UI Retirement

## Previous Behavior
- `/` rendered `app/ui/templates/dashboard_asic.html` via the legacy FastAPI router (`app/ui/routes.py`).
- Every navigation branch (miners, pools, automation, settings, etc.) depended on Jinja templates plus inline scripts located under `app/ui/templates/`.
- React lived under `/app`, meaning operators had to browse to `/app` manually to reach the new experience.

## New Behavior
- The FastAPI root route now redirects to `/app`, making the React SPA the default experience for every visit.
- The legacy router and Jinja templates were removed entirely, eliminating the chance of falling back to outdated views.
- Only the React build (served from `app/ui/static/app`) remains, so all navigation flows run through the SPA.

## Notes
- No API endpoints were changed—`/api/**` continues to serve the same FastAPI JSON responses that back the SPA.
- If the React bundle is missing (for example in a fresh checkout before running `npm run build`), the server responds with a JSON error so the issue is obvious during development.
