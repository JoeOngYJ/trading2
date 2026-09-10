import copy
import unittest
from fractions import Fraction as F
from decimal import Decimal as D, localcontext, Inexact
from research.btc.reference_r1_v3 import account


def events(specs):
    output=[]
    for n,(side,q,p,fee,mark) in enumerate(specs,1):
        e=dict(sequence=n,timestamp=f'2020-01-01T00:{(n-1)*5:02}:00Z',
               kind='mark' if side is None else 'fill',mark_price=mark)
        if side is not None:e.update(side=side,quantity=q,fill_price=p,quote_fee=fee)
        output.append(e)
    return output


def reconcile(source, rows):
    """Independent exact rational oracle, from input events, without engine helpers."""
    assert len(rows)==len(source)
    cash,inventory,fees,notional=F(1000),F(0),F(0),F(0)
    for event,row in zip(source,rows):
        assert row['sequence']==event['sequence'] and row['timestamp']==event['timestamp']
        assert row['kind']==event['kind']
        assert F(row['cash_before'])==cash and F(row['inventory_before'])==inventory
        if event['kind']=='fill':
            signed=F(event['quantity'])*(1 if event['side']=='buy' else -1)
            notional+=signed*F(event['fill_price'])
            fees+=F(event['quote_fee'])
            inventory+=signed
        cash=F(1000)-notional-fees
        expected=dict(cash=cash,inventory=inventory,equity=cash+inventory*F(event['mark_price']),
                      fees=fees,signed_fill_notional=notional)
        for key,value in expected.items():assert F(row[key])==value,(key,row[key],value)


class R1Tests(unittest.TestCase):
    def test_literals(self):
        buy=('buy','2','100','0','100')
        cases=[
          ([(None,None,None,None,'100')],[('1000','0','1000','0')]),
          ([('buy','2','100.15','0','100'),('sell','2','99.85','0','100')],[('799.7','2','999.7','0'),('999.4','0','999.4','0')]),
          ([('buy','2','100','0.3','100'),('sell','2','100','0.3','100')],[('799.7','2','999.7','0.3'),('999.4','0','999.4','0.6')]),
          ([buy,('sell','1','110','0','110'),(None,None,None,None,'90'),('sell','1','90','0','90')],[('800','2','1000','0'),('910','1','1020','0'),('910','1','1000','0'),('1000','0','1000','0')]),
          ([buy,('sell','2','110','0','110'),('buy','1','100','0','100'),('sell','1','90','0','90')],[('800','2','1000','0'),('1020','0','1020','0'),('920','1','1020','0'),('1010','0','1010','0')]),
          ([buy,(None,None,None,None,'110')],[('800','2','1000','0'),('800','2','1020','0')]),
          ([('buy','1','100','0','100'),('sell','1','100','0','100')],[('900','1','1000','0'),('1000','0','1000','0')]),
          ([('buy','1','100','0','100'),('buy','1','100','0','100')],[('900','1','1000','0'),('800','2','1000','0')])]
        for n,(specs,literals) in enumerate(cases):
            with self.subTest(case=n+1):
                source=events(specs)
                if n==6:source[1]['timestamp']=source[0]['timestamp']
                rows=account(source);reconcile(source,rows)
                self.assertEqual(len(rows),len(literals))
                for row,state in zip(rows,literals):
                    self.assertEqual(tuple(row[k] for k in ('cash','inventory','equity','fees')),tuple(map(D,state)))

    def test_invalid(self):
        source=events([('buy','2','100','0','100')])
        invalid=[[],source*10001,{},[None]]
        for key,value in [('sequence',True),('sequence',2),('side','short'),('kind','order'),
                          ('timestamp','2020-02-30T00:00:00Z'),('timestamp','2020-01-01T00:00:00'),
                          ('quantity','0'),('quantity',1.0),('fill_price','NaN'),('mark_price','-1'),
                          ('quote_fee','1e-3'),('quantity','1'*33),('quantity','0.'+'1'*25),
                          ('quantity','11'),('side','sell'),('extra','x')]:
            x=copy.deepcopy(source);x[0][key]=value;invalid.append(x)
        x=copy.deepcopy(source);del x[0]['quantity'];invalid.append(x)
        for sequence,time in [(1,'2020-01-01T00:05:00Z'),(2,'2019-12-31T23:00:00Z')]:
            x=source+copy.deepcopy(source);x[1].update(sequence=sequence,timestamp=time);invalid.append(x)
        invalid.append(events([('buy','2','100','0','100'),('sell','2','100','1001','100')]))
        for n,x in enumerate(invalid):
            with self.subTest(n=n),self.assertRaises(ValueError):account(x)

    def test_independence_and_discrepancy(self):
        source=events([('buy','2','100.15','0','100'),(None,None,None,None,'110')])
        rows=account(source)
        bad=copy.deepcopy(rows);bad[0]['cash']+=D('0.01')
        with self.assertRaises(AssertionError):reconcile(source,bad)
        with localcontext() as ctx:
            ctx.prec=3;ctx.traps[Inexact]=True
            self.assertEqual(account(source),rows)
        changed=copy.deepcopy(source);changed[1]['mark_price']='90'
        self.assertEqual(account(changed)[0],rows[0])
        reconcile(source,rows)

    def test_mixed_scale_precision_regression(self):
        specs=[('buy','1','1','0','1'),('sell','1','999999999999999999','0','1'),
               ('buy','0.000000000001','0.000000000001','0','1'),
               ('buy','999999999999999999','0.000000000001','0','999999999999999999')]
        source=events(specs);reconcile(source,account(source))
        # Maximum permitted event count, mixed magnitudes and 24-place products.
        source=events(specs[:3])
        for n in range(4,10001):
            source.append(dict(sequence=n,timestamp=source[-1]['timestamp'],kind='fill',side='buy',
                               quantity='1',fill_price='0.000000000001',quote_fee='0',
                               mark_price='999999999999999999'))
        reconcile(source,account(source))

    def test_wide_domain_extremes(self):
        huge='9'*32
        tiny='0.'+'0'*23+'1'
        source=events([('buy','1','1','0','1'),('sell','1',huge,'0',huge),
                       ('buy',tiny,tiny,'0',huge)])
        for n in range(4,10001):
            source.append(dict(sequence=n,timestamp=source[-1]['timestamp'],kind='fill',side='buy',
                               quantity=huge,fill_price=tiny,quote_fee=tiny,mark_price=huge))
        reconcile(source,account(source))
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            reconcile(source,account(source))


if __name__=='__main__':unittest.main()
