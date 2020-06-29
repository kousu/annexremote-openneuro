
from . import __version__

import os
import io
import asyncio
import posixpath # posixpath because that's the format the remote side uses
import random

import warnings

import logging

import requests  # for downloads; TODO: don't use two different http libraries
from aiogqlc import GraphQLClient # for uploads

from urllib.parse import urlparse

class OpenNeuroError(Exception): pass

def asyncio_run(*args, **kwargs):
    return asyncio.get_event_loop().run_until_complete(*args, **kwargs)
    # in python3.8 this is just 'asyncio.run()'

async def execute(graphql, query, variables=None, operation=None):
    "execute a GraphQL statement with error handling"
    # TODO: this should be down in the graphql library, like requests.Response.raise_for_status()
    response = await graphql.execute(query, variables=variables, operation=operation)

    # openneuro's GraphQL server sometimes gives HTTP error codes,
    # but often happily gives 200 OK even on errors
    # TODO: handle response.status != 200
    #       the trouble is...in the few cases I've observed that cause that, the errors are still formatted GraphQL-style.
    #       so it makes sense to ignore the HTTP codes and just look in the returned JSON
    #       but what if the GraphQL server itself is broken and not returning JSON?

    response = await response.json()
    if 'errors' in response:
        errors = response['errors']
        if len(errors) == 1:
            # common case: there's usually (always??) only one error returned
            # so strip away the extra wrapping in that case
            errors = errors[0]
            errors = errors['message']
        #errors = pformat(errors) # DEBUG for readability;
        # what I should actually do is extract error['message'], error['extensions']['code'] and maybe error['extensions']['exception']['stackstrace'] and turn them into python exceptions
        raise OpenNeuroError(errors)
    elif 'data' in response:
        return response['data']
    else:
        raise RuntimeError('No data returned')

