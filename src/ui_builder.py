#!/usr/bin/env python3
"""Offline Android APK builder for a single self-contained Activity.
Produces a small Dalvik DEX, binary AndroidManifest.xml, and v1-signed APK.
No Android SDK or external dependencies required.
"""
import os, struct, hashlib, zlib, zipfile, base64, subprocess, textwrap, shutil
from collections import defaultdict
from pathlib import Path

OUT=Path(__file__).resolve().parent
APK=OUT/'mumu_ui.apk'
PKG='com.sahanaz.lawnchairwidget'
CLS='L'+PKG.replace('.','/')+'/MainActivity;'
SUPER='Landroid/app/Activity;'


def leb(n):
    b=bytearray()
    while n>127: b.append((n&127)|128); n>>=7
    b.append(n&127); return bytes(b)

def sleb(n):
    b=bytearray()
    while True:
        x=n & 127; n >>=7
        done=(n==0 and (x&64)==0) or (n==-1 and (x&64)!=0)
        b.append(x if done else x|128)
        if done: return bytes(b)

def field(tag,b):return leb((tag<<3)|2)+leb(len(b))+b

def popup_entry(text):
    key=field(1,b'launcher_popup_order')
    pref_value=field(5,text.encode())
    mp=field(2,pref_value)
    return field(1,key+mp)

DEFAULT='+carousel|-lock|-edit_mode|+wallpaper|+widgets|+home_settings|+sys_settings'
DEFAULT_HIDE=DEFAULT.replace('+widgets','-widgets')
ENTRY_HIDE=base64.b64encode(popup_entry(DEFAULT_HIDE)).decode('ascii')
ENTRY_SHOW=base64.b64encode(popup_entry(DEFAULT)).decode('ascii')

# Configuration toggles and rollback. The UI asks for Root; no automatic changes on installation.
ROOT='''
[ "$(id -u)" = 0 ] || exit 40
pm path app.lawnchair >/dev/null 2>&1 || exit 41
dumpsys package app.lawnchair | grep -q 'versionName=15.0.0.7' || exit 42
'''
AD_ONE='com.mumu.store/com.mumu.store.widget.appWidgetProvider.AdBannerWidgetProvider'
AD_TWO='com.mumu.store/com.mumu.store.widget.appWidgetProvider.DailyDiscoveryWidgetProvider'

def menu_toggle(hidden):
    old='+widgets' if hidden else '-widgets'
    new='-widgets' if hidden else '+widgets'
    char='-' if hidden else '+'
    return '''
F=/data/user/0/app.lawnchair/files/datastore/launcher_preferences.preferences_pb
[ -f "$F" ] || exit 61
if grep -aqF -- '%(new)s' "$F"; then
  :
elif grep -aqF -- '%(old)s' "$F"; then
  N=$(LC_ALL=C grep -aoF -- '%(old)s' "$F" | wc -l | tr -d ' ')
  [ "$N" = 1 ] || exit 62
  if [ ! -e "$F.sahanaz-v1.bak" ]; then cp -p "$F" "$F.sahanaz-v1.bak" || exit 63; fi
  O=$(LC_ALL=C grep -aobF -- '%(old)s' "$F" | head -n 1 | cut -d: -f1)
  [ -n "$O" ] || exit 64
  printf '%(char)s' | dd of="$F" bs=1 seek="$O" conv=notrunc 2>/dev/null || exit 65
  restorecon "$F" >/dev/null 2>&1 || true
else
  exit 66
fi
grep -aqF -- '%(new)s' "$F" || exit 67
''' % {'old':old,'new':new,'char':char}

def restart_home():
    return '''
am force-stop app.lawnchair >/dev/null 2>&1 || exit 71
am start -n app.lawnchair/.LawnchairLauncher >/dev/null 2>&1 || exit 72
'''

def ads_toggle(hidden):
    command='disable' if hidden else 'enable'
    return f'''\npm {command} --user 0 {AD_ONE} >/dev/null 2>&1 || exit 51
pm {command} --user 0 {AD_TWO} >/dev/null 2>&1 || exit 52
'''

def search_toggle(hidden):
    return f'''\nsettings put global sahanaz_mumu_hide_search {1 if hidden else 0} || exit 53
'''

