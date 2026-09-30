"""Build data/catalogue.jsonl + SQLite `standards` table from the archive.org listing.

By default the committed data/catalogue.jsonl snapshot is loaded (reproducible, offline; the
extracted refs and subset were built against it). --refresh re-downloads the archive listing."""
import json
import sys
from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models import StandardRow
from data_pipeline.common import RAW, ROOT
from data_pipeline.parsing import parse_item, to_dict

DB = ROOT / "data" / "specsure.sqlite"
CATALOGUE = ROOT / "data" / "catalogue.jsonl"
META = ROOT / "data" / "catalogue_meta.json"


def main(refresh: bool = False) -> None:
    src = RAW / "ia_docs.jsonl"
    if refresh or (not src.exists() and not CATALOGUE.exists()):
        from data_pipeline.fetch_raw import main as fetch
        fetch()
        META.write_text(json.dumps({"synced": date.today().isoformat()}), encoding="utf-8")
    if src.exists():
        rows = [to_dict(r) for r in (parse_item(json.loads(l)) for l in open(src, encoding="utf-8")) if r]
        with open(CATALOGUE, "w", encoding="utf-8", newline="\n") as f:
            for d in rows:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
    else:
        rows = [json.loads(l) for l in open(CATALOGUE, encoding="utf-8")]
        print(f"loaded committed snapshot {CATALOGUE.name} (use --refresh to re-download)")
    DB.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{DB}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for d in rows:
            s.add(StandardRow(**{**d, "flags": ",".join(d["flags"])}))
        s.commit()
    print(f"parsed {len(rows)} standards -> {DB}")


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
