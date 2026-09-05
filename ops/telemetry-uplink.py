#!/usr/bin/env python3
"""Push protected local receiver telemetry to the remote dashboard relay."""
import argparse,json,ssl,time,urllib.error,urllib.request
from pathlib import Path

def request(url,token,method='GET',body=None):
    data=json.dumps(body,allow_nan=False).encode() if body is not None else None
    headers={'Authorization':'Bearer '+token,'User-Agent':'AntennaObservatory-Uplink/1'}
    if data is not None:headers['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=20,context=ssl.create_default_context()) as response:
        return json.load(response)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--local',default='http://127.0.0.1:8787/api/uplink');parser.add_argument('--remote',required=True);parser.add_argument('--token-file',required=True);args=parser.parse_args()
    token=Path(args.token_file).read_text().strip()
    if len(token)<32:raise SystemExit('Invalid relay token')
    failures=0
    while True:
        try:
            payload=request(args.local,token)
            request(args.remote,token,'POST',payload)
            if failures:print('Telemetry uplink restored.',flush=True)
            failures=0;time.sleep(2)
        except (OSError,ValueError,urllib.error.URLError) as error:
            failures+=1
            if failures==1 or failures%30==0:print(f'Telemetry uplink unavailable ({type(error).__name__}); retrying.',flush=True)
            time.sleep(min(30,2**min(failures,5)))

if __name__=='__main__':main()