def execute_sync(graphql, query, variables=None, operation=None):
    "execute a GraphQL query, blockingly and with error handling"

    # plugging asyncio to not asyncio is awkward :/
    # it would be nice if `await x` when not in an async context
    # was shorthand for asyncio.run(x) (ie. it just became a blocking call)
    # or if *all* of python was async'd, like Javascript, so that you're always on an async thread and there's no need to notate it
    return asyncio_run(execute(graphql, query, variables=variables, operation=operation))

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

    # according to schema introspection, these are the 'mutations' (i.e. inserts/commands) available:
    # >>> a.fields.keys()
    # odict_keys(['createDataset', 'deleteDataset', 'createSnapshot', 'deleteSnapshot', 'updateFiles', 'deleteFiles', 'deleteFile', 'updatePublic', 'updateSummary', 'updateValidation', 'updateSnapshotFileUrls', 'updatePermissions', 'removePermissions', 'removeUser', 'setAdmin', 'setBlocked', 'trackAnalytics', 'followDataset', 'starDataset', 'publishDataset', 'updateDescription', 'updateDescriptionList', 'updateReadme', 'addComment', 'editComment', 'subscribeToNewsletter', 'addMetadata', 'updateRef'])

    def __init__(self, auth_token=None, server='https://openneuro.org'):
        self.auth_token = auth_token
        self.server = server
        # TODO: normalize server (urllib.parse) to ensure it has no trailing /
        self._graphql = GraphQLClient(
            f'{server}/crn/graphql',
            headers={'Cookie': f'accessToken={auth_token}'} if auth_token else {})

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

    def _download(self, url, target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        response = self._session.get(url, stream=True)
        with open(target, 'wb') as fp:
            for chunk in response.iter_content(chunk_size=2048):
                if chunk:
                    fp.write(chunk)

    def files(self, dataset, version=None):
        url = self._datasetUrl(dataset, version)
        r = self._session.get(url)
        r.raise_for_status()
        r = r.json()
        assert r['datasetId'] == dataset # TODO: turn into a warning / other exception?
        return r['files']
        return r.json()

    def downloadFile(self, dataset, file, target=None, version=None):
        if target is None: target = file # XXX check for directory traversal (use os.path.relpath?)

        m = self.fileDetails(dataset, file, version=version)
        if not m['urls']:
            raise NotFoundError(f'{file} is indexed but has no URLs to download from.')
        url = random.choice(m['urls']) # should we always take the first? the last? try to find the closest mirror?
        return self._download(url, target)

    def fileDetails(self, dataset, file, version=None):
        # there does not seem to be *any* API, either in GraphQL or not,
        # for just asking "is a file there?"
        # The only API is to download the *entire* file list best we can do is
        # Maybe we should cache .files()? Python 3.8 has https://docs.python.org/3/library/functools.html#functools.cached_property in the stdlib

        files = self.files(dataset, version=version)
        for metadata in files:
            if metadata['filename'] == file:
                return metadata
        raise NotFoundError(f'{file} not found in {dataset} (at version {version}. {len(files)} were found but not the one you seek.')

    def downloadDataset(self, dataset, version=None, path=None):
        if path is None:
            path = os.getcwd()
        os.makedirs(path, exist_ok=True)
        for m in self.files(dataset, version=None):
            try:
                self._download(random.choice(m['urls']), os.path.join(path, m['filename'])) # XXX fix the directory traversal vuln here
            except Exception:
                # log it but continue
                logging.exception(f"Unable to download {m['filename']}")
                continue

    def publishDataset(self, dataset):
        query = '''
            mutation($dataset: ID!) {
                publishDataset(datasetId: $dataset)
            }
        '''
        variables = {
            'dataset': dataset,
        }
        response = execute_sync(self._graphql, query, variables)
        if response['publishDataset'] != True:
            # it would be strange to get as far as getting a true/false
            # and *not* having the publish work
            raise RuntimeError('Dataset failed to publish.') # ?

    def deleteDataset(self, dataset):
        query = '''
            mutation deleteDataset($id: ID!) {
                deleteDataset(id: $id)
            }
        '''
        variables = {
            'id': dataset,
        }
        response = execute_sync(self._graphql, query, variables, operation="deleteDataset")
        print("delete", dataset, response)
        if response['deleteDataset'] != True:
            raise RuntimeError('Dataset failed to delete.') # ?

    def createDataset(self, label="", metadata=None):
        if label != "":
            # https://github.com/OpenNeuroOrg/openneuro/issues/1679
            warnings.warn("createDataset() ignores the label passed to it.")

        query = '''
            mutation createDataset($label: String!) {
                createDataset(label: $label) {
                    id
                }
            }
        '''
        variables = {
            'label': label
        }

        response = execute_sync(self._graphql, query, variables)
        return response['createDataset']['id']

    def updateDescription(self, dataset, field, value):
        """
        Set the value of a metadata field in a dataset.

        This is effectively just a shortcut for updating the
        contents of the dataset's /dataset_description.json.

        Examples:

        Set the dataset's title.
        >>> client.updateDescription('ds000001', 'Name', 'MRI Scans')

        Beware:
        This will fail if dataset_description.json is missing or otherwise corrupted.
        See https://github.com/OpenNeuroOrg/openneuro/issues/1680.

        For a workaround, explicitly-initialize it:
        >>> client.uploadFile(id, io.BytesIO(b"{}"), "dataset_description.json")
        """
        query = '''
            mutation updateDescription($datasetId: ID!, $field: String!, $value: String!) {
              updateDescription(datasetId: $datasetId, field: $field, value: $value) {
                id
              }
            }
        '''
        variables = {
            'datasetId': dataset,
            'field': field,
            'value': value
        }

        response = execute_sync(self._graphql, query, variables, operation="updateDescription")
        return response['updateDescription']

    def uploadFile(self, dataset, file, path=None):
        """
        Upload a file to a dataset.

        dataset: the dataset ID to upload to
        file: either a filename or an open file-like object.
        path: (optional) the path within the dataset to upload the file to.
              If file is a file-like object, path must be given explicitly.

        Caveats:
        We only support uploading one file at a time (you can use a loop)
        and we don't support uploading empty folders, even though openneuro
        supports both empty folders and batch uploads.
        """

        # OpenNeuro implements this [experimental spec](https://github.com/jaydenseric/graphql-multipart-request-spec)
        # for taking file uploads attached to GraphQL.
        # it allows batching files, but we don't support that yet because it's tricky to get right.
        # (the bandwidth overhead of just calling this multiple times is neglible compared
        #  to the size of most files stored on openneuro anyway)

        if not isinstance(file, io.IOBase):
            # file is a filename
            if path is None:
                # and path wasn't given, so default the filename to the path
                path = file
            file = open(file, 'rb')
        else:
            # file is an open file/socket/something
            if path is None:
                # and path wasn't given, but we don't know the filename so we cannot
                raise TypeError("file must be a filename in order to guess upload path.")

        # Reformat the path to the file as a [FileTree](https://github.com/OpenNeuroOrg/openneuro/blob/51aef9b199d643c07791dc3942c917291551eb73/packages/openneuro-server/src/graphql/schema.js#L176-L181)
        # containing a single file which is actually
        # rather complicated.
        # Build the FileTree inside-out:

        # First, the root node, the file to upload:
        components = path.split('/') # TODO: use os.path or PathLib; also, think about directory traversal?
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
        # TODO: it would be good to get a progressbar in here.
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

        response = execute_sync(self._graphql, query, variables)
        return response['updateFiles']['dataset']

    def deleteFile(self, dataset, path) -> bool:
        """
        dataset: a dataset ID
        path: the file path within the dataset to delete

        Returns: whether the file was deleted or not.

        Beware:
        This method never explains failures -- exceptions are swallowed into
        False -- and sometimes False is even incorrectly raised on success:
        https://github.com/OpenNeuroOrg/openneuro/issues/1683
        So the return value is unreliable.
        """

        query = '''mutation deleteFile($datasetId: ID!, $path: String!, $filename: String!) {
          deleteFile(datasetId: $datasetId, path: $path, filename: $filename)}
        '''
        variables = {
            'datasetId': dataset,
            'path': posixpath.dirname(path),
            'filename': posixpath.basename(path)
        }

        response = execute_sync(self._graphql, query, variables, operation="deleteFile")
        return response['deleteFile'] # whether the file was deleted or not
