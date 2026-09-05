#!/usr/bin/env python3
"""Small unprivileged process supervisor for the ServerCheap deployment."""
import argparse,fcntl,os,signal,subprocess,time
from pathlib import Path

BASE=Path.home()/'antenna-observatory'
STATE=Path.home()/'.local/share/antenna-observatory'
LOGS=Path.home()/'.local/state/antenna-observatory'
child=None
stopping=False

def stop(_signal,_frame):
    global stopping
    stopping=True
    if child and child.poll() is None:child.terminate()

def main():
    global child
    parser=argparse.ArgumentParser();parser.add_argument('service',choices=('relay','tunnel'));args=parser.parse_args()
    STATE.mkdir(parents=True,exist_ok=True);LOGS.mkdir(parents=True,exist_ok=True)
    lock=(STATE/(args.service+'.lock')).open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    if args.service=='relay':
        command=['python3',str(BASE/'current/server/observatory.py'),'--relay','--port','8787']
        env=dict(os.environ,ANTENNA_STATE_DIR=str(STATE),PYTHONUNBUFFERED='1')
    else:
        command=[str(Path.home()/'.local/bin/cloudflared'),'tunnel','--no-autoupdate','--metrics','127.0.0.1:8788','run','--token-file',str(STATE/'tunnel-token')]
        env=os.environ.copy()
    with (LOGS/(args.service+'.log')).open('ab',buffering=0) as log:
        while not stopping:
            child=subprocess.Popen(command,stdout=log,stderr=log,env=env)
            child.wait();child=None
            if not stopping:time.sleep(5)

if __name__=='__main__':main()
