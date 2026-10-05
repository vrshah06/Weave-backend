from bson import ObjectId
from bson.errors import InvalidId

from core.errors import InvalidRequestError, NotFoundError


def parse_path_id(value: str, resource: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise NotFoundError(f"{resource} not found")


def parse_body_ids(values: list[str], field: str) -> list[ObjectId]:
    invalid = [v for v in values if not ObjectId.is_valid(v)]
    if invalid:
        raise InvalidRequestError(f"Invalid id(s) in {field}: {', '.join(invalid[:10])}")
    return [ObjectId(v) for v in values]
