# Deploy on Railway (Shareable URL)

This project is set up to deploy as **one web service** (backend + frontend) using Docker.

## Quick Start (Railway)

1. Push this repo to GitHub.
2. Open Railway and create a new project.
3. Choose **Deploy from GitHub repo** and select this repository.
4. Railway will detect the `Dockerfile` and build/deploy automatically.
5. In Railway Variables, set:
   - `OPENAI_API_KEY` (required for AI features)
   - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (if using Supabase logging/provider storage)
   - `RF_DIAGNOSTICS=0` (optional, quieter logs in production)
6. Open **Settings -> Networking** and generate a public domain.

After deploy, you get a public URL like:

`https://raga-fusion-music-generator.up.railway.app`

Share that URL.

## What This Deployment Serves

- Frontend app at `/`
- API at `/api/*`

So the same URL handles both UI and API.

## Notes

- Railway provides a single public domain per service.
- Generated files in `output/` are ephemeral unless you attach a volume/external storage.
- If the app idles or restarts, local generated files can be lost.
