import re
from datetime import date
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel

ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_iso_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and ISO_DATE_PATTERN.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD, e.g. 2026-10-02.")


IsoDate = Annotated[date, BeforeValidator(parse_iso_date)]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


T = TypeVar("T")


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
