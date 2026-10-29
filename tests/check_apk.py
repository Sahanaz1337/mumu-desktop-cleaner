#!/usr/bin/env python3
"""Static checks only. Cannot verify Android runtime behavior."""
import sys
import zipfile
from pathlib import Path

def main():
    path=Path(sys.argv[1] if len(sys.argv)>1 else 'dist/MuMu-Desktop-Cleaner-v1.0.apk')
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None,'ZIP integrity failed'
        names=set(z.namelist())
        assert {'AndroidManifest.xml','classes.dex','classes2.dex','assets/xposed_init'} <= names
        manifest=z.read('AndroidManifest.xml')
        ui=z.read('classes2.dex')
        hook=z.read('classes.dex')
        assert b'MuMu Desktop Cleaner V1.0' in ui
        assert b'\xe6\x89\xa7\xe8\xa1\x8c\xe6\x88\x90\xe5\x8a\x9f' in ui
        assert b'\xe6\x8c\x87\xe4\xbb\xa4\xe6\x91\x98\xe8\xa6\x81' not in ui
        assert b'MuMuCleanerV1' in hook
        assert b'com.sahanaz.mumu.vectorcleaner.HookMain' in z.read('assets/xposed_init')
        assert b'1.0' in manifest
    print('PASS: signed-package contents, V1.0 label, concise status text, Xposed entry')

if __name__=='__main__':main()
