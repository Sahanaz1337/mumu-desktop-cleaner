#!/usr/bin/env python3
"""Build MuMu Desktop Cleaner from the source generators in src/.
The APK is signed locally; no developer signing key is shipped in this repository.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'src'
DEST=ROOT/'dist'/'MuMu-Desktop-Cleaner-v1.0.apk'

def main():
    for command in (['java','-version'],['keytool','-help'],['jarsigner','-help']):
        try:
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except FileNotFoundError:
            raise SystemExit('JDK tool not found: '+command[0])
    for tool in ('ui_builder.py','hook_builder.py','assemble.py'):
        subprocess.run([sys.executable,str(SOURCE/tool)],cwd=SOURCE,check=True)
    DEST.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(SOURCE/'MuMu-Desktop-Cleaner-V1.0.apk',DEST)
    subprocess.run([sys.executable,str(ROOT/'tests'/'check_apk.py'),str(DEST)],check=True)
    print('Built:',DEST)

if __name__=='__main__':main()
