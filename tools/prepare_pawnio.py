"""Cache the same official PawnIO installer identified by the Microsoft WinGet manifest."""
import hashlib
import os
from pathlib import Path
from urllib.request import Request,urlopen

URL='https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/PawnIO_setup.exe'
SHA256='1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032'
TARGET=Path(__file__).resolve().parents[1]/'artifacts'/'pawnio'/'PawnIO_setup.exe'


def prepare():
    if TARGET.is_file() and hashlib.sha256(TARGET.read_bytes()).hexdigest()==SHA256:return TARGET
    with urlopen(Request(URL,headers={'User-Agent':'BigFishDockpro-build'}),timeout=35) as response:
        data=response.read(16*1024*1024+1)
    if hashlib.sha256(data).hexdigest()!=SHA256:raise ValueError('PawnIO 2.2.0 package digest differs from WinGet.')
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    pending=TARGET.with_suffix('.pending');pending.write_bytes(data);os.replace(pending,TARGET)
    return TARGET


if __name__=='__main__':print(prepare())
