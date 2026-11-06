"""Fetch the pinned official standalone PresentMon console, with no service installer."""
import hashlib
import os
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/GameTechDev/PresentMon/releases/download/v2.3.1/PresentMon-2.3.1-x64.exe'
SHA='364e5d98d4d134bd54dd25c22ed2ca2f4883f8bc3ed6502bee0c151e3436d30c'
TARGET=ROOT/'artifacts'/'presentmon'/'PresentMon.exe'

def prepare():
    if TARGET.is_file() and hashlib.sha256(TARGET.read_bytes()).hexdigest()==SHA:return TARGET
    with urlopen(Request(URL,headers={'User-Agent':'BigFishDockpro-build'}),timeout=35) as response:
        data=response.read(4*1024*1024)
    if hashlib.sha256(data).hexdigest()!=SHA:raise ValueError('PresentMon does not match the official x64 release digest.')
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    pending=TARGET.with_suffix('.pending');pending.write_bytes(data);os.replace(pending,TARGET)
    return TARGET

if __name__=='__main__':print(prepare())
