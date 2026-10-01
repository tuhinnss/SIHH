"""Create or update the Hugging Face Space (Docker SDK) that hosts Kalamkaar.

    hf auth login                                    # once; needs a token with write access
    python deploy/push_space.py <user>/kalamkaar     # --private for a private Space

One commit with the Dockerfile, backend/app, the frontend sources, the built data (SQLite + indexes:
metadata and <=800-char scope snippets, no standard texts) and deploy/README.md as the Space card.
GEMINI_API_KEY / GROQ_API_KEY go from .env into Space secrets (never into the repo); --no-secrets
skips that and the Space runs retrieval-only.
"""
import argparse
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import CommitOperationAdd, HfApi

ROOT = Path(__file__).resolve().parents[1]
CODE = ["Dockerfile", ".dockerignore", "backend/app", "backend/requirements.txt", "frontend"]
DATA = ["data/kalamkaar.sqlite", "data/indexes", "data/catalogue_meta.json", "data/certification.csv",
        "data/refs_extracted.jsonl"]
SECRETS = ["GEMINI_API_KEY", "GROQ_API_KEY"]


def bundle() -> list[str]:
    """Repo-relative paths to upload: tracked code (so no node_modules/dist/__pycache__) + built data."""
    out = subprocess.run(["git", "ls-files", "--", *CODE], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout.split("\n")
    files = [p for p in out if p]
    for d in DATA:
        p = ROOT / d
        if not p.exists():
            raise SystemExit(f"{d} is missing: build the data first (fetch_catalogue, build_edges, build_index)")
        found = sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
        files += [f.relative_to(ROOT).as_posix() for f in found]
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo_id", help="<user>/<space name>")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--no-secrets", action="store_true", help="do not copy the LLM keys from .env")
    ap.add_argument("--dry-run", action="store_true", help="list the files and stop")
    args = ap.parse_args()

    files = bundle()
    size = sum((ROOT / f).stat().st_size for f in files) / 1e6
    print(f"{len(files)} files, {size:.0f} MB")
    if args.dry_run:
        print("\n".join(files))
        return

    api = HfApi()
    api.create_repo(args.repo_id, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
    if not args.no_secrets:
        env = dotenv_values(ROOT / ".env")
        for name in SECRETS:
            if env.get(name):
                api.add_space_secret(args.repo_id, name, env[name])
                print(f"secret {name}: set")
            else:
                print(f"secret {name}: not in .env, skipped")
    ops = [CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=str(ROOT / "deploy" / "README.md"))]
    ops += [CommitOperationAdd(path_in_repo=f, path_or_fileobj=str(ROOT / f)) for f in files]
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    api.create_commit(args.repo_id, repo_type="space", operations=ops, commit_message=f"Deploy {head}")
    print(f"https://huggingface.co/spaces/{args.repo_id}")


if __name__ == "__main__":
    main()
