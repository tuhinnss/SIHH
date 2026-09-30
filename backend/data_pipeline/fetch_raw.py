"""Dump all gov.in.is.* items via the archive.org Scraping API (cursor-based; the
advancedsearch API caps deep paging at 10,000) to data/raw/ia_docs.jsonl."""
import json

from tqdm import tqdm

from data_pipeline.common import RAW, polite_get_json

URL = "https://archive.org/services/search/v1/scrape"
COUNT = 5000


def main() -> None:
    params = {"q": "identifier:gov.in.is.*", "fields": "identifier,title,date", "count": COUNT}
    docs: dict[str, dict] = {}
    bar = None
    while True:
        data = polite_get_json(URL, params)
        if bar is None:
            bar = tqdm(total=data.get("total"), desc="items")
        for d in data["items"]:
            docs[d["identifier"]] = d
        bar.update(len(data["items"]))
        cursor = data.get("cursor")
        if not cursor:
            break
        params = {**params, "cursor": cursor}
    RAW.mkdir(parents=True, exist_ok=True)
    with open(RAW / "ia_docs.jsonl", "w", encoding="utf-8") as f:
        for d in docs.values():
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"unique items: {len(docs)}")


if __name__ == "__main__":
    main()