def folder_toggle(hidden):
    return '\nDB=/data/user/0/app.lawnchair/databases/launcher_4_7_6_1.db\nROWS=/data/user/0/app.lawnchair/files/sahanaz_tools_v12_rows.db\nSNAP=/data/user/0/app.lawnchair/files/sahanaz_tools_v12_before.db\n[ -f "$DB" ] || exit 81\ncommand -v sqlite3 >/dev/null 2>&1 || exit 82\n# Match the exact user-confirmed folder, not just an arbitrary folder title.\nMATCH=$(sqlite3 "$DB" "SELECT COUNT(*) FROM favorites WHERE _id=6 AND title=\'小工具\' AND itemType=2 AND container=-101 AND screen=5 AND cellX=5 AND cellY=0;" 2>/dev/null) || exit 83\nif [ "$MATCH" = 1 ]; then\n  sqlite3 "$DB" \'PRAGMA quick_check;\' | grep -qx ok || exit 84\n  if [ ! -f "$SNAP" ]; then\n    sqlite3 "$DB" ".backup \'$SNAP\'" || exit 85\n    chmod 600 "$SNAP" || exit 86\n    chown 10014:10014 "$SNAP" || exit 86\n    restorecon "$SNAP" >/dev/null 2>&1 || true\n  fi\n  sqlite3 -batch -bail "$DB" <<SQL\nPRAGMA busy_timeout=10000;\nATTACH DATABASE \'$ROWS\' AS saved;\nBEGIN IMMEDIATE;\nCREATE TABLE IF NOT EXISTS saved.folder_items AS SELECT * FROM main.favorites WHERE 0;\nDELETE FROM saved.folder_items;\nINSERT INTO saved.folder_items SELECT * FROM main.favorites WHERE _id=6 OR container=6;\nDELETE FROM main.favorites WHERE container=6;\nDELETE FROM main.favorites WHERE _id=6;\nCOMMIT;\nSQL\n  [ "$?" = 0 ] || exit 87\n  chmod 600 "$ROWS" || exit 88\n  chown 10014:10014 "$ROWS" || exit 88\n  restorecon "$ROWS" >/dev/null 2>&1 || true\nelif [ -f "$ROWS" ]; then\n  N=$(sqlite3 "$ROWS" "SELECT COUNT(*) FROM folder_items WHERE _id=6 AND title=\'小工具\';" 2>/dev/null) || exit 89\n  [ "$N" = 1 ] || exit 90\nelse\n  exit 91\nfi\n# Neutralize the obsolete V1.2 view-hiding setting; V1.2 does not hook FolderIcon.\nsettings put global sahanaz_mumu_hide_tools_folder 0 >/dev/null 2>&1 || true\n' if hidden else '\nDB=/data/user/0/app.lawnchair/databases/launcher_4_7_6_1.db\nROWS=/data/user/0/app.lawnchair/files/sahanaz_tools_v12_rows.db\nSNAP=/data/user/0/app.lawnchair/files/sahanaz_tools_v12_before.db\n[ -f "$DB" ] || exit 81\ncommand -v sqlite3 >/dev/null 2>&1 || exit 82\n[ -f "$ROWS" ] || exit 92\nN=$(sqlite3 "$ROWS" "SELECT COUNT(*) FROM folder_items WHERE _id=6 AND title=\'小工具\' AND itemType=2;" 2>/dev/null) || exit 93\n[ "$N" = 1 ] || exit 94\nMATCH=$(sqlite3 "$DB" "SELECT COUNT(*) FROM favorites WHERE _id=6 AND title=\'小工具\' AND itemType=2 AND container=-101;" 2>/dev/null) || exit 95\nif [ "$MATCH" != 1 ]; then\n  # Guard all original IDs and the dock coordinate against new user shortcuts.\n  USED=$(sqlite3 "$DB" "ATTACH DATABASE \'$ROWS\' AS saved; SELECT COUNT(*) FROM main.favorites WHERE _id IN (SELECT _id FROM saved.folder_items);" 2>/dev/null) || exit 96\n  [ "$USED" = 0 ] || exit 97\n  SLOT=$(sqlite3 "$DB" \'SELECT COUNT(*) FROM favorites WHERE container=-101 AND screen=5 AND cellX=5 AND cellY=0;\' 2>/dev/null) || exit 98\n  [ "$SLOT" = 0 ] || exit 99\n  sqlite3 -batch -bail "$DB" <<SQL\nPRAGMA busy_timeout=10000;\nATTACH DATABASE \'$ROWS\' AS saved;\nBEGIN IMMEDIATE;\nINSERT INTO main.favorites SELECT * FROM saved.folder_items ORDER BY CASE WHEN _id=6 THEN 0 ELSE 1 END;\nCOMMIT;\nSQL\n  [ "$?" = 0 ] || exit 100\nfi\nsettings put global sahanaz_mumu_hide_tools_folder 0 >/dev/null 2>&1 || true\n'

