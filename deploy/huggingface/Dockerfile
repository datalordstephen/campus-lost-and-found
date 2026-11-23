# Hugging Face Space (Docker SDK) for Campus Lost & Found.
#
# This file and README.md are the only files the Space needs: the image clones
# the app from GitHub, builds the React frontend, installs CPU-only PyTorch and
# bakes both model checkpoints in, so startup never waits on a download.
# To pick up new commits, use "Factory rebuild" in the Space settings.
#
# Needs two Space secrets: SECRET_KEY and FERNET_KEY (see DEPLOY.md).

ARG REPO=https://github.com/datalordstephen/campus-lost-and-found.git
ARG REF=main

# --- frontend ---------------------------------------------------------------
FROM node:22-slim AS web
ARG REPO
ARG REF
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${REF}" "${REPO}" /src
WORKDIR /src/frontend
# Same origin as the API, so no VITE_API_URL.
RUN npm ci && npm run build

# --- backend ----------------------------------------------------------------
FROM python:3.11-slim
ARG REPO
ARG REF
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates libgomp1 \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
RUN git clone --depth 1 --branch "${REF}" "${REPO}" /app
COPY --from=web /src/frontend/dist /app/frontend/dist
WORKDIR /app

# Pinned versions from uv.lock, but CPU-only PyTorch: the locked Linux build pulls
# several GB of CUDA libraries that a CPU Space cannot use.
RUN pip install --no-cache-dir uv \
 && uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/req.txt \
 && grep -Ev '^(torch|torchvision|triton|nvidia-[a-z0-9-]+|cuda-[a-z-]+)==' /tmp/req.txt > /tmp/req-cpu.txt \
 && (pip install --no-cache-dir torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cpu \
     || pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu) \
 && pip install --no-cache-dir -r /tmp/req-cpu.txt

RUN chown -R user:user /app
USER user
ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    PORT=7860 \
    FRONTEND_DIST=/app/frontend/dist \
    DATABASE_URL=sqlite:////home/user/data/campus_lost_found.db \
    UPLOAD_DIR=/home/user/data/uploads \
    FAISS_INDEX_PATH=/home/user/data/faiss_index/index.bin \
    CLIP_DEVICE=cpu \
    NLI_RULE=reverse \
    OMP_NUM_THREADS=2 \
    TOKENIZERS_PARALLELISM=false

# Bake the OpenCLIP and NLI checkpoints into the image.
RUN python -c "from backend import clip_encoder, verification; clip_encoder.load_model(); verification.load_model()"
# Demo photos (Wikimedia Commons) for the optional demo seed; not fatal if offline.
RUN python tests/fixtures/download_fixtures.py || echo "fixtures unavailable; demo seed will be skipped"

EXPOSE 7860
CMD ["bash", "deploy/huggingface/start.sh"]
