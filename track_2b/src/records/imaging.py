"""Bounded technical inspection, without findings or clinical interpretation.

Run only in the resource-limited processing child, never during an HTTP upload.
"""
from io import BytesIO
import re
import warnings
import pydicom
from pydicom.uid import UID
from PIL import Image, ImageOps
from .storage import read_original

PIXEL_LIMIT = 16_000_000
PREVIEW_LIMIT = 1024 * 1024
Image.MAX_IMAGE_PIXELS = PIXEL_LIMIT
DICOM_FIELDS = {
    'Modality': '0008,0060', 'StudyDate': '0008,0020',
    'InstitutionName': '0008,0080', 'StudyDescription': '0008,1030',
    'SeriesDescription': '0008,103E', 'StudyInstanceUID': '0020,000D',
    'SeriesInstanceUID': '0020,000E', 'SOPInstanceUID': '0008,0018',
}


def inspect_image(version):
    data = read_original(version)
    if version.media_type == 'application/dicom':
        return inspect_dicom(data)
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        with Image.open(BytesIO(data)) as image:
            expected = {'image/jpeg': 'JPEG', 'image/png': 'PNG'}[version.media_type]
            if image.format != expected or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Unsupported raster image.')
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > PIXEL_LIMIT:
                raise ValueError('Image dimensions exceed the inspection limit.')
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((512, 512))
            # Copy pixels into a fresh image; never copy EXIF/GPS/header metadata.
            preview = Image.new('RGB', image.size)
            preview.paste(image)
            output = BytesIO()
            preview.save(output, format='PNG')
    png = output.getvalue()
    if len(png) > PREVIEW_LIMIT:
        raise ValueError('Preview exceeds the inspection limit.')
    return ({'format': expected, 'width': width, 'height': height, 'frames': 1,
             'preview_status': 'available', 'clinical_interpretation': 'not_performed'},
            png, 'Pillow-' + Image.__version__)


def inspect_dicom(data):
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        ds = pydicom.dcmread(BytesIO(data), force=False, stop_before_pixels=True,
                             specific_tags=[*DICOM_FIELDS, 'Rows', 'Columns', 'NumberOfFrames', 'SOPClassUID'])
        meta = ds.file_meta
        for value in (ds.get('SOPInstanceUID', ''), ds.get('SOPClassUID', ''),
                      meta.get('TransferSyntaxUID', ''), meta.get('MediaStorageSOPInstanceUID', ''),
                      meta.get('MediaStorageSOPClassUID', '')):
            if not value or not UID(str(value)).is_valid:
                raise ValueError('Missing or invalid DICOM UID.')
        if ds.SOPInstanceUID != meta.MediaStorageSOPInstanceUID or ds.SOPClassUID != meta.MediaStorageSOPClassUID:
            raise ValueError('DICOM file metadata does not match the dataset.')
        rows, columns = int(ds.get('Rows', 0)), int(ds.get('Columns', 0))
        frames = int(ds.get('NumberOfFrames', 1))
        if not 1 <= rows <= 65535 or not 1 <= columns <= 65535 or not 1 <= frames <= 100000:
            raise ValueError('Unsupported DICOM image dimensions.')
        fields = {}
        for keyword, tag in DICOM_FIELDS.items():
            value = ds.get(keyword)
            if value is None or str(value) == '':
                continue
            value = str(value)
            if len(value) > 180 or re.search(r'[\x00-\x1f\x7f]', value):
                raise ValueError('Invalid DICOM header value.')
            if keyword.endswith('UID') and not UID(value).is_valid:
                raise ValueError('Invalid DICOM UID.')
            fields[keyword] = {'tag': tag, 'value': value}
        if not re.fullmatch(r'[A-Z0-9_]{1,16}', fields.get('Modality', {}).get('value', '')):
            raise ValueError('Missing or invalid modality.')
        return ({'format': 'DICOM', 'rows': rows, 'columns': columns, 'frames': frames,
                 'sop_class_uid': str(ds.SOPClassUID), 'transfer_syntax_uid': str(meta.TransferSyntaxUID),
                 'header_fields': fields, 'metadata_status': 'source_header_unverified',
                 'preview_status': 'external_dicom_viewer_required',
                 'pixel_validation': 'not_performed', 'clinical_interpretation': 'not_performed'},
                None, 'pydicom-' + pydicom.__version__)
