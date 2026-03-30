from typing import Protocol


class PackageSearchPort(Protocol):
    def search(self, query: str, urlquote_fn):
        ...


class ExtensionSearchPort(Protocol):
    def search(self, query: str):
        ...
