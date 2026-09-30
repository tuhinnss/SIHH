"""Build data/catalogue.jsonl + SQLite `standards` table from the archive.org listing."""
import json

from sqlmodel import Session, SQLModel, create_engine

from app.models import StandardRow
from data_pipeline.common import RAW, ROOT
from data_pipeline.parsing import parse_item, to_dict

DB = ROOT / "data" / "specsure.sqlite"


def main() -> None:
    src = RAW / "ia_docs.jsonl"
    if not src.exists():
        from data_pipeline.fetch_raw import main as fetch
        fetch()
    rows = [r for r in (parse_item(json.loads(l)) for l in open(src, encoding="utf-8")) if r]
    with open(ROOT / "data" / "catalogue.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(to_dict(r), ensure_ascii=False) + "\n")
    DB.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{DB}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for r in rows:
            d = to_dict(r)
            d["flags"] = ",".join(d["flags"])
            s.add(StandardRow(**d))
        s.commit()
    print(f"parsed {len(rows)} standards -> {DB}")


if __name__ == "__main__":
    main()
