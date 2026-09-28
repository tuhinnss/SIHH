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
