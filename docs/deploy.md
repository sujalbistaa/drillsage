# Deploying the demo (free tiers)

The web app runs on **Netlify** (it never sleeps) and the API on **Render**, kept awake by an
external pinger. `render.yaml` still defines a Render web service as a fallback.

`render.yaml` defines two free web services in Singapore:

| Service | Build | Serves |
|---|---|---|
| `drillsage-api` | `uv sync`, then downloads the field snapshot from the `field-snapshot` GitHub Release and validates it against the code's schema | FastAPI on `$PORT`; no database needed |
| `drillsage-web` | `pnpm install`, `next build` (standalone output) | Next.js server; finds the API from `API_RENDER_HOST` |

The snapshot is built on a developer machine, not at deploy time: Sodir's FactPages do not
answer requests from Render's network. It is a release asset, not a committed file (derived
data stays out of git history).

## First deploy

1. Build and publish the snapshot: `make snapshot-publish` (needs `gh auth login`).
2. Push the repository to GitHub.
3. On [render.com](https://render.com), sign in with GitHub, then **New > Blueprint**, pick the
   repository, and **Apply**. Render creates both services and builds them (about 5 to 10
   minutes).
4. Open the `drillsage-web` URL.

Every push to `main` redeploys both services. After changing the extraction or the snapshot
schema, run `make snapshot-publish` again before pushing; a snapshot that no longer matches
the code fails the API build rather than serving broken data.

## Web on Netlify

1. On [netlify.com](https://netlify.com), **Add new project > Import an existing project**,
   pick the repository. Leave **Base directory** empty and set **Package directory** to
   `apps/web`; `apps/web/netlify.toml` supplies the build command and publish directory.
2. Add two environment variables (all scopes) before deploying:
   - `API_INTERNAL_URL` = `https://drillsage-api.onrender.com`
   - `API_TIMEOUT_MS` = `9000` (stays under the serverless function's time limit; if the API
     is still waking, the page shows "Dead air" and retries itself every 20 s)
3. In **Build & deploy > Branches**, set the production branch to `live` and branch deploys
   to none. The free plan has a hard cap of 300 credits a month and each production deploy
   costs 15, so only deliberate releases deploy: `git push origin main:live`.
4. Deploy.

## Keep the API awake

Render's free tier gives 750 instance hours a month per workspace: enough for one service
running all month (at most 744 h), not two. With the web on Netlify, ping only the API:
create a free job on [cron-job.org](https://cron-job.org) (or an UptimeRobot HTTP monitor)
that requests `https://drillsage-api.onrender.com/healthz` every 10 minutes. Render sleeps a
service after 15 minutes without traffic, so it never sleeps.

Pause the job for three night hours (for example 02:00 to 05:00 IST). That keeps the API near
650 h a month and leaves about 100 h for the Render web service, which still serves the
original `drillsage-web.onrender.com` link (it sleeps when idle and only counts hours while
awake). Going over 750 h suspends every free service in the workspace until the next month.

## Things to know

- **Cold starts.** Free services sleep after 15 minutes idle. The first visit afterwards
  wakes the web service, which then waits up to 60 s (`API_TIMEOUT_MS`) for the API to wake.
  Open the site a minute before presenting.
- **If the web shows "Dead air"** after the API is up, the derived API address is wrong: set
  `API_INTERNAL_URL` on `drillsage-web` to the API's URL (for example
  `https://drillsage-api.onrender.com`) and redeploy.
- **No database in the demo.** `DRILLSAGE_SNAPSHOT_ONLY=true` makes readiness check the field
  snapshot instead of the database; events come from the rule tier in the snapshot.
- **Data licence.** The deployed site shows Volve data under CC BY-NC-SA 4.0 with the
  required attribution in every page footer; keep it non-commercial.
