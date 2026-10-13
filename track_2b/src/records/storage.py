import hashlib
from pathlib import Path
import re
from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload

LIMIT = 10 * 1024 * 1024


class StorageError(Exception):
    pass


class LimitedUploadHandler(FileUploadHandler):
    def __init__(self, request=None):
        super().__init__(request)
        self.total = 0

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if self.total > LIMIT:
            self.request.upload_too_large = True
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None


def read_upload(upload):
    data = bytearray()
    for chunk in upload.chunks():
        data.extend(chunk)
        if len(data) > LIMIT:
            raise ValueError('File exceeds the 10 MB limit.')
    if not data:
        raise ValueError('Empty file.')
    name = upload.name.replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'[\x00-\x1f\x7f]', '_', name)[:180] or 'document'
    suffix = Path(name).suffix.lower()
    formats = [('application/pdf', data.startswith(b'%PDF-'), ('.pdf',)),
               ('image/png', data.startswith(b'\x89PNG\r\n\x1a\n'), ('.png',)),
               ('image/jpeg', data.startswith(b'\xff\xd8\xff'), ('.jpg', '.jpeg')),
               ('application/dicom', len(data)>132 and data[128:132]==b'DICM', ('.dcm', '.dicom'))]
    media = next((mime for mime, valid, suffixes in formats if valid and suffix in suffixes), None)
    if not media:
        raise ValueError('Upload a PDF, JPEG, PNG or Part 10 DICOM with matching file content and extension.')
    return bytes(data), name, media


def object_path(key):
    if not re.fullmatch(r'[0-9a-f-]{36}/[0-9a-f-]{36}', key):
        raise StorageError('Invalid private object reference.')
    root = settings.PRIVATE_STORAGE_ROOT.resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise StorageError('Invalid private object reference.')
    return path


def write_original(key, data):
    path = object_path(key)
    opened=False
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open('xb') as output:
            opened=True
            output.write(data)
        path.chmod(0o400)
    except OSError:
        if opened:
            try:
                path.unlink()
            except OSError:
                pass
        raise StorageError('Private storage is unavailable.') from None


def read_original(version):
    try:
        data = object_path(version.private_object_key).read_bytes()
    except OSError:
        raise StorageError('Original is unavailable.') from None
    if len(data) != version.byte_size or hashlib.sha256(data).hexdigest() != version.sha256:
        raise StorageError('Original integrity check failed.')
    return data
