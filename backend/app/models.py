from sqlmodel import Field, SQLModel


class StandardRow(SQLModel, table=True):
    __tablename__ = "standards"
    identifier: str = Field(primary_key=True)
    key: str = Field(index=True)
    is_number: str = Field(index=True)
    designation: str
    number: str = Field(index=True)
    part: str | None = None
    section: str | None = None
    year: int | None = Field(default=None, index=True)
    title: str
    flags: str = ""
    source_url: str
    ia_date: str | None = None
    scope_snippet: str | None = None


class EdgeRow(SQLModel, table=True):
    """Relations between standards. edge_type: supersedes | normative_ref | test_method |
    terminology | same_series. For `supersedes`, src is the NEWER standard, dst the older."""
    __tablename__ = "edges"
    id: int | None = Field(default=None, primary_key=True)
    src_key: str = Field(index=True)
    dst_key: str = Field(index=True)
    edge_type: str = Field(index=True)
    source: str | None = None
