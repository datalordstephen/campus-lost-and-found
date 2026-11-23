# Deploying a public demo (Hugging Face Spaces)

The app runs as one container: FastAPI serves the API and the built React app
from the same address. A free Hugging Face Space (2 CPUs, 16 GB RAM) has room
for both models; most free hosts (around 512 MB) do not.

## One-time setup

1. Push this repository to GitHub (the Space builds from `main`).
2. On huggingface.co: **New Space** → name it (e.g. `campus-lost-and-found`) →
   **Docker** → **Blank** → **Public** → **Create Space**.
3. In the Space, **Files** → **Add file** → **Upload files**: upload
   `deploy/huggingface/Dockerfile` and `deploy/huggingface/README.md`
   (replacing the Space's own README). Commit.
4. **Settings** → **Variables and secrets** → **New secret**, twice:
   - `SECRET_KEY`: output of `python -c "import secrets;print(secrets.token_urlsafe(48))"`
   - `FERNET_KEY`: output of `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`
5. Wait for the build (about 10–15 minutes the first time). The **Logs** tab
   shows progress; the app is up when it reads `Uvicorn running on
   http://0.0.0.0:7860` and the demo seed has finished.

The public link is `https://<your-username>-<space-name>.hf.space`.

## Updating

After pushing new commits to GitHub: **Settings** → **Factory rebuild**.

## What to know

- **Nothing persists.** A free Space has no disk that survives a restart, and it
  sleeps after about two days without visitors. Each start recreates the demo
  accounts and items (`SEED_DEMO=1`); anything added by hand is lost. Set a
  Space variable `SEED_DEMO=0` to start empty instead.
- **The demo accounts are public.** Their password is in `scripts/seed_demo.py`,
  so anyone with the link can sign in as the admin. That is fine for a demo of
  sample data; do not put real items or personal details into it.
- **The first request after waking is slow** (the Space has to start). Open the
  link a few minutes before you need it.
- **Ownership verification** uses the reverse rule (`NLI_RULE=reverse`), as in
  development.
