"""Verify and stage the managed fan library used by the Windows resource probe."""
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.9.6'
SHA256 = '086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001'
URL = f'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v{VERSION}/LibreHardwareMonitor.zip'
ARCHIVE = ROOT / 'artifacts' / f'LibreHardwareMonitor-{VERSION}.zip'
OUTPUT = ROOT / 'artifacts' / 'fan-monitor-libraries'


def prepare():
    if not ARCHIVE.is_file() or sha256(ARCHIVE.read_bytes()).hexdigest() != SHA256:
        with urlopen(Request(URL, headers={'User-Agent': 'BigFishDockpro-build'}), timeout=35) as response:
            data = response.read(10 * 1024 * 1024 + 1)
        if sha256(data).hexdigest() != SHA256:
            raise ValueError('LibreHardwareMonitor release checksum mismatch.')
        ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        pending = ARCHIVE.with_suffix('.pending')
        pending.write_bytes(data)
        pending.replace(ARCHIVE)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    libraries = []
    with ZipFile(ARCHIVE) as package:
        for name in sorted(package.namelist()):
            if '/' in name or not name.endswith('.dll'):
                continue
            if not (name.startswith(('System.', 'Microsoft.Bcl.')) or name in {
                'LibreHardwareMonitorLib.dll', 'DiskInfoToolkit.dll', 'BlackSharp.Core.dll',
                'RAMSPDToolkit-NDD.dll', 'HidSharp.dll',
            }):
                continue
            target = OUTPUT / name
            data = package.read(name)
            if not target.is_file() or target.read_bytes() != data:
                target.write_bytes(data)
            libraries.append(target)
    return libraries
