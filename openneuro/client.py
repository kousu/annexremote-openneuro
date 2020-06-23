
from . import __version__

#import graphql
import requests

from urllib.parse import urlparse

class Client:
    def __init__(self, auth_token=None, server='https://openneuro.org'):
        self.auth_token = auth_token
        self.server = server
        # TODO: normalize server (urllib.parse) to ensure it has no trailing /
        self._graphql = None #graphql.....
        self._session = requests.Session()
        self._session.headers['User-Agent'] = f'python openneuro-client {__version__}'
        if auth_token:
            self._session.cookies.set('accessToken', auth_token, domain=urlparse(server).netloc, path='/')

    def _datasetUrl(self, dataset, version=None):
        # TODO validate the dataset format; make sure it has no /s in it, etc
        url = f'{self.server}/crn/datasets/{dataset}'
        if version is not None:
            url += f'/snapshots/{version}'
        url += '/download'
        return url

    def files(self, dataset, version=None):
        url = self._datasetUrl(dataset, version)
        r = self._session.get(url)
        r.raise_for_status()
        r = r.json()
        assert r['datasetId'] == dataset # TODO: turn into a warning / other exception?
        return r['files']
        return r.json()