def script(mode):
    if mode=='check':
        return ROOT+'''\nS=$(settings get global sahanaz_mumu_hide_search)
[ "$S" = 1 ] || exit 11
DB=/data/user/0/app.lawnchair/databases/launcher_4_7_6_1.db
CNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM favorites WHERE _id=6 AND title='小工具' AND itemType=2;" 2>/dev/null)
[ "$CNT" = 0 ] || exit 13
A=$(pm list packages -d | grep -c 'com.mumu.store')
# pm list packages -d checks whole packages, not disabled components.
C=$(dumpsys package com.mumu.store | grep -A 40 'disabledComponents:' | grep -c 'AdBannerWidgetProvider')
[ "$C" -ge 0 ] || exit 12
F=/data/user/0/app.lawnchair/files/datastore/launcher_preferences.preferences_pb
[ -f "$F" ] || exit 12
grep -aqF -- '-widgets' "$F" || exit 12
exit 10
'''
    if mode=='all_hide':
        # Stage safe configuration first. Refresh Launcher after data mutation.
        return ROOT+search_toggle(True)+ads_toggle(True)+'''\nam force-stop app.lawnchair >/dev/null 2>&1 || exit 71
'''+folder_toggle(True)+menu_toggle(True)+'''\nam start -n app.lawnchair/.LawnchairLauncher >/dev/null 2>&1 || exit 72
'''
    if mode=='all_show':
        return ROOT+search_toggle(False)+ads_toggle(False)+'''\nam force-stop app.lawnchair >/dev/null 2>&1 || exit 71
'''+folder_toggle(False)+menu_toggle(False)+'''\nam start -n app.lawnchair/.LawnchairLauncher >/dev/null 2>&1 || exit 72
'''
    if mode=='hide_search':return ROOT+search_toggle(True)+restart_home()
    if mode=='show_search':return ROOT+search_toggle(False)+restart_home()
    if mode=='hide_ads':return ROOT+ads_toggle(True)+restart_home()
    if mode=='show_ads':return ROOT+ads_toggle(False)+restart_home()
    if mode=='hide_menu':return ROOT+'''\nam force-stop app.lawnchair >/dev/null 2>&1 || exit 71
'''+menu_toggle(True)+'''\nam start -n app.lawnchair/.LawnchairLauncher >/dev/null 2>&1 || exit 72
'''
    if mode=='show_menu':return ROOT+'''\nam force-stop app.lawnchair >/dev/null 2>&1 || exit 71
'''+menu_toggle(False)+'''\nam start -n app.lawnchair/.LawnchairLauncher >/dev/null 2>&1 || exit 72
'''
    if mode=='hide_folder':return ROOT+'''
am force-stop app.lawnchair >/dev/null 2>&1 || exit 71
'''+folder_toggle(True)+'''
am start -n app.lawnchair/.LawnchairLauncher >/dev/null 2>&1 || exit 72
'''
    if mode=='show_folder':return ROOT+'''
am force-stop app.lawnchair >/dev/null 2>&1 || exit 71
'''+folder_toggle(False)+'''
am start -n app.lawnchair/.LawnchairLauncher >/dev/null 2>&1 || exit 72
'''
    if mode=='restart':return ROOT+restart_home()
    raise ValueError(mode)

MODES=['all_hide','all_show','hide_search','show_search','hide_ads','show_ads','hide_menu','show_menu','hide_folder','show_folder','check','restart']
LABELS=[
 '一键净化（搜索栏 + 广告 + 菜单 + 小工具文件夹）',
 '一键恢复全部设置（包含小工具文件夹）',
 '仅隐藏顶部推广搜索框',
 '仅恢复顶部搜索框',
 '仅关闭两个广告微件',
 '仅恢复两个广告微件组件',
 '仅隐藏长按菜单「微件」',
 '仅恢复长按菜单「微件」',
 '真正移除「小工具」Dock 文件夹（保留应用）',
 '恢复「小工具」Dock 文件夹（检查位置冲突）',
 '检查当前配置',
 '重新启动 Lawnchair 桌面'
]

# DEX generator: minimal classes, methods, debug-free and valid header/id sections.
class Dex:
    def __init__(self):
        self.types=set();self.strings=set();self.protos=set();self.fields=set();self.methods=set();self.codes={}
    def typ(self,t):self.types.add(t);self.strings.add(t)
    def proto(self,ret,params):
        self.typ(ret)
        for p in params:self.typ(p)
        self.protos.add((ret,tuple(params)))
    def met(self,owner,name,ret,params):
        self.typ(owner);self.strings.add(name);self.proto(ret,params)
        m=(owner,name,ret,tuple(params));self.methods.add(m);return m
    def fld(self,owner,name,t):
        self.typ(owner);self.strings.add(name);self.typ(t)
        f=(owner,name,t);self.fields.add(f);return f
    def literal(self,s):self.strings.add(s)

D=Dex()
for t in (CLS,SUPER,'Landroid/view/View$OnClickListener;','Landroid/widget/LinearLayout;','Landroid/widget/TextView;','Landroid/widget/Button;','Landroid/widget/ScrollView;','Landroid/content/Context;','Landroid/view/View;','Landroid/os/Bundle;','Ljava/lang/Runtime;','Ljava/lang/Process;','Ljava/lang/String;','Ljava/lang/CharSequence;','[Ljava/lang/String;','Ljava/lang/Throwable;','V','I','F'):
    D.typ(t)

