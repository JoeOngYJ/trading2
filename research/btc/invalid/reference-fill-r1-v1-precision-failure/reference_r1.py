"""Synthetic explicit-fill bookkeeping. No execution model or external I/O."""
import re
from datetime import datetime
from decimal import Decimal, Context, localcontext, ROUND_HALF_EVEN


def _amount(value, positive=False):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value):
        raise ValueError('ordinary decimal string required')
    if len(value.replace('.',''))>18 or ('.' in value and len(value.split('.')[1])>12):
        raise ValueError('amount outside qualified domain')
    result=Decimal(value)
    if positive and result<=0:
        raise ValueError('positive amount required')
    return result


def account(events):
    if not isinstance(events,list) or not 1<=len(events)<=10000:
        raise ValueError('event count')
    parsed=[]
    previous=None
    for sequence,event in enumerate(events,1):
        if not isinstance(event,dict):
            raise ValueError('event object required')
        kind=event.get('kind')
        keys={'sequence','timestamp','kind','mark_price'}
        if kind=='fill':
            keys|={'side','quantity','fill_price','quote_fee'}
        elif kind!='mark':
            raise ValueError('kind')
        if set(event)!=keys or type(event['sequence']) is not int or event['sequence']!=sequence:
            raise ValueError('schema or sequence')
        t=event['timestamp']
        if not isinstance(t,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',t):
            raise ValueError('UTC timestamp required')
        time=datetime.strptime(t,'%Y-%m-%dT%H:%M:%SZ')
        if previous is not None and time<previous:
            raise ValueError('reversed time')
        previous=time
        mark=_amount(event['mark_price'],True)
        q,p,fee=Decimal(0),Decimal(0),Decimal(0)
        if kind=='fill':
            if event['side'] not in ('buy','sell'):
                raise ValueError('side')
            q=_amount(event['quantity'],True)
            p=_amount(event['fill_price'],True)
            fee=_amount(event['quote_fee'])
        parsed.append((event.copy(),mark,q,p,fee))
    with localcontext(Context(prec=50,rounding=ROUND_HALF_EVEN)):
        cash,inventory,fees,notional=map(Decimal,('1000','0','0','0'))
        rows=[]
        for event,mark,q,p,fee in parsed:
            before_cash,before_inventory=cash,inventory
            if event['kind']=='fill':
                signed=q if event['side']=='buy' else -q
                cash-=signed*p+fee
                inventory+=signed
                if cash<0 or inventory<0:
                    raise ValueError('insufficient cash or inventory')
                fees+=fee
                notional+=signed*p
            rows.append(dict(sequence=event['sequence'],timestamp=event['timestamp'],kind=event['kind'],
                             cash_before=before_cash,inventory_before=before_inventory,cash=cash,
                             inventory=inventory,equity=cash+inventory*mark,fees=fees,
                             signed_fill_notional=notional))
        return rows
