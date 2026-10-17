#!/usr/bin/env python3
"""Read-only performance and controller observation; never activates the game UI."""
import argparse
import bisect
import collections
import json
from pathlib import Path
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'work/run'

def rows(name):
    result=[]
    path=RUN/name
    if path.exists():
        for line in path.read_text(errors='replace').splitlines():
            try: result.append(json.loads(line))
            except ValueError: pass  # The writer may still be completing its last line.
    return result

def stats(values):
    if not values:return None
    values=sorted(values)
    return {'count':len(values),'p50':round(statistics.median(values),2),
            'p95':round(values[min(len(values)-1,int(len(values)*.95))],2),'max':round(values[-1],2)}

def snapshot(seconds=30):
    frames=collections.defaultdict(dict)
    p=RUN/'performance.tsv'
    if p.exists():
        for line in p.read_text(errors='replace').splitlines():
            parts=line.split('\t')
            if len(parts)!=3:continue
            try: frames[int(parts[0])][parts[1]]=float(parts[2])
            except ValueError:pass
    end=max((r.get('@t_s',0) for r in frames.values()),default=0)
    selected={f:r for f,r in frames.items() if r.get('@t_s',-1)>=max(0,end-seconds)}
    metrics={key:stats([r[key] for r in selected.values() if key in r and r[key]>=0])
             for key in ['@frame_ms','@gpu_ms','@presented_ms','@nvn_ms','@work_ms','@wait_ms','@pq_wait_ms','@upload_ms']}
    receipts=rows('controller.jsonl'); events=rows('controller-events.jsonl')
    hid=sorted((r for r in receipts if 'time_ns' in r),key=lambda r:r['read_start_ns']); ev=[r for r in events if 'time_ns' in r]
    last=max([r['time_ns'] for r in hid+ev],default=0)
    recent=[r for r in ev if r['time_ns']>=last-seconds*1e9]
    reads=[r for r in hid if r['time_ns']>=last-seconds*1e9]
    starts=[r['read_start_ns'] for r in hid]
    presses=[]; previous=0
    for event in ev:
        rising=event['buttons'] & ~previous; previous=event['buttons']
        if not rising or not event['active'] or event['time_ns']<last-seconds*1e9:continue
        i=bisect.bisect_left(starts,event['time_ns'])
        match=next((r for r in hid[i:] if r['read_start_ns']-event['time_ns']<=500_000_000 and r['buttons']&rising==rising),None)
        if match:presses.append((match['read_start_ns']-event['time_ns'])/1e6)
    text=(RUN/'app.log').read_text(errors='replace') if (RUN/'app.log').exists() else ''
    red=[line for line in text.splitlines() if any(k in line for k in ['【红】','CRASH','FATAL','UNIMPL'])]
    running=any(line.startswith(str(RUN.parent/name/'DR3 Mobile.app/Contents/MacOS/dmhost')+' ') for line in subprocess.check_output(['ps','-axo','command'],text=True).splitlines() for name in ['macapp','macapp-candidate','macapp-lantern','macapp-complete'])
    return {'running':running,'host_seconds':round(end,2),'frames_in_window':len(selected),'metrics_ms':metrics,
            'median_passes':stats([r['@passes'] for r in selected.values() if '@passes' in r]),
            'median_draws':stats([r['@draws'] for r in selected.values() if '@draws' in r]),
            'uniform_forward_updates':sum(r.get('@uf_updates',0) for r in selected.values()),
            'uniform_forward_bindings':sum(r.get('@uf_bindings',0) for r in selected.values()),
            'uniform_forward_rejects':sum(r.get('@uf_rejects',0) for r in selected.values()),
            'uniform_forward_feedback_splits':sum(r.get('@uf_feedback_splits',0) for r in selected.values()),
            'pipeline_creations':sum(r.get('@pso_new',0) for r in selected.values()),
            'library_creations':sum(r.get('@lib_new',0) for r in selected.values()),
            'controller_publications':len(recent),'hid_receipts':len(reads),
            'last_controller_state':ev[-1] if ev else None,
            'last_controller_event_age_ms':round((last-ev[-1]['time_ns'])/1e6,2) if ev else None,
            'presented_samples':sum(r.get('@presented_ms',-1)>=0 for r in selected.values()),
            'discarded_samples':sum(r.get('@presented_ms',0)<0 for r in selected.values()),
            'matched_press_to_hid_ms':stats(presses),
            'receipt_limit_reached':any('limit_reached' in r for r in receipts),
            'recent_warnings':red[-4:],
            'limitations':['Input latencies cover only matched published button presses; no unmatched event is classified as a lost press.',
                           'Game frame time and asynchronous GPU span differ from actual display intervals.',
                           'Scene, focus and loading must be identified separately.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--follow',type=int,default=0,help='observe this many seconds; 0 prints one snapshot')
    parser.add_argument('--interval',type=int,default=20)
    args=parser.parse_args(); deadline=time.monotonic()+args.follow
    while True:
        data=snapshot()
        (RUN/'monitor-latest.json').write_text(json.dumps(data,indent=2)+'\n')
        print(json.dumps(data),flush=True)
        if time.monotonic()>=deadline or not data['running']:break
        time.sleep(min(args.interval,deadline-time.monotonic()))

if __name__=='__main__':main()
