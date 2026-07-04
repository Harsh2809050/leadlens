# LeadLens — Lead Intelligence

Type a company name + industry → get **direct competitors**, **decision-maker
leads (with LinkedIn URLs)** and a **business intelligence report** (3 growth
levers, 3 kill risks), researched live from the web and cached in SQLite.

## Run it

**Windows:** double-click `start.bat`
**macOS/Linux:** `bash start.sh`

Then open http://127.0.0.1:8787 — the UI is already built and served by the
backend. Just type a company name; the industry is detected automatically.
Try **Notion** first: it's pre-cached with a fully researched, real dataset
(competitors, 10 LinkedIn-verified leads, analyst report) and returns
instantly.

> Port 8787 is used on purpose — port 8000 was already taken by another app
> on this machine.

## How it works

- **Backend** — FastAPI (`backend/`)
  - `GET /api/search?company=` — full payload (industry optional; auto-detected)
  - `/api/competitors`, `/api/leads`, `/api/report` — individual sections
  - `/api/history` — everything researched so far
  - `refresh=1` on any endpoint forces a re-run
- **Research engine** (`backend/research.py`) — scrapes live DuckDuckGo/Bing
  SERPs and real pages: competitor mining via cross-source frequency voting,
  leads via `site:linkedin.com/in` queries, positioning from the company's own
  homepage, trends/stats from market coverage. No API keys needed.
- **Report** (`backend/report.py`) — analyst-style narrative composed strictly
  from gathered data (named competitors, quoted market stats, real leads).
- **Cache** (`backend/db.py`) — SQLite (`backend/leadlens.db`). Every search is
  stored; the same company is never researched twice.
- **Frontend** — React + Vite + Tailwind (`frontend/`), pre-built to
  `frontend/dist` and served by FastAPI. To develop:
  `cd frontend && npm install && npm run dev` (proxies `/api` to :8787).

## Deploy it for other people (free)

The repo is deploy-ready (Dockerfile + render.yaml). To give everyone a
public URL:

1. Push the `leadlens` folder to a GitHub repo
   (`git init && git add . && git commit -m "LeadLens" && git push`).
2. Go to render.com → New → Web Service → connect the repo. Render reads
   `render.yaml` and deploys automatically on the free plan.
3. Recommended: grab a free API key at brave.com/search/api (2,000
   queries/month) and set it as the `BRAVE_API_KEY` environment variable in
   Render. Cloud datacenter IPs get blocked by search engines far more often
   than home IPs — the API fallback keeps research reliable.

Notes for hosted mode: the SQLite cache is shared by all visitors (every
company anyone searches becomes instant for everyone), but Render's free
disk is ephemeral — the cache resets on each deploy. The pre-researched
Notion and Figma datasets ship in `backend/leadlens.db`.

## Notes

- First-time research for a new company takes 1–3 minutes (it is doing real
  web research, politely rate-limited). Cached repeats are instant.
- `backend/seed.py payload.json` lets you inject externally researched data
  into the cache (the Notion dataset was seeded this way from live browser
  research).
