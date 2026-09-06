#!/usr/bin/env python3
"""Install the already-built dashboard as a local service on this Mac."""
import os, plistlib, re, shutil, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
BASE=Path.home()/'Library/Application Support/AntennaObservatory'
LABEL='local.antenna-observatory.web'
FRAME_LABEL='local.antenna-observatory.frames'
DOMAIN=f'gui/{os.getuid()}'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
FRAME_PLIST=Path.home()/'Library/LaunchAgents'/f'{FRAME_LABEL}.plist'
READSB_PLIST=Path.home()/'Library/LaunchAgents/local.airplanes-live.readsb.plist'

def run(*args):
    return subprocess.run(args,check=False,capture_output=True,text=True)

def replace_launch_agent(path,job):
    """Atomically replace a user LaunchAgent and restore it if bootstrap fails."""
    original=path.read_bytes() if path.is_file() else None
    loaded=run('/bin/launchctl','print',f'{DOMAIN}/{job["Label"]}').returncode==0
    if loaded:
        result=run('/bin/launchctl','bootout',f'{DOMAIN}/{job["Label"]}')
        if result.returncode:raise SystemExit(result.stderr)
    temporary=path.with_suffix('.tmp');temporary.write_bytes(plistlib.dumps(job));temporary.chmod(0o644);temporary.replace(path)
    result=run('/bin/launchctl','bootstrap',DOMAIN,str(path))
    if result.returncode:
        if original is None:path.unlink(missing_ok=True)
        else:path.write_bytes(original);path.chmod(0o644)
        if loaded and original is not None:run('/bin/launchctl','bootstrap',DOMAIN,str(path))
        raise SystemExit(result.stderr)

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
    if not (BASE/'state/relay-token').is_file(): raise SystemExit('Configure the protected telemetry relay before installing.')
    zstd=Path('/opt/homebrew/bin/zstd')
    if not zstd.is_file():raise SystemExit('Install zstd with Homebrew before enabling Beast archival.')
    try:readsb_job=plistlib.loads(READSB_PLIST.read_bytes())
    except (OSError,ValueError):raise SystemExit('The installed readsb LaunchAgent is unavailable or invalid.')
    BASE.mkdir(parents=True,exist_ok=True)
    stage=BASE/'app-next';installed=BASE/'app';previous=BASE/'app-previous'
    if stage.exists(): shutil.rmtree(stage)
    (stage/'server').mkdir(parents=True)
    shutil.copytree(built,stage/'dist/client')
    shutil.copy2(ROOT/'server/observatory.py',stage/'server/observatory.py')
    (stage/'ops').mkdir()
    shutil.copy2(ROOT/'ops/telemetry-uplink.py',stage/'ops/telemetry-uplink.py')
    shutil.copy2(ROOT/'ops/frame-uplink.py',stage/'ops/frame-uplink.py')
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
    result=run('/bin/launchctl','bootstrap',DOMAIN,str(PLIST))
    if result.returncode: raise SystemExit(result.stderr)

    state=BASE/'state';dump=state/'beast-dump';spool=state/'beast-spool';status=state/'frame-uplink-status.json'
    for path in (dump,spool):path.mkdir(parents=True,exist_ok=True)
    frame_log=Path.home()/'Library/Logs/antenna-observatory-frames.log'
    frame_job={'Label':FRAME_LABEL,'ProgramArguments':['/usr/bin/python3',str(installed/'ops/frame-uplink.py'),'--remote','https://antenna.ramideltoro.com/api/ingest/beast','--token-file',str(state/'relay-token'),'--dump-dir',str(dump),'--spool-dir',str(spool),'--status-file',str(status),'--zstd',str(zstd)],'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,'StandardOutPath':str(frame_log),'StandardErrorPath':str(frame_log)}
    replace_launch_agent(FRAME_PLIST,frame_job)

    arguments=readsb_job.get('ProgramArguments',[]);dump_argument='--dump-beast='+str(dump)+',120,1'
    updated=[value for value in arguments if not value.startswith('--dump-beast=')]
    if '--dump-beast' in updated:
        index=updated.index('--dump-beast');del updated[index:index+2]
    updated.append(dump_argument)
    if arguments!=updated:
        readsb_job['ProgramArguments']=updated;replace_launch_agent(READSB_PLIST,readsb_job)
    print('Installed Antenna Observatory at http://127.0.0.1:8787/')

if __name__=='__main__':main()
