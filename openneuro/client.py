
from . import __version__

import io
import asyncio

import requests  # for downloads; TODO: don't use two different http libraries
from aiogqlc import GraphQLClient # for uploads

from urllib.parse import urlparse

def asyncio_run(*args, **kwargs):
    return asyncio.get_event_loop().run_until_complete(*args, **kwargs)
    # in python3.8 this is just 'asyncio.run()'

async def execute(graphql, query, variables=None):
    "execute a GraphQL statement with error handling"
    # TODO: this should be down in the graphql library, like requests.Response.raise_for_status()
    response = await graphql.execute(query, variables=variables)
    if response.status != 200:
        raise RuntimeError(await response.text())
    response = await response.json()
    response = response['data']
    return response

def execute_sync(graphql, query, variables=None):
    "execute a GraphQL query, blockingly and with error handling"

    # plugging asyncio to not asyncio is awkward :/
    # it would be nice if `await x` when not in an async context
    # was shorthand for asyncio.run(x) (ie. it just became a blocking call)
    # or if *all* of python was async'd, like Javascript, so that you're always on an async thread and there's no need to notate it
    return asyncio_run(execute(graphql, query, variables))

class NamedStream(io.IOBase):
    """
    A filestream with an explicit .name, chosen by the user.
    io.FileIO has this, and it is used internally (implicitly) by aiohttp, which aioqglc uses,
    to send the filename= attribute on file uploads, which is then used by OpenNeuro to
    name the file. If we're just mirroring an existing folder structure this is fine,
    but if we want to upload to a chosen name or pipe off a socket or even a pipe we can't.

    We could change aioqglc to call aiohttp's add_field(name, fp, filename) instead of add_fields()
    but we would also have to find some way to pass the filename in along with the
    GraphQL variables argument.
    """
    def __init__(self, name, stream):
        self.wrapped = stream
        self.name = name
    def __getattr__(self, name):
        # recall: this is only run as a fallback
        return getattr(self.wrapped, name)

class Client:
    """
    API client for https://openneuro.org.

    Caveats:
    - an incorrect auth token sometimes causes 500s instead of 403s like it should
    - cannot handle batch file uploads (you can just write a loop and it's almost as good)
    """
    def __init__(self, auth_token=None, server='https://openneuro.org'):
        self.auth_token = auth_token
        self.server = server
        # TODO: normalize server (urllib.parse) to ensure it has no trailing /
        self._graphql = GraphQLClient(
            'https://openneuro.org/crn/graphql',
            headers={'Cookie': f'accessToken={auth_token}'})

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
        # weirdly, this link behaves differently in curl and firefox and python:
        # in firefox, it gives a .zip; with scripts, it gives json? what?
        return url

    def files(self, dataset, version=None):
        url = self._datasetUrl(dataset, version)
        r = self._session.get(url)
        r.raise_for_status()
        r = r.json()
        assert r['datasetId'] == dataset # TODO: turn into a warning / other exception?
        return r['files']
        return r.json()

    def downloadDataset(dataset):
        raise NotImplemented()
        # TODO: use the GraphQL API?

    def publishDataset(self, dataset):
        raise NotImplemented()

    def deleteDataset(self, dataset):
        raise NotImplemented()

    def createDataset(self, description="", metadata=None):
        if metadata is not None:
            raise NotImplemented()

        query = '''
            mutation createDataset {
                createDataset(label: $label) {
                    id
                }
            }
        '''
        variables = {
            'label': description
        }

        response = execute_sync(self._graphql, query, variables)
        return response['createDataset']['id']

    def upload(self, dataset, file, path):

        # TODO: support self.upload(id, "path/to/file.gz"), self.upload(dataset, "/mnt/nfs/path/to/file.gz", "forgotten/place.com/elsewhere.gz") and self.upload(dataset, socket, "forgotten/place.com/elsewhere.zip")

        # OpenNeuro implements an [experimental spec](https://github.com/jaydenseric/graphql-multipart-request-spec) for taking file uploads attached to GraphQL.
        # it allows batching files, but we don't support that here
        # just use a loop.
        # (the bandwidth overhead is neglible compared to the size of most files storedo on openneuro)

        # like git, we also don't support uploading empty folders, even though openneuro allows that?

        # reformat the path to the file as a [FileTree](https://github.com/OpenNeuroOrg/openneuro/blob/51aef9b199d643c07791dc3942c917291551eb73/packages/openneuro-server/src/graphql/schema.js#L176-L181)
        # which is actually rather complicated

        # This builds the FileTree inside-out.

        # First, the root node, the file to upload:
        components = path.split('/') # TODO: use os.path or PathLib; also, think about directory traversal?
        if not isinstance(file, io.IOBase):
            file = open(file, 'rb')
        file = NamedStream(components[-1], file) # set the filename to upload to, explicitly
        components = components[:-1]

        # Then all the parent directories, working upwards:
        # Also notice how, despite having the FileTree,
        #  OpenNeuro needs each folder labelled with a
        #  full path to behave correctly.
        filetree = {'name': '/'.join(components), 'files': [file], 'directories': []}
        while components:
            components = components[:-1]
            filetree = {'name': '/'.join(components), 'files': [], 'directories': [filetree]}

        # Do the upload!
        # TODO: it would be good to get some kind of feedback
        # the js version has a clever hack: wrap the filestream in another stream that prints its .tell() to stderr every so many .read()s
        query = '''
            mutation($dataset: ID!, $files: FileTree!) {
                updateFiles(datasetId: $dataset, files: $files) {
                    dataset {
                        id
                    }
                }
            }
        '''
        variables = {
            'dataset': dataset,
            'files': filetree,
        }

        return execute_sync(self._graphql, query, variables)
