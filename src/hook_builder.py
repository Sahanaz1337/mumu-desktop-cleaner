#!/usr/bin/env python3
"""Build a minimalist *legacy* LSPosed module APK offline (no Android SDK).
Target: MuMu Android 15 customized Lawnchair 15.0.0.7.
Only hook app.lawnchair k7.l onAttachedToWindow() and V(Launcher). Hide both wrapper and binding.searchRoot.
The independent store widgets must remain disabled separately; no file edits.
"""
import hashlib, os, shutil, struct, subprocess, zipfile, zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parent
APK = Path(__file__).resolve().parent / 'hook.apk'
PKG = 'com.sahanaz.mumu.vectorcleaner'
MAIN = 'Lcom/sahanaz/mumu/vectorcleaner/HookMain;'
SEARCH_HOOK = 'Lcom/sahanaz/mumu/vectorcleaner/SearchViewHook;'
METHOD_HOOK = 'Lde/robv/android/xposed/XC_MethodHook;'
HOOK_PARAM = 'Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;'
VIEW = 'Landroid/view/View;'
INTERFACE = 'Lde/robv/android/xposed/IXposedHookLoadPackage;'
PARAM = 'Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;'
REPLACEMENT = 'Lde/robv/android/xposed/XC_MethodReplacement;'
HELPERS = 'Lde/robv/android/xposed/XposedHelpers;'
BRIDGE = 'Lde/robv/android/xposed/XposedBridge;'


def sleb(n):
    out=bytearray()
    while True:
        x=n&127;n >>= 7
        done=(n==0 and (x&64)==0) or (n==-1 and (x&64)!=0)
        out.append(x if done else x|128)
        if done: return bytes(out)

def leb(n):
    b = bytearray()
    while n > 127:
        b.append((n & 127) | 128)
        n >>= 7
    b.append(n & 127)
    return bytes(b)


class DexTable:
    def __init__(self):
        self.types = set(); self.strings = set(); self.protos = set(); self.fields = set(); self.methods = set()
    def typ(self, val): self.types.add(val); self.strings.add(val)
    def proto(self, ret, params):
        self.typ(ret)
        for p in params: self.typ(p)
        self.protos.add((ret, tuple(params)))
    def met(self, owner, name, ret, params=()):
        self.typ(owner); self.strings.add(name); self.proto(ret, params)
        m = (owner,name,ret,tuple(params)); self.methods.add(m)
        return m
    def fld(self, owner, name, t):
        self.typ(owner); self.strings.add(name); self.typ(t)
        f = (owner,name,t); self.fields.add(f)
        return f
    def literal(self, val): self.strings.add(val)

D = DexTable()
for typ in (MAIN,SEARCH_HOOK,METHOD_HOOK,HOOK_PARAM,INTERFACE,PARAM,HELPERS,BRIDGE,VIEW,
            'Ljava/lang/Object;','Ljava/lang/String;','Ljava/lang/Class;',
            'Ljava/lang/ClassLoader;','Ljava/lang/Throwable;',
            '[Ljava/lang/Object;','Lde/robv/android/xposed/XC_MethodHook$Unhook;',
            'V','Z','I'):
    D.typ(typ)
