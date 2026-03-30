from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchQuery:
    text: str


@dataclass(frozen=True)
class PackageMutation:
    app: str
    run_uninstall: bool = True


@dataclass(frozen=True)
class ApiResult:
    payload: dict[str, Any]
    status: int = 200
