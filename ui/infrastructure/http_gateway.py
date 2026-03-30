import requests


class HttpGateway:
    def __init__(self, get_fn=None):
        self._session = requests.Session()
        self._get_fn = get_fn

    def get(self, url, **kwargs):
        if self._get_fn is not None:
            return self._get_fn(url, **kwargs)
        return self._session.get(url, **kwargs)
