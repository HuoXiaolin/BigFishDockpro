"""Verify upstream PresentMon and brand the packaged copy's icon."""
import hashlib
import os
import shutil
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/GameTechDev/PresentMon/releases/download/v2.3.1/PresentMon-2.3.1-x64.exe'
SHA='364e5d98d4d134bd54dd25c22ed2ca2f4883f8bc3ed6502bee0c151e3436d30c'
TARGET=ROOT/'artifacts'/'presentmon'/'PresentMon.exe'
ORIGINAL=TARGET.with_name('PresentMon-2.3.1-original.exe')

def verified(path):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == SHA


def prepare():
    import pefile
    from PyInstaller.utils.win32.icon import CopyIcons_FromIco

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if not verified(ORIGINAL):
        if verified(TARGET):
            data = TARGET.read_bytes()
        else:
            with urlopen(Request(URL, headers={'User-Agent': 'BigFishDockpro-build'}), timeout=35) as response:
                data = response.read(4 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != SHA:
            raise ValueError('PresentMon does not match the official x64 release digest.')
        pending = ORIGINAL.with_suffix('.pending')
        pending.write_bytes(data)
        os.replace(pending, ORIGINAL)

    staged = TARGET.with_suffix('.pending.exe')
    shutil.copyfile(ORIGINAL, staged)
    CopyIcons_FromIco(str(staged), [str(ROOT/'assets'/'dock.ico')])
    # An icon resource changes the Authenticode hash of the derivative.
    with pefile.PE(str(staged)) as image, pefile.PE(str(ORIGINAL)) as vendor:
        directory = image.OPTIONAL_HEADER.DATA_DIRECTORY[4]
        directory.VirtualAddress = directory.Size = 0
        source_code = next(section for section in vendor.sections if section.Name.rstrip(b'\0') == b'.text')
        packaged_code = next(section for section in image.sections if section.Name.rstrip(b'\0') == b'.text')
        if source_code.get_data() != packaged_code.get_data():
            raise ValueError('Adding the PresentMon icon changed executable code.')
        image.OPTIONAL_HEADER.CheckSum = image.generate_checksum()
        staged.write_bytes(image.write())
    os.replace(staged, TARGET)
    return TARGET

if __name__=='__main__':print(prepare())