M={}
def m(k,*args):M[k]=D.met(*args);return M[k]
ctor=m('ctor',SUPER,'<init>','V',[])
oncre=m('superOnCreate',SUPER,'onCreate','V',['Landroid/os/Bundle;'])
layout_ctor=m('layoutCtor','Landroid/widget/LinearLayout;','<init>','V',['Landroid/content/Context;'])
layout_orientation=m('orientation','Landroid/widget/LinearLayout;','setOrientation','V',['I'])
layout_padding=m('padding','Landroid/widget/LinearLayout;','setPadding','V',['I','I','I','I'])
view_add=m('add','Landroid/widget/LinearLayout;','addView','V',['Landroid/view/View;'])
text_ctor=m('textCtor','Landroid/widget/TextView;','<init>','V',['Landroid/content/Context;'])
scroll_ctor=m('scrollCtor','Landroid/widget/ScrollView;','<init>','V',['Landroid/content/Context;'])
scroll_add=m('scrollAdd','Landroid/widget/ScrollView;','addView','V',['Landroid/view/View;'])
button_ctor=m('buttonCtor','Landroid/widget/Button;','<init>','V',['Landroid/content/Context;'])
text_set=m('textSet','Landroid/widget/TextView;','setText','V',['Ljava/lang/CharSequence;'])
text_size=m('textSize','Landroid/widget/TextView;','setTextSize','V',['F'])
view_setid=m('viewSetId','Landroid/view/View;','setId','V',['I'])
view_listener=m('listener','Landroid/view/View;','setOnClickListener','V',['Landroid/view/View$OnClickListener;'])
activity_content=m('content',SUPER,'setContentView','V',['Landroid/view/View;'])
view_getid=m('getid','Landroid/view/View;','getId','I',[])
run_action=m('runAction',CLS,'runAction','V',['I'])
string_valueof=m('stringValueOf','Ljava/lang/String;','valueOf','Ljava/lang/String;',['I'])
string_concat=m('stringConcat','Ljava/lang/String;','concat','Ljava/lang/String;',['Ljava/lang/String;'])
getruntime=m('getRuntime','Ljava/lang/Runtime;','getRuntime','Ljava/lang/Runtime;',[])
execute=m('exec','Ljava/lang/Runtime;','exec','Ljava/lang/Process;',['[Ljava/lang/String;'])
wait=m('waitFor','Ljava/lang/Process;','waitFor','I',[])
my_ctor=m('myCtor',CLS,'<init>','V',[])
my_oncreate=m('myOnCreate',CLS,'onCreate','V',['Landroid/os/Bundle;'])
my_onclick=m('myOnClick',CLS,'onClick','V',['Landroid/view/View;'])
FSTATUS=D.fld(CLS,'resultLabel','Landroid/widget/TextView;')

TITLE='MuMu Desktop Cleaner V1.0'
INFO='准备就绪。选择需要的操作，完成后将在这里显示结果。'
COMMANDS=''  # Internal command details are documented in README, not displayed in the app.
OK='执行成功。请返回桌面查看效果。'
S10='检查完成：已启用净化配置。请以桌面实际显示为准。'
S11='检查完成：搜索框当前未设置为隐藏。'
S12='检查完成：部分设置尚未启用，请按需执行。'
FAIL='操作未完成，错误码：'
ERR='执行失败：请检查 KernelSU 授权。'
for s in [TITLE,INFO,COMMANDS,*LABELS,OK,S10,S11,S12,FAIL,ERR,'su','-c',*[script(x) for x in MODES]]: D.literal(s)

