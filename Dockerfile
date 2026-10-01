# One container: FastAPI serves the API under /api and the built frontend (app.site).
# The data (data/kalamkaar.sqlite, data/indexes/) is NOT built here: build it first, see README.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# Hugging Face Spaces run the container as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user backend/requirements.txt backend/requirements.txt
# CPU torch first, so sentence-transformers does not pull the CUDA build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r backend/requirements.txt

# bake the embedding model into the image: no download when the container starts
ARG EMBED_MODEL=BAAI/bge-m3
ENV EMBED_MODEL=$EMBED_MODEL
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['EMBED_MODEL'], device='cpu')"

COPY --chown=user backend/app backend/app
COPY --chown=user data data
COPY --chown=user --from=web /web/dist frontend/dist

WORKDIR /home/user/app/backend
EXPOSE 7860
CMD ["uvicorn", "app.site:create_site", "--factory", "--host", "0.0.0.0", "--port", "7860"]