obj_ctor = D.met('Ljava/lang/Object;', '<init>', 'V')
method_hook_ctor = D.met(METHOD_HOOK, '<init>', 'V')
main_ctor = D.met(MAIN, '<init>', 'V')
search_ctor = D.met(SEARCH_HOOK, '<init>', 'V')
handle = D.met(MAIN, 'handleLoadPackage', 'V', [PARAM])
after = D.met(SEARCH_HOOK,'afterHookedMethod','V',[HOOK_PARAM])
string_equals = D.met('Ljava/lang/String;', 'equals', 'Z', ['Ljava/lang/Object;'])
find_class = D.met(HELPERS,'findClassIfExists','Ljava/lang/Class;', ['Ljava/lang/String;','Ljava/lang/ClassLoader;'])
find_hook = D.met(HELPERS,'findAndHookMethod','Lde/robv/android/xposed/XC_MethodHook$Unhook;', ['Ljava/lang/Class;','Ljava/lang/String;','[Ljava/lang/Object;'])
get_object_field = D.met(HELPERS,'getObjectField','Ljava/lang/Object;',['Ljava/lang/Object;','Ljava/lang/String;'])
set_visibility = D.met(VIEW,'setVisibility','V',['I'])
get_context=D.met(VIEW,'getContext','Landroid/content/Context;')
get_resolver=D.met('Landroid/content/Context;','getContentResolver','Landroid/content/ContentResolver;')
get_global=D.met('Landroid/provider/Settings$Global;','getInt','I',['Landroid/content/ContentResolver;','Ljava/lang/String;','I'])
log = D.met(BRIDGE,'log','V',['Ljava/lang/String;'])
log_error = D.met(BRIDGE,'log','V',['Ljava/lang/Throwable;'])
package_field = D.fld(PARAM,'packageName','Ljava/lang/String;')
loader_field = D.fld(PARAM,'classLoader','Ljava/lang/ClassLoader;')
this_field = D.fld(HOOK_PARAM,'thisObject','Ljava/lang/Object;')
for lit in ('sahanaz_mumu_hide_search','app.lawnchair','k7.l','com.android.launcher3.Launcher','onAttachedToWindow','V','h','searchRoot',
   'MuMuCleanerV1: loaded for app.lawnchair',
   'MuMuCleanerV1: onAttach & V hooks installed',
   'MuMuCleanerV1: searchRoot GONE',
   'MuMuCleanerV1: k7.l not found'):
    D.literal(lit)

class Code:
    def __init__(self): self.items=[]; self.labels={}; self.fix=[]
    def label(self,s): self.labels[s]=len(self.items)
    def emit(self,*x): self.items.extend(v if isinstance(v,tuple) else v&0xffff for v in x)
    def instr(self,op,reg=0): self.emit(op|(reg<<8))
    def const4(self,r,n): self.emit(0x12|(r<<8)|((n&15)<<12))
    def const16(self,r,n): self.emit(0x13|(r<<8),n)
    def string(self,r,s): self.emit(0x1a|(r<<8),('str',s))
    def obj(self,r,t): self.emit(0x22|(r<<8),('type',t))
    def cast(self,r,t): self.emit(0x1f|(r<<8),('type',t))
    def invoke(self,op,m,regs):
        assert len(regs)<=5 and all(0<=v<=15 for v in regs)
        rr=regs+[0]*(5-len(regs))
        self.emit(op|(len(regs)<<12)|(rr[4]<<8),('met',m), rr[0]|(rr[1]<<4)|(rr[2]<<8)|(rr[3]<<12))
    def iget(self,op,a,b,f): self.emit(op|(a<<8)|(b<<12),('field',f))
    def newarr(self,a,b,t): self.emit(0x23|(a<<8)|(b<<12),('type',t))
    def aput(self,a,b,c): self.emit(0x4d|(a<<8),b|(c<<8))
    def jump(self,label):
        pos=len(self.items);self.emit(0x28);self.fix.append((pos,label,True))
    def branch(self,op,reg,label):
        assert op in (0x38,0x39)
        pos=len(self.items);self.emit(op|(reg<<8),0);self.fix.append((pos,label,False))
    def finish(self,ids):
        w=list(self.items)
        for pos,label,short in self.fix:
            off=self.labels[label]-pos
            if short:
                assert -128<=off<128
                w[pos]=0x28|((off&255)<<8)
            else:
                assert -32768<=off<=32767
                w[pos+1]=off&0xffff
        for i,v in enumerate(w):
            if isinstance(v,tuple): w[i]=ids[v[0]][v[1]]
        assert all(isinstance(v,int) for v in w)
        return struct.pack('<'+'H'*len(w),*w),self.labels

# constructors
c=Code();c.invoke(0x70,obj_ctor,[0]);c.instr(0x0e)
main_ctor_code=(c,1,1,1,None)
c=Code();c.invoke(0x70,method_hook_ctor,[0]);c.instr(0x0e)
search_ctor_code=(c,1,1,1,None)