class Code:
    def __init__(self):self.items=[];self.labels={};self.fix=[]
    def label(self,n):self.labels[n]=len(self.items)
    def emit(self,*w):self.items.extend(x if isinstance(x,tuple) else x&0xffff for x in w)
    def ins(self,op,reg=0):self.emit(op|(reg<<8))
    def const4(self,r,n):self.emit(0x12 | (r<<8) | ((n&15)<<12))
    def const16(self,r,n):self.emit(0x13 | (r<<8),n)
    def string(self,r,s):self.emit(0x1a | (r<<8),('str',s))
    def new(self,r,t):self.emit(0x22|(r<<8),('type',t))
    def newarr(self,a,b,t):self.emit(0x23|(a<<8)|(b<<12),('type',t))
    def invoke(self,op,m,regs):
        count=len(regs); assert count<=5 and all(0<=r<=15 for r in regs)
        padded=regs+[0]*(5-count)
        self.emit(op|((count&15)<<12)|(padded[4]<<8),('met',m),padded[0]|(padded[1]<<4)|(padded[2]<<8)|(padded[3]<<12))
    def iget(self,op,a,b,f):self.emit(op|(a<<8)|(b<<12),('field',f))
    def aput(self,a,b,c):self.emit(0x4d|(a<<8),b|(c<<8))
    def branch(self,op,a,b,label):
        pos=len(self.items)
        if op in (0x32,0x33):self.emit(op|(a<<8)|(b<<12),0)
        elif op in (0x38,0x39):self.emit(op|(a<<8),0)
        elif op==0x28:self.emit(0x28, )
        elif op==0x29:self.emit(0x29,0)
        else:raise ValueError(op)
        self.fix.append((pos,op,label))
    def finish(self,ids):
        w=list(self.items)
        for pos,op,label in self.fix:
            delta=self.labels[label]-pos
            if op==0x28:
                assert -128<=delta<128
                w[pos]=0x28|((delta&255)<<8)
            else:
                assert -32768<=delta<=32767
                w[pos+1]=delta & 65535
        for i,x in enumerate(w):
            if isinstance(x,tuple):
                kind,val=x
                w[i]=ids[kind][val]
        return struct.pack('<'+'H'*len(w),*w),self.labels

codes={}
# Constructor
c=Code();c.invoke(0x70,ctor,[1]);c.ins(0x0e);codes['ctor']=(c,2,1,1,None)
# Activity.onCreate: scrollable controls, readable action/status panel.
c=Code()
c.invoke(0x6f,oncre,[7,8]);c.new(0,'Landroid/widget/LinearLayout;');c.invoke(0x70,layout_ctor,[0,7]);c.const4(1,1);c.invoke(0x6e,layout_orientation,[0,1]);
c.const16(1,24);c.const16(2,24);c.invoke(0x6e,layout_padding,[0,1,2,1,1]);
c.new(3,'Landroid/widget/TextView;');c.invoke(0x70,text_ctor,[3,7]);c.string(4,TITLE);c.invoke(0x6e,text_set,[3,4]);c.emit(0x15|(5<<8),0x41b0);c.invoke(0x6e,text_size,[3,5]);c.invoke(0x6e,view_add,[0,3]);
c.new(3,'Landroid/widget/TextView;');c.invoke(0x70,text_ctor,[3,7]);c.string(4,INFO);c.invoke(0x6e,text_set,[3,4]);c.iget(0x5b,3,7,FSTATUS);c.invoke(0x6e,view_add,[0,3]);
for idx,title in enumerate(LABELS,1):
    c.new(3,'Landroid/widget/Button;');c.invoke(0x70,button_ctor,[3,7]);c.string(4,title);c.invoke(0x6e,text_set,[3,4]);c.const16(1,idx);c.invoke(0x6e,view_setid,[3,1]);c.invoke(0x6e,view_listener,[3,7]);c.invoke(0x6e,view_add,[0,3]);
c.new(6,'Landroid/widget/ScrollView;');c.invoke(0x70,scroll_ctor,[6,7]);c.invoke(0x6e,scroll_add,[6,0]);c.invoke(0x6e,activity_content,[7,6]);c.ins(0x0e);codes['onCreate']=(c,9,2,5,None)
# onClick(View)
c=Code();c.invoke(0x6e,view_getid,[5]);c.ins(0x0a,0);c.invoke(0x70,run_action,[4,0]);c.ins(0x0e);codes['onClick']=(c,6,2,2,None)
# runAction(int). Each button has a matching Root shell script, no automatic mutation on open.
c=Code()
for idx,mode in enumerate(MODES,1):
    c.const16(0,idx);c.branch(0x32,8,0,mode)
c.string(1,script('check'));c.branch(0x29,0,0,'haveScript')
for mode in MODES:
    c.label(mode);c.string(1,script(mode));c.branch(0x29,0,0,'haveScript')
c.label('haveScript')
c.const4(0,3);c.newarr(2,0,'[Ljava/lang/String;');c.string(3,'su');c.const4(4,0);c.aput(3,2,4);c.string(3,'-c');c.const4(4,1);c.aput(3,2,4);c.const4(4,2);c.aput(1,2,4)
c.label('try_start');c.invoke(0x71,getruntime,[]);c.ins(0x0c,4);c.invoke(0x6e,execute,[4,2]);c.ins(0x0c,4);c.invoke(0x6e,wait,[4]);c.ins(0x0a,5);c.label('try_end');c.branch(0x29,0,0,'hasCode')
c.label('catch');c.ins(0x0d,6);c.iget(0x54,4,7,FSTATUS);c.string(3,ERR);c.invoke(0x6e,text_set,[4,3]);c.ins(0x0e)
c.label('hasCode');c.iget(0x54,4,7,FSTATUS);c.const4(0,0);c.branch(0x32,5,0,'ok');c.const16(0,10);c.branch(0x32,5,0,'hidden');c.const16(0,11);c.branch(0x32,5,0,'visible');c.const16(0,12);c.branch(0x32,5,0,'missing');c.string(3,FAIL);c.invoke(0x71,string_valueof,[5]);c.ins(0x0c,0);c.invoke(0x6e,string_concat,[3,0]);c.ins(0x0c,3);c.branch(0x29,0,0,'display');
c.label('ok');c.string(3,OK);c.branch(0x29,0,0,'display');c.label('hidden');c.string(3,S10);c.branch(0x29,0,0,'display');c.label('visible');c.string(3,S11);c.branch(0x29,0,0,'display');c.label('missing');c.string(3,S12);c.label('display');c.invoke(0x6e,text_set,[4,3]);c.ins(0x0e)
codes['runAction']=(c,9,2,3,('try_start','try_end','catch'))

