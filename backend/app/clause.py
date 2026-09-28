"""Copy-ready tender clause, built ONLY from validated catalogue fields (never LLM text)."""


def tender_clause(is_number: str, year: int | None, title: str) -> str:
    edition = f" : {year}" if year else ""
    return (f"The material/equipment supplied shall conform to {is_number}{edition} "
            f"({title.strip().rstrip('-').strip()}), or the latest edition thereof, "
            "and shall be supported by test reports as per the standard.")
