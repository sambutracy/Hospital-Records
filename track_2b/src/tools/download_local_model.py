"""Download and verify the pinned text-only community Apertus conversion."""
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]/'.runtime'/'local-model'
ROOT.mkdir(parents=True,exist_ok=True)
TARGET=ROOT/'apertus-v1.5-8b-text-q4_k_m.gguf'
PART=TARGET.with_suffix('.gguf.part')
URL='https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF/resolve/248ec68a63e219e3f061e4c946fc8a20d63b9975/apertus-v1.5-8b-text-q4_k_m.gguf'
EXPECTED_SIZE=5059027136
EXPECTED_SHA='a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299'

if not TARGET.exists():
    start=PART.stat().st_size if PART.exists() else 0
    if start>EXPECTED_SIZE:
        raise SystemExit('Partial file exceeds expected size.')
    if start<EXPECTED_SIZE:
        request=Request(URL,headers={'Range':f'bytes={start}-'} if start else {})
        with urlopen(request,timeout=90) as response:
            resumed=start>0 and response.status==206
            if resumed and not response.headers.get('Content-Range','').startswith(f'bytes {start}-'):
                raise SystemExit('Unexpected range response.')
            n=start if resumed else 0
            last=n
            with PART.open('ab' if resumed else 'wb') as output:
                while True:
                    data=response.read(8*1024*1024)
                    if not data:
                        break
                    n+=len(data)
                    if n>EXPECTED_SIZE:
                        raise SystemExit('Download exceeds expected size.')
                    output.write(data)
                    if n-last>=512*1024*1024:
                        print(f'{n}/{EXPECTED_SIZE} bytes downloaded',flush=True)
                        last=n
    path=PART
else:
    path=TARGET
sha=hashlib.sha256()
with path.open('rb') as source:
    for data in iter(lambda:source.read(8*1024*1024),b''):
        sha.update(data)
if path.stat().st_size!=EXPECTED_SIZE or sha.hexdigest()!=EXPECTED_SHA:
    raise SystemExit('Model size/checksum mismatch; not activated.')
if path==PART:
    PART.rename(TARGET)
print('Model verified: 5059027136 bytes, expected SHA-256.',flush=True)