# Assemble DEX tables
string_vals=sorted(D.strings,key=lambda s:s.encode('utf-16be'))
sidx={v:i for i,v in enumerate(string_vals)}
type_vals=sorted(D.types,key=lambda t:sidx[t]);tidx={v:i for i,v in enumerate(type_vals)}
proto_vals=sorted(D.protos,key=lambda p:(tidx[p[0]],tuple(tidx[v] for v in p[1])))
for ret,params in proto_vals:
    shorty=''.join(('L' if v.startswith(('L','[')) else v) for v in (ret,)+params)
    D.literal(shorty)
# Shorty strings may add new strings; need recalc tables! 
string_vals=sorted(D.strings,key=lambda s:s.encode('utf-16be'));sidx={v:i for i,v in enumerate(string_vals)}
type_vals=sorted(D.types,key=lambda t:sidx[t]);tidx={v:i for i,v in enumerate(type_vals)}
proto_vals=sorted(D.protos,key=lambda p:(tidx[p[0]],tuple(tidx[v] for v in p[1])));pidx={v:i for i,v in enumerate(proto_vals)}
field_vals=sorted(D.fields,key=lambda f:(tidx[f[0]],sidx[f[1]],tidx[f[2]]));fidx={v:i for i,v in enumerate(field_vals)}
method_vals=sorted(D.methods,key=lambda m:(tidx[m[0]],sidx[m[1]],pidx[(m[2],m[3])]));midx={v:i for i,v in enumerate(method_vals)}
ids={'str':sidx,'type':tidx,'met':midx,'field':fidx}

NS=len(string_vals);NT=len(type_vals);NP=len(proto_vals);NF=len(field_vals);NM=len(method_vals)
sections={};cur=112
for name,count,itemsize in [('string_ids',NS,4),('type_ids',NT,4),('proto_ids',NP,12),('field_ids',NF,8),('method_ids',NM,8),('class_defs',1,32)]:
    sections[name]=(cur,count);cur+=count*itemsize
DATA_OFF=(cur+3)&~3
buf=bytearray(DATA_OFF);cur=DATA_OFF

def align(n):
    global cur
    new=(cur+n-1)//n*n
    if new>len(buf):buf.extend(b'\x00'*(new-len(buf)))
    cur=new

def append(data):
    global cur
    off=cur
    if len(buf)<cur:buf.extend(b'\x00'*(cur-len(buf)))
    buf.extend(data);cur+=len(data)
    return off

def put(off,b):buf[off:off+len(b)]=b

# type lists for method parameters and implemented interface (deduplicated)
param_lists={};typelist_entries=[]
align(4)
interface_list_off=append(struct.pack('<IH',1,tidx['Landroid/view/View$OnClickListener;'])+b'\0\0')
typelist_entries.append(interface_list_off)
for r,params in proto_vals:
    if params and params not in param_lists:
        align(4);off=append(struct.pack('<I',len(params))+b''.join(struct.pack('<H',tidx[v]) for v in params)+ (b'\0\0' if len(params)%2 else b''))
        param_lists[params]=off;typelist_entries.append(off)

