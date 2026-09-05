#!/usr/bin/env python3
"""Install the already-built dashboard as a login service on this Mac."""
import os, plistlib, re, shutil, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
BASE=Path.home()/'Library/Application Support/AntennaObservatory'
LABEL='local.antenna-observatory.web'
DOMAIN=f'gui/{os.getuid()}'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
READSB_PLIST=Path.home()/'Library/LaunchAgents/local.airplanes-live.readsb.plist'

def run(*args):
    return subprocess.run(args,check=False,capture_output=True,text=True)

def receiver_environment():
    """Read non-secret receiver identity from the installed readsb service."""
    result={'PYTHONUNBUFFERED':'1','ANTENNA_DEVICE_MODEL':'Nooelec NESDR SMArt v5'}
    try:
        args=plistlib.loads(READSB_PLIST.read_bytes()).get('ProgramArguments',[])
    except (OSError, ValueError):
        return result
    if '--device' in args and args.index('--device')+1<len(args):
        result['ANTENNA_DEVICE_SERIAL']=args[args.index('--device')+1]
    connector=next((value for value in args if 'feed.airplanes.live' in value), '')
    match=re.search(r'(?:^|,)uuid=([0-9a-fA-F-]{36})(?:,|$)',connector)
    if match: result['ANTENNA_FEEDER_ID']=match.group(1).lower()
    return result

def main():
    built=ROOT/'dist/client'
    if not (built/'index.html').is_file(): raise SystemExit('Build the website first: pnpm build')
    if not (BASE/'state/account.json').is_file(): raise SystemExit('Configure the single dashboard account before installing.')
    if not (BASE/'state/relay-token').is_file(): raise SystemExit('Configure the protected telemetry relay before installing.')
    BASE.mkdir(parents=True,exist_ok=True)
    stage=BASE/'app-next';installed=BASE/'app';previous=BASE/'app-previous'
    if stage.exists(): shutil.rmtree(stage)
    (stage/'server').mkdir(parents=True)
    shutil.copytree(built,stage/'dist/client')
    shutil.copy2(ROOT/'server/observatory.py',stage/'server/observatory.py')
    shutil.copy2(ROOT/'server/login.html',stage/'server/login.html')
    (stage/'ops').mkdir()
    shutil.copy2(ROOT/'ops/telemetry-uplink.py',stage/'ops/telemetry-uplink.py')
    if run('/bin/launchctl','print',f'{DOMAIN}/{LABEL}').returncode==0:
        result=run('/bin/launchctl','bootout',f'{DOMAIN}/{LABEL}')
        if result.returncode: raise SystemExit(result.stderr)
        for _ in range(40):
            if run('/bin/launchctl','print',f'{DOMAIN}/{LABEL}').returncode: break
            time.sleep(.25)
        else: raise SystemExit('The previous website service did not stop. Installed files have not changed.')
    if previous.exists(): shutil.rmtree(previous)
    if installed.exists(): installed.rename(previous)
    stage.rename(installed)
    PLIST.parent.mkdir(parents=True,exist_ok=True)
    log=Path.home()/'Library/Logs/antenna-observatory.log';log.parent.mkdir(parents=True,exist_ok=True)
    job={'Label':LABEL,'ProgramArguments':['/usr/bin/python3',str(installed/'server/observatory.py'),'--port','8787'],'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,'StandardOutPath':str(log),'StandardErrorPath':str(log),'EnvironmentVariables':receiver_environment()}
    PLIST.write_bytes(plistlib.dumps(job));PLIST.chmod(0o644)
    shutil.copy2(PLIST,ROOT/'ops'/PLIST.name)
    result=run('/bin/launchctl','bootstrap',DOMAIN,str(PLIST))
    if result.returncode: raise SystemExit(result.stderr)
    print('Installed Antenna Observatory at http://127.0.0.1:8787/')

if __name__=='__main__':main()