# afterHookedMethod: hide actual k7.l wrapper first, then binding.searchRoot.
# Some MuMu builds attach the inflated searchRoot separately; hide both.
# v0 instance or View, v1 scratch; v2 this; v3 callback param
c=Code()
c.label('try_start')
c.iget(0x54,0,6,this_field)
c.cast(0,VIEW)
c.invoke(0x6e,get_context,[0]);c.instr(0x0c,0)
c.invoke(0x6e,get_resolver,[0]);c.instr(0x0c,0)
c.string(1,'sahanaz_mumu_hide_search');c.const4(2,0)
c.invoke(0x71,get_global,[0,1,2]);c.instr(0x0a,2)
c.branch(0x38,2,'done')
c.iget(0x54,0,6,this_field)
c.cast(0,VIEW)
c.const16(1,8)              # View.GONE
c.invoke(0x6e,set_visibility,[0,1])
c.string(0,'MuMuCleanerV1: wrapper GONE')
c.invoke(0x71,log,[0])
# Retrieve k7.l.h binding, then binding.searchRoot and hide again.
c.iget(0x54,0,6,this_field)
c.string(1,'h')
c.invoke(0x71,get_object_field,[0,1]);c.instr(0x0c,0)
c.string(1,'searchRoot')
c.invoke(0x71,get_object_field,[0,1]);c.instr(0x0c,0)
c.cast(0,VIEW)
c.const16(1,8)
c.invoke(0x6e,set_visibility,[0,1])
c.string(0,'MuMuCleanerV1: searchRoot GONE')
c.invoke(0x71,log,[0])
c.label('try_end');c.jump('done')
c.label('catch');c.instr(0x0d,0);c.invoke(0x71,log_error,[0])
c.label('done');c.instr(0x0e)
after_code=(c,7,2,3,('try_start','try_end','catch'))

# handleLoadPackage: hook search view attach, and refresh method V(Launcher)
# locals v0-v6, this v7, loadPackageParam v8
c=Code()
c.iget(0x54,0,8,package_field)
c.string(1,'app.lawnchair')
c.invoke(0x6e,string_equals,[1,0]);c.instr(0x0a,2)
c.branch(0x38,2,'done')
c.label('try_start')
c.string(0,'MuMuCleanerV1: loaded for app.lawnchair')
c.invoke(0x71,log,[0])
c.string(0,'k7.l')
c.iget(0x54,1,8,loader_field)
c.invoke(0x71,find_class,[0,1]);c.instr(0x0c,0)
c.branch(0x38,0,'not_found')
# hook V(Launcher) to enforce GONE after display refresh
c.string(3,'com.android.launcher3.Launcher')
c.iget(0x54,4,8,loader_field)
c.invoke(0x71,find_class,[3,4]);c.instr(0x0c,3)
c.branch(0x38,3,'doAttach')
c.string(1,'V')
c.const4(2,2);c.newarr(2,2,'[Ljava/lang/Object;')
c.const4(4,0);c.aput(3,2,4)
c.obj(5,SEARCH_HOOK);c.invoke(0x70,search_ctor,[5])
c.const4(4,1);c.aput(5,2,4)
c.invoke(0x71,find_hook,[0,1,2])
c.label('doAttach')
# hook onAttachedToWindow()
c.string(1,'onAttachedToWindow')
c.const4(2,1);c.newarr(2,2,'[Ljava/lang/Object;')
c.obj(3,SEARCH_HOOK);c.invoke(0x70,search_ctor,[3])
c.const4(4,0);c.aput(3,2,4)
c.invoke(0x71,find_hook,[0,1,2])
c.label('hooked')
c.string(0,'MuMuCleanerV1: onAttach & V hooks installed')
c.invoke(0x71,log,[0]);c.label('try_end');c.jump('done')
c.label('not_found')
c.string(0,'MuMuCleanerV1: k7.l not found')
c.invoke(0x71,log,[0]);c.jump('done')
c.label('catch');c.instr(0x0d,0);c.invoke(0x71,log_error,[0])
c.label('done');c.instr(0x0e)
handle_code=(c,9,2,3,('try_start','try_end','catch'))