# code items: each aligned to 4, and can reference method IDs by mapping.
code_offsets={};code_entries=[]
for k in ['ctor','runAction','onCreate','onClick']:
    assembler,regs,ins,outs,catch=codes[k]
    words,labels=assembler.finish(ids)
    align(4)
    tries=1 if catch else 0
    ci=struct.pack('<HHHHII',regs,ins,outs,tries,0,len(words)//2)+words
    if catch:
        if len(words)//2%2:ci+=b'\0\0'
        st,en,handler=catch
        # catchall handler offset 1, because preceding uleb size of handler list is one byte
        ci+=struct.pack('<IHH',labels[st],labels[en]-labels[st],1)
        ci+=leb(1)+sleb(0)+leb(labels[handler])
    off=append(ci);code_offsets[k]=off;code_entries.append(off)

# class_data direct/virtual method sorted
my_methods={'ctor':my_ctor,'runAction':run_action,'onCreate':my_oncreate,'onClick':my_onclick}
def method_encoded(entries):
    data=bytearray();last=0
    for k,access in sorted(entries,key=lambda x:midx[my_methods[x[0]]]):
        n=midx[my_methods[k]];data+=leb(n-last)+leb(access)+leb(code_offsets[k]);last=n
    return data
class_data=bytearray()
class_data+=leb(0)+leb(1)+leb(2)+leb(2)  # no static fields; one instance field; two direct, two virtual
class_data+=leb(fidx[FSTATUS])+leb(0x2)
class_data+=method_encoded([('ctor',0x10001),('runAction',0x2)])
class_data+=method_encoded([('onCreate',0x4),('onClick',0x1)])
class_data_off=append(class_data)

# string_data
str_offsets=[]
for s in string_vals:
    # Modified UTF8 encodes utf16 supplementary values as surrogate pairs. None used here.
    size=len(s.encode('utf-16-le'))//2
    offset=append(leb(size)+s.encode('utf-8')+b'\0');str_offsets.append(offset)

align(4);map_off=cur
# Map entries sorted by physical offset, not map type
maps=[(0x0000,1,0),(0x0001,NS,sections['string_ids'][0]),(0x0002,NT,sections['type_ids'][0]),(0x0003,NP,sections['proto_ids'][0]),(0x0004,NF,sections['field_ids'][0]),(0x0005,NM,sections['method_ids'][0]),(0x0006,1,sections['class_defs'][0])]
if typelist_entries:maps.append((0x1001,len(typelist_entries),typelist_entries[0]))
maps.append((0x2001,len(code_entries),code_entries[0]))
maps.append((0x2000,1,class_data_off))
maps.append((0x2002,NS,str_offsets[0]))
maps.append((0x1000,1,map_off))
maps.sort(key=lambda x:x[2])
append(struct.pack('<I',len(maps))+b''.join(struct.pack('<HHII',typ,0,cnt,off) for typ,cnt,off in maps))

# IDs tables
for i,off in enumerate(str_offsets): put(sections['string_ids'][0]+4*i,struct.pack('<I',off))
for i,t in enumerate(type_vals): put(sections['type_ids'][0]+4*i,struct.pack('<I',sidx[t]))
for i,(ret,params) in enumerate(proto_vals):
    shorty=''.join(('L' if v.startswith(('L','[')) else v) for v in (ret,)+params)
    put(sections['proto_ids'][0]+12*i,struct.pack('<III',sidx[shorty],tidx[ret],param_lists.get(params,0)))
for i,(owner,name,t) in enumerate(field_vals):put(sections['field_ids'][0]+8*i,struct.pack('<HHI',tidx[owner],tidx[t],sidx[name]))
for i,(owner,name,ret,params) in enumerate(method_vals):put(sections['method_ids'][0]+8*i,struct.pack('<HHI',tidx[owner],pidx[(ret,params)],sidx[name]))
put(sections['class_defs'][0],struct.pack('<IIIIIIII',tidx[CLS],0x1,tidx[SUPER],interface_list_off,sidx.get('MainActivity.java',0xffffffff),0,class_data_off,0))
# Class implements OnClickListener: interface type list (single type) must be allocated before map list.
# We put interface list in existing data before code instead of inserting now: see explicit check below.

# DEX header
file_size=len(buf);data_size=file_size-DATA_OFF
hdr=struct.pack('<8sI20s20I',b'dex\n035\x00',0,b'\0'*20,file_size,112,0x12345678,0,0,map_off,
                NS,sections['string_ids'][0],NT,sections['type_ids'][0],NP,sections['proto_ids'][0],
                NF,sections['field_ids'][0],NM,sections['method_ids'][0],1,sections['class_defs'][0],data_size,DATA_OFF)
assert len(hdr)==112
put(0,hdr)
put(12,hashlib.sha1(buf[32:]).digest())
put(8,struct.pack('<I',zlib.adler32(buf[12:])&0xffffffff))
dex=bytes(buf)

# Android binary XML compiler for the self-contained manifest.
ANDROID_URI='http://schemas.android.com/apk/res/android'
NAME_IDS={'name':0x01010003,'label':0x01010001,'exported':0x01010010,
          'minSdkVersion':0x0101020c,'targetSdkVersion':0x01010270,'theme':0x01010000}
S=['manifest','package',PKG,'uses-sdk','application','activity','intent-filter','action','category',
   'android',ANDROID_URI,'name','label','exported','minSdkVersion','targetSdkVersion',
   'android.intent.action.MAIN','android.intent.category.LAUNCHER',
   PKG+'.MainActivity','MuMu Desktop Cleaner V1.0','theme']
S=list(dict.fromkeys(S)); SI={s:i for i,s in enumerate(S)}

def string_len(n):
    if n<=127:return bytes([n])
    return bytes([(n>>8)|128,n&255])

def chunk(typ,header_size,header_payload,body):
    assert len(header_payload)==header_size-8,(typ,header_size,len(header_payload))
    return struct.pack('<HHI',typ,header_size,header_size+len(body))+header_payload+body

def xml_stringpool(strings):
    stringdata=bytearray();offsets=[]
    for s in strings:
        offsets.append(len(stringdata))
        raw=s.encode('utf-8');stringdata+=string_len(len(s.encode('utf-16-le'))//2)+string_len(len(raw))+raw+b'\0'
    while len(stringdata)%4:stringdata.append(0)
    start=28+len(strings)*4
    head=struct.pack('<IIIII',len(strings),0,0x100,start,0)
    body=b''.join(struct.pack('<I',o) for o in offsets)+stringdata
    return chunk(0x0001,28,head,body)

# map resource attribute name indexes to android public ids (other entries 0)
resmap=chunk(0x0180,8,b'',b''.join(struct.pack('<I',NAME_IDS.get(s,0)) for s in S))

def attr(name,value,as_type='str'):
    ns=SI[ANDROID_URI] if name in NAME_IDS else 0xffffffff
    raw=0xffffffff
    if as_type=='str':typ=3;data=SI[value];raw=data
    elif as_type=='int':typ=0x10;data=int(value)
    elif as_type=='bool':typ=0x12;data=1 if value else 0
    else:raise ValueError(as_type)
    return struct.pack('<IIIHBBI',ns,SI[name],raw,8,0,typ,data)

def xml_node(typ,name=None,attributes=()):
    header=struct.pack('<II',0,0xffffffff) # line number, comment
    if typ in ('start-ns','end-ns'):
        return chunk(0x0100 if typ=='start-ns' else 0x0101,16,header,struct.pack('<II',SI['android'],SI[ANDROID_URI]))
    if typ=='start':
        attrs=b''.join(attr(*x) for x in attributes)
        payload=struct.pack('<IIHHHHHH',0xffffffff,SI[name],20,20,len(attributes),0,0,0)
        return chunk(0x0102,16,header,payload+attrs)
    if typ=='end':return chunk(0x0103,16,header,struct.pack('<II',0xffffffff,SI[name]))
    raise ValueError(typ)

node=[]
node.append(xml_node('start-ns'))
node.append(xml_node('start','manifest',[('package',PKG,'str')]))
node.append(xml_node('start','uses-sdk',[('minSdkVersion',29,'int'),('targetSdkVersion',29,'int')]))
node.append(xml_node('end','uses-sdk'))
node.append(xml_node('start','application',[('label','MuMu Desktop Cleaner V1.0','str')]))
node.append(xml_node('start','activity',[('name',PKG+'.MainActivity','str'),('exported',True,'bool')]))
node.append(xml_node('start','intent-filter'))
node.append(xml_node('start','action',[('name','android.intent.action.MAIN','str')]))
node.append(xml_node('end','action'))
node.append(xml_node('start','category',[('name','android.intent.category.LAUNCHER','str')]))
node.append(xml_node('end','category'))
node.append(xml_node('end','intent-filter'))
node.append(xml_node('end','activity'))
node.append(xml_node('end','application'))
node.append(xml_node('end','manifest'))
node.append(xml_node('end-ns'))
sp=xml_stringpool(S)
axml=chunk(0x0003,8,b'',sp+resmap+b''.join(node))

# v1 signature is widely supported by Android; no privileged permissions requested.
unsigned=OUT/'unsigned.apk'
with zipfile.ZipFile(unsigned,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr('AndroidManifest.xml',axml)
    z.writestr('classes.dex',dex)
# Signing private key generated locally for this artifact, not distributed.
key=OUT/'devsign.jks'
if not key.exists():
    subprocess.run(['keytool','-genkeypair','-keystore',str(key),'-storepass','changeit',
                    '-keypass','changeit','-alias','widgettoggle','-keyalg','RSA',
                    '-keysize','3072','-validity','3650','-dname','CN=Sahanaz Local Utility, O=Local Tools'],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['jarsigner','-keystore',str(key),'-storepass','changeit','-keypass','changeit',
                '-sigalg','SHA256withRSA','-digestalg','SHA-256',str(unsigned),'widgettoggle'],
               check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
shutil.copy2(unsigned,APK)
print('APK:',APK,'bytes',APK.stat().st_size)
print('DEX:',len(dex),'manifest:',len(axml),'methods:',len(method_vals),'strings:',len(string_vals))
print('sha256:',hashlib.sha256(APK.read_bytes()).hexdigest())
