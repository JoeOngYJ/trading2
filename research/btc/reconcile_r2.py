"""R2 frozen archive gate and recorded-fill arithmetic replay."""
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal as D, Context, localcontext
from fractions import Fraction as F
from pathlib import Path
from research.btc.reference_r1 import account

ROOT=Path(__file__).resolve().parents[2]
BASE='artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/'
SCENARIOS=tuple('candle-'+s+'-v1' for s in ('primary-30bps-rt','stress-40bps-rt','severe-80bps-rt'))
FIELDS=('entry_fill','exit_fill','entry_reference','exit_reference','quantity')
CASH=('cash_before','remaining_cash','cash_after','pnl_quote')
TIMES=('signal_ms','entry_ms','exit_ms')
LOW=1546300800000
HIGH=1767225600000


def checked_bytes(path, digest, size=None):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('symlink input')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest or (size is not None and len(raw)!=size):
        raise ValueError('input checksum/size')
    return raw


def decode(text):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate key')
            out[k]=v
        return out
    def invalid(_):raise ValueError('nonfinite JSON')
    return json.loads(text,parse_float=D,parse_int=D,parse_constant=invalid,object_pairs_hook=pairs)


def gate(rows):
    if len(rows)!=201:raise ValueError('record count')
    counts=Counter();previous={};issues={}
    for row in rows:
        if not isinstance(row,dict) or not set((*FIELDS,*CASH,*TIMES,'scenario_id'))<=set(row):
            raise ValueError('missing fields')
        scenario=row['scenario_id']
        if scenario not in SCENARIOS:raise ValueError('scenario')
        counts[scenario]+=1
        for name in (*FIELDS,*CASH,*TIMES):
            x=row[name]
            if not isinstance(x,D) or not x.is_finite():raise ValueError('numeric type')
            if name in FIELDS and x<=0:raise ValueError('nonpositive value')
            if name in CASH[:-1] and x<0:raise ValueError('negative cash')
        for name in TIMES:
            x=row[name]
            if not LOW<=x<HIGH or x!=int(x) or int(x)%1000:raise ValueError('timestamp boundary')
        if not row['signal_ms']<=row['entry_ms']<=row['exit_ms']:raise ValueError('timestamp order')
        if scenario in previous and row['entry_ms']<previous[scenario]:raise ValueError('overlap')
        previous[scenario]=row['exit_ms']
        for name in FIELDS:
            # Remove insignificant decimal zeros without using caller-context normalize().
            s=format(row[name],'f')
            if '.' in s:s=s.rstrip('0').rstrip('.')
            digits=len(s.replace('.',''));fraction=len(s.split('.')[1]) if '.' in s else 0
            if digits>18 or fraction>12:
                a=issues.setdefault(name,dict(count=0,max_digits=0,max_fractional_digits=0))
                a['count']+=1;a['max_digits']=max(a['max_digits'],digits)
                a['max_fractional_digits']=max(a['max_fractional_digits'],fraction)
    if counts!=Counter({s:67 for s in SCENARIOS}):raise ValueError('scenario count')
    return dict(status='blocked_numeric_compatibility' if issues else 'compatible',
                record_count=len(rows),scenario_counts=dict(counts),incompatible_fields=issues)


def close(actual, expected):
    a,b=F(actual),F(expected)
    return abs(a-b)<=F('0.00000001')+F('0.000000000001')*abs(b)


def reconcile(events, states):
    if len(events)!=len(states):raise ValueError('oracle row count')
    inv=F(0);notional=F(0);fees=F(0);cash=F(1000)
    for e,r in zip(events,states):
        if (r['sequence'],r['timestamp'],r['kind'])!=(e['sequence'],e['timestamp'],e['kind']):raise ValueError('oracle identity')
        if F(r['cash_before'])!=cash or F(r['inventory_before'])!=inv:raise ValueError('oracle prestate')
        q=F(e['quantity'])*(1 if e['side']=='buy' else -1)
        inv+=q;notional+=q*F(e['fill_price']);fees+=F(e['quote_fee']);cash=F(1000)-notional-fees
        for k,v in dict(cash=cash,inventory=inv,fees=fees,signed_fill_notional=notional,equity=cash+inv*F(e['mark_price'])).items():
            if F(r[k])!=v:raise ValueError('oracle '+k)


def replay(rows):
    result=gate(rows)
    if result['status']!='compatible':return result
    with localcontext(Context(prec=80)):
        outputs={}
        for scenario in SCENARIOS:
            trades=[r for r in rows if r['scenario_id']==scenario];events=[]
            for r in trades:
                for side,prefix in [('buy','entry'),('sell','exit')]:
                    def ordinary(x):
                        s=format(x,'f');return s.rstrip('0').rstrip('.') if '.' in s else s
                    events.append(dict(sequence=len(events)+1,kind='fill',side=side,quote_fee='0',
                        timestamp=datetime.fromtimestamp(int(r[prefix+'_ms'])//1000,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        quantity=ordinary(r['quantity']),fill_price=ordinary(r[prefix+'_fill']),mark_price=ordinary(r[prefix+'_reference'])))
            try:
                states=account(events)
                reconcile(events,states)
            except ValueError as exc:
                outputs[scenario]=dict(passed=False,status='accounting_or_oracle_failure',reason=str(exc))
                continue
            differences=[]
            for n,r in enumerate(trades):
                entry,exit=states[2*n:2*n+2]
                values={'cash_before':entry['cash_before'],'remaining_cash':entry['cash'],
                        'cash_after':exit['cash'],'pnl_quote':exit['cash']-entry['cash_before']}
                for field,value in values.items():
                    error=value-r[field]
                    differences.append(dict(trade=n,field=field,error=str(error),relative_error=str(abs(error/r[field])) if r[field] else None,passed=close(value,r[field])))
                prior=trades[n-1]['cash_after'] if n else D('1000')
                error=r['cash_before']-prior
                differences.append(dict(trade=n,field='source_carryforward',error=str(error),
                    relative_error=str(abs(error/prior)) if prior else None,passed=close(r['cash_before'],prior)))
            outputs[scenario]=dict(comparisons=differences,passed=all(x['passed'] for x in differences),
                maximum_absolute_error=str(max(abs(D(x['error'])) for x in differences)),
                maximum_relative_error=str(max((D(x['relative_error']) for x in differences if x['relative_error'] is not None),default=D(0))),
                final_cash=str(states[-1]['cash']),terminal_return=str(states[-1]['cash']/1000-1))
        return dict(status='reconciled' if all(o['passed'] for o in outputs.values()) else 'discrepancy',scenarios=outputs)


def run_archive():
    checked_bytes(ROOT/BASE/'manifest.json','5a99488be5dd8fac7b5d1628a3335fc9fb3548745cdb0269604e1d9d860af435')
    raw=checked_bytes(ROOT/BASE/'breakout-trades.jsonl.gz','22d68c6174edc18b055041ba3a32c03c1f8945d9e532b7169bcb370507629809',25331)
    rows=[decode(line) for line in gzip.decompress(raw).decode('utf-8').splitlines()]
    return replay(rows)
