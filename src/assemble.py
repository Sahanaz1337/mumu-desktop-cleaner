#!/usr/bin/env python3
"""Build MuMu Desktop Cleaner release 1.0 (UI Activity + Vector-compatible Xposed hook).
Reuses locally generated, separately verifiable DEX from ui_builder.py and hook_builder.py;
compile minimal binary AndroidManifest.xml, retain old Vector module's signing certificate.
"""
from pathlib import Path
import struct,hashlib,subprocess,zipfile,shutil,os
R=Path(__file__).resolve().parent
PKG='com.sahanaz.mumu.vectorcleaner'
OUTPUT=R/'MuMu-Desktop-Cleaner-V1.0.apk'
ANDROID='http://schemas.android.com/apk/res/android'
ATTR_IDS={'name':0x01010003,'label':0x01010001,'value':0x01010024,
 'minSdkVersion':0x0101020c,'targetSdkVersion':0x01010270,
 'versionCode':0x0101021b,'versionName':0x0101021c,'exported':0x01010010}
strings=['manifest','uses-sdk','application','activity','intent-filter','action','category','meta-data',
  'package','android',ANDROID,'name','value','label','versionCode','versionName','minSdkVersion',
  'targetSdkVersion','exported',PKG,'MuMu 桌面净化 V1.0','1.0',
  'com.sahanaz.lawnchairwidget.MainActivity', 'android.intent.action.MAIN', 'android.intent.category.LAUNCHER',
  'xposedmodule','xposeddescription','xposedminversion','xposedscope',
  'MuMu Android 15 Lawnchair 净化与 Root 控制面板（仅 app.lawnchair）','app.lawnchair']
strings=list(dict.fromkeys(strings)); ix={s:i for i,s in enumerate(strings)}
def chunk(typ,hs,header,body):
 assert len(header)==hs-8
 return struct.pack('<HHI',typ,hs,hs+len(body))+header+body
def length(n):return bytes([n]) if n<=127 else bytes([(n>>8)|128,n&255])
def pool(ss):
 data=bytearray();offset=[]
 for s in ss:
  offset.append(len(data));b=s.encode('utf-8')
  data+=length(len(s.encode('utf-16-le'))//2)+length(len(b))+b+b'\0'
 while len(data)%4:data.append(0)
 return chunk(1,28,struct.pack('<IIIII',len(ss),0,0x100,28+4*len(ss),0),
              b''.join(struct.pack('<I',k) for k in offset)+data)
def attr(name,v,kind='str'):
 ns=ix[ANDROID] if name in ATTR_IDS else 0xffffffff
 if kind=='str':t=3;data=ix[v];raw=data
 elif kind=='int':t=0x10;data=int(v);raw=0xffffffff
 elif kind=='bool':t=0x12;data=int(v);raw=0xffffffff
 else: raise ValueError(kind)
 return struct.pack('<IIIHBBI',ns,ix[name],raw,8,0,t,data)
def node(kind,name='',attrs=()):
 pre=struct.pack('<II',0,0xffffffff)
 if kind in ('ns+','ns-'):return chunk(0x100 if kind=='ns+' else 0x101,16,pre,struct.pack('<II',ix['android'],ix[ANDROID]))
 if kind=='open':return chunk(0x102,16,pre,struct.pack('<IIHHHHHH',0xffffffff,ix[name],20,20,len(attrs),0,0,0)+b''.join(attr(*x) for x in attrs))
 if kind=='close':return chunk(0x103,16,pre,struct.pack('<II',0xffffffff,ix[name]))
 raise ValueError(kind)
ns=[node('ns+'),node('open','manifest',[('package',PKG),('versionCode',5,'int'),('versionName','1.0')]),
 node('open','uses-sdk',[('minSdkVersion',29,'int'),('targetSdkVersion',29,'int')]),node('close','uses-sdk'),
 node('open','application',[('label','MuMu 桌面净化 V1.0')]),
 node('open','activity',[('name','com.sahanaz.lawnchairwidget.MainActivity'),('exported',1,'bool')]),
 node('open','intent-filter'),node('open','action',[('name','android.intent.action.MAIN')]),node('close','action'),
 node('open','category',[('name','android.intent.category.LAUNCHER')]),node('close','category'),
 node('close','intent-filter'),node('close','activity'),
 node('open','meta-data',[('name','xposedmodule'),('value',1,'bool')]),node('close','meta-data'),
 node('open','meta-data',[('name','xposeddescription'),('value','MuMu Android 15 Lawnchair 净化与 Root 控制面板（仅 app.lawnchair）')]),node('close','meta-data'),
 node('open','meta-data',[('name','xposedminversion'),('value',93,'int')]),node('close','meta-data'),
 node('open','meta-data',[('name','xposedscope'),('value','app.lawnchair')]),node('close','meta-data'),
 node('close','application'),node('close','manifest'),node('ns-')]
resmap=chunk(0x180,8,b'',b''.join(struct.pack('<I',ATTR_IDS.get(s,0)) for s in strings))
axml=chunk(3,8,b'',pool(strings)+resmap+b''.join(ns))
with zipfile.ZipFile(R/'hook.apk') as z:hookdex=z.read('classes.dex')
with zipfile.ZipFile(R/'mumu_ui.apk') as z:uidex=z.read('classes.dex')
unsigned=R/'combined_unsigned.apk'
with zipfile.ZipFile(unsigned,'w',compression=zipfile.ZIP_DEFLATED) as z:
 z.writestr('AndroidManifest.xml',axml)
 z.writestr('classes.dex',hookdex)
 z.writestr('classes2.dex',uidex)
 z.writestr('assets/xposed_init','com.sahanaz.mumu.vectorcleaner.HookMain\n')
# Signing configuration: local release key may be supplied via environment.
# Never commit keystores or signing passwords to GitHub.
key=Path(os.environ.get('MUMU_SIGN_KEYSTORE',str(R/'vector_signing_key.jks')))
storepass=os.environ.get('MUMU_SIGN_STOREPASS','changeit')
keypass=os.environ.get('MUMU_SIGN_KEYPASS',storepass)
alias=os.environ.get('MUMU_SIGN_ALIAS','vectorcleaner')
if not key.exists():
    if os.environ.get('MUMU_SIGN_KEYSTORE'):
        raise FileNotFoundError('MUMU_SIGN_KEYSTORE does not exist: '+str(key))
    # Local development certificate. Its signature CANNOT upgrade the official release.
    subprocess.run(['keytool','-genkeypair','-keystore',str(key),
       '-storepass',storepass,'-keypass',keypass,'-alias',alias,
       '-keyalg','RSA','-keysize','3072','-validity','3650',
       '-dname','CN=MuMu Desktop Cleaner Local Build, O=User Tools'],
       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
subprocess.run(['jarsigner','-keystore',str(key),'-storepass',storepass,
 '-keypass',keypass,'-sigalg','SHA256withRSA','-digestalg','SHA-256',
 str(unsigned),alias],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
shutil.copy2(unsigned,OUTPUT)
assert zipfile.ZipFile(OUTPUT).testzip() is None
subprocess.run(['jarsigner','-verify','-strict','-certs',str(OUTPUT)],capture_output=True,check=False)
print('OUTPUT',OUTPUT,'bytes',OUTPUT.stat().st_size)
print('SHA256',hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
print('hookdex',len(hookdex),'uidex',len(uidex),'axml',len(axml))
