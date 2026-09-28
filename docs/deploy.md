# Deploying the demo (Render, free tier)

`render.yaml` defines two free web services in Singapore:

| Service | Build | Serves |
|---|---|---|
| `drillsage-api` | `uv sync`, then `drillsage-data fetch` and `snapshot` (downloads the pinned public Volve DDR mirror and Sodir tables, builds the field snapshot) | FastAPI on `$PORT`; no database needed |
| `drillsage-web` | `pnpm install`, `next build` (standalone output) | Next.js server; finds the API from `API_RENDER_HOST` |

## First deploy

1. Push the repository to GitHub.
2. On [render.com](https://render.com), sign in with GitHub, then **New > Blueprint**, pick the
   repository, and **Apply**. Render creates both services and builds them (about 5 to 10
   minutes).
3. Open the `drillsage-web` URL.

Every push to `main` redeploys both services.

## Things to know

- **Cold starts.** Free services sleep after 15 minutes idle. The first visit afterwards
  wakes the web service, which then waits up to 60 s (`API_TIMEOUT_MS`) for the API to wake.
  Open the site a minute before presenting.
- **If the web shows "Dead air"** after the API is up, the derived API address is wrong: set
  `API_INTERNAL_URL` on `drillsage-web` to the API's URL (for example
  `https://drillsage-api.onrender.com`) and redeploy.
- **No database in the demo.** The status light reads "DB offline · snapshot"; events come
  from the rule tier in the snapshot.
- **Data licence.** The deployed site shows Volve data under CC BY-NC-SA 4.0 with the
  required attribution in every page footer; keep it non-commercial.