for extra_log in ('MuMuCleanerV1: wrapper GONE','MuMuCleanerV1: searchRoot GONE'):
    D.literal(extra_log)

# dex metadata tables (canonical sorting)
for ret,params in list(D.protos):
    shorty=''.join(('L' if x.startswith(('L','[')) else x) for x in (ret,)+params)
    D.literal(shorty)
strings=sorted(D.strings,key=lambda x:x.encode('utf-16be')); si={v:i for i,v in enumerate(strings)}
types=sorted(D.types,key=lambda x:si[x]);ti={v:i for i,v in enumerate(types)}
protos=sorted(D.protos,key=lambda p:(ti[p[0]],tuple(ti[v] for v in p[1])));pi={v:i for i,v in enumerate(protos)}
fields=sorted(D.fields,key=lambda f:(ti[f[0]],si[f[1]],ti[f[2]]));fi={v:i for i,v in enumerate(fields)}
methods=sorted(D.methods,key=lambda m:(ti[m[0]],si[m[1]],pi[(m[2],m[3])]));mi={v:i for i,v in enumerate(methods)}
ids={'str':si,'type':ti,'field':fi,'met':mi}
assert len(types)<65536 and len(methods)<65536
sections={}; pos=112
for name,n,size in [('strings',len(strings),4),('types',len(types),4),('protos',len(protos),12),
                    ('fields',len(fields),8),('methods',len(methods),8),('classes',2,32)]:
    sections[name]=(pos,n);pos+=n*size
DATA_OFF=(pos+3)&~3
buf=bytearray(DATA_OFF);cur=DATA_OFF

def align(n):
    global cur
    new=(cur+n-1)//n*n
    if len(buf)<new: buf.extend(b'\0'*(new-len(buf)))
    cur=new

def add(b):
    global cur
    off=cur;buf.extend(b);cur+=len(b);return off

def put(off,b): buf[off:off+len(b)]=b

align(4)
interfaces=add(struct.pack('<IHH',1,ti[INTERFACE],0))
typelists=[interfaces]
params={}
for _, ps in protos:
    if ps and ps not in params:
        align(4)
        params[ps]=add(struct.pack('<I',len(ps))+b''.join(struct.pack('<H',ti[v]) for v in ps)+ (b'\0\0' if len(ps)%2 else b''))
        typelists.append(params[ps])

codeoff={};codeitems=[]
for key,(assembler,registers,ins,outs,catch) in [
    ('main_ctor',main_ctor_code),('search_ctor',search_ctor_code),
    ('after',after_code),('handle',handle_code)]:
    data,labels=assembler.finish(ids)
    align(4)
    ci=struct.pack('<HHHHII',registers,ins,outs,1 if catch else 0,0,len(data)//2)+data
    if catch:
        if len(data)//2 % 2:ci+=b'\0\0'
        start,end,handler=catch
        ci+=struct.pack('<IHH',labels[start],labels[end]-labels[start],1)
        ci+=leb(1)+sleb(0)+leb(labels[handler])
    off=add(ci)
    codeoff[key]=off;codeitems.append(off)

classdataoffs={}
for cls,ctor_id,virt_id,co,vo,virt_flags in [
  (MAIN,main_ctor,handle,'main_ctor','handle',0x1),
  (SEARCH_HOOK,search_ctor,after,'search_ctor','after',0x4)]:
    cd=leb(0)+leb(0)+leb(1)+leb(1)
    cd+=leb(mi[ctor_id])+leb(0x10001)+leb(codeoff[co])
    cd+=leb(mi[virt_id])+leb(virt_flags)+leb(codeoff[vo])
    classdataoffs[cls]=add(cd)

stringoffs=[]
for s in strings:
    stringoffs.append(add(leb(len(s.encode('utf-16-le'))//2)+s.encode('utf-8')+b'\0'))
align(4)
mapoff=cur
maptypes=[(0x0000,1,0),(0x0001,len(strings),sections['strings'][0]),
          (0x0002,len(types),sections['types'][0]),(0x0003,len(protos),sections['protos'][0]),
          (0x0004,len(fields),sections['fields'][0]),(0x0005,len(methods),sections['methods'][0]),
          (0x0006,2,sections['classes'][0]),(0x1001,len(typelists),typelists[0]),
          (0x2001,len(codeitems),codeitems[0]),(0x2000,2,min(classdataoffs.values())),
          (0x2002,len(strings),stringoffs[0]),(0x1000,1,mapoff)]
maptypes.sort(key=lambda t:t[2])
add(struct.pack('<I',len(maptypes))+b''.join(struct.pack('<HHII',typ,0,n,off) for typ,n,off in maptypes))
for i,o in enumerate(stringoffs):put(sections['strings'][0]+4*i,struct.pack('<I',o))
for i,s in enumerate(types):put(sections['types'][0]+4*i,struct.pack('<I',si[s]))
for i,(ret,par) in enumerate(protos):
    shorty=''.join(('L' if x.startswith(('L','[')) else x) for x in (ret,)+par)
    put(sections['protos'][0]+12*i,struct.pack('<III',si[shorty],ti[ret],params.get(par,0)))
for i,(owner,name,t) in enumerate(fields):put(sections['fields'][0]+8*i,struct.pack('<HHI',ti[owner],ti[t],si[name]))
for i,(owner,name,ret,par) in enumerate(methods):put(sections['methods'][0]+8*i,struct.pack('<HHI',ti[owner],pi[(ret,par)],si[name]))
for j,cls in enumerate(sorted([MAIN,SEARCH_HOOK],key=lambda x:ti[x])):
    sup='Ljava/lang/Object;' if cls==MAIN else METHOD_HOOK
    itf=interfaces if cls==MAIN else 0
    put(sections['classes'][0]+32*j,struct.pack('<IIIIIIII',ti[cls],0x1,ti[sup],itf,
                                       0xffffffff,0,classdataoffs[cls],0))
file_size=len(buf)
hdr=struct.pack('<8sI20s20I',b'dex\n035\0',0,b'\0'*20,file_size,112,0x12345678,0,0,mapoff,
    len(strings),sections['strings'][0],len(types),sections['types'][0],
    len(protos),sections['protos'][0],len(fields),sections['fields'][0],
    len(methods),sections['methods'][0],2,sections['classes'][0],file_size-DATA_OFF,DATA_OFF)
assert len(hdr)==112
put(0,hdr);put(12,hashlib.sha1(buf[32:]).digest());put(8,struct.pack('<I',zlib.adler32(buf[12:]) & 0xffffffff))
dex=bytes(buf)

# Minimal compiled AXML manifest with legacy Xposed metadata, no launcher activity.
ANDROID='http://schemas.android.com/apk/res/android'
NS='android'
ATTR_IDS={'name':0x01010003,'label':0x01010001,'value':0x01010024,'minSdkVersion':0x0101020c,
          'targetSdkVersion':0x01010270,'versionCode':0x0101021b,'versionName':0x0101021c}
ss=['manifest','uses-sdk','application','meta-data','package','android',ANDROID,'name','value',
    'label','versionCode','versionName','minSdkVersion','targetSdkVersion',PKG,
    'MuMu 桌面净化 - Vector','1.0','xposedmodule','xposeddescription','xposedminversion',
    'xposedscope','适配 Vector 2.2：隐藏 MuMu Lawnchair 搜索栏（仅 app.lawnchair）',
    'app.lawnchair']
ss=list(dict.fromkeys(ss));sx={v:i for i,v in enumerate(ss)}

def length(n):
    if n<=127:return bytes([n])
    return bytes([(n>>8)|128,n&0xff])

def chunk(typ,hs,head,body):
    assert len(head)==hs-8
    return struct.pack('<HHI',typ,hs,hs+len(body))+head+body

def pool(vals):
    data=bytearray();offs=[]
    for s in vals:
        offs.append(len(data))
        b=s.encode('utf8');data+=length(len(s.encode('utf-16le'))//2)+length(len(b))+b+b'\0'
    while len(data)%4:data.append(0)
    head=struct.pack('<IIIII',len(vals),0,0x100,28+4*len(vals),0)
    return chunk(1,28,head,b''.join(struct.pack('<I',x) for x in offs)+data)

def attr(name,val,typ='str'):
    namespace=sx[ANDROID] if name in ATTR_IDS else 0xffffffff
    if typ=='str':t=3;idx=sx[val];raw=idx
    elif typ=='int':t=0x10;idx=int(val);raw=0xffffffff
    elif typ=='bool':t=0x12;idx=int(val);raw=0xffffffff
    else:raise ValueError(typ)
    return struct.pack('<IIIHBBI',namespace,sx[name],raw,8,0,t,idx)

def node(kind,name='',attrs=()):
    header=struct.pack('<II',0,0xffffffff)
    if kind=='ns+':return chunk(0x100,16,header,struct.pack('<II',sx[NS],sx[ANDROID]))
    if kind=='ns-':return chunk(0x101,16,header,struct.pack('<II',sx[NS],sx[ANDROID]))
    if kind=='open':
        bs=b''.join(attr(*x) for x in attrs)
        return chunk(0x102,16,header,struct.pack('<IIHHHHHH',0xffffffff,sx[name],20,20,len(attrs),0,0,0)+bs)
    if kind=='close':return chunk(0x103,16,header,struct.pack('<II',0xffffffff,sx[name]))
    raise ValueError(kind)

nodes=[node('ns+'),
    node('open','manifest',[('package',PKG),('versionCode',1,'int'),('versionName','1.0')]),
    node('open','uses-sdk',[('minSdkVersion',29,'int'),('targetSdkVersion',29,'int')]),node('close','uses-sdk'),
    node('open','application',[('label','MuMu 桌面净化 - Vector')]),
    node('open','meta-data',[('name','xposedmodule'),('value',1,'bool')]),node('close','meta-data'),
    node('open','meta-data',[('name','xposeddescription'),('value','适配 Vector 2.2：隐藏 MuMu Lawnchair 搜索栏（仅 app.lawnchair）')]),node('close','meta-data'),
    node('open','meta-data',[('name','xposedminversion'),('value',93,'int')]),node('close','meta-data'),
    node('open','meta-data',[('name','xposedscope'),('value','app.lawnchair')]),node('close','meta-data'),
    node('close','application'),node('close','manifest'),node('ns-')]
resource_map=chunk(0x180,8,b'',b''.join(struct.pack('<I',ATTR_IDS.get(s,0)) for s in ss))
axml=chunk(3,8,b'',pool(ss)+resource_map+b''.join(nodes))

unsigned=ROOT/'vector_unsigned.apk'
with zipfile.ZipFile(unsigned,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('AndroidManifest.xml',axml)
    z.writestr('classes.dex',dex)
    z.writestr('assets/xposed_init','com.sahanaz.mumu.vectorcleaner.HookMain\n')
key=ROOT/'vector_signing_key.jks'
if not key.exists():
    subprocess.run(['keytool','-genkeypair','-keystore',str(key),'-storepass','changeit',
      '-keypass','changeit','-alias','vectorcleaner','-keyalg','RSA','-keysize','3072',
      '-validity','3650','-dname','CN=MuMu Desktop Cleaner Local Test, O=User Tools'],
      check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['jarsigner','-keystore',str(key),'-storepass','changeit',
  '-keypass','changeit','-sigalg','SHA256withRSA','-digestalg','SHA-256',
  str(unsigned),'vectorcleaner'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
shutil.copy2(unsigned,APK)
print('Built',APK,'bytes',APK.stat().st_size)
print('DEX',len(dex),'AXML',len(axml),'types',len(types),'methods',len(methods))
print('SHA256',hashlib.sha256(APK.read_bytes()).hexdigest())
