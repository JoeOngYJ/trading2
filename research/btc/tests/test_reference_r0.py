import unittest
from decimal import Decimal as D, getcontext, localcontext, Inexact
from research.btc.reference_r0 import run, InputError


def order(side='buy', quantity='2', decision='00:30:00', available=None):
    return dict(side=side, quantity=quantity, decision='2020-01-01T'+decision+'Z',
                available='2020-01-01T'+(available or decision)+'Z')


def bars(last='100'):
    return [('2020-01-01T00:00:00Z','100'),('2020-01-01T01:00:00Z','100'),
            ('2020-01-01T02:00:00Z',last)]


class ReferenceTests(unittest.TestCase):
    def check_case(self, orders, expected, last='100', **rules):
        rows = run(bars(last), orders, **rules)
        self.assertEqual(len(rows),3)
        self.assertEqual([r['timestamp'] for r in rows],[t for t,_ in bars(last)])
        self.assertEqual(rows[0]['disposition'],'hold')
        for row, state in zip(rows, [('1000','0','1000')]+expected):
            self.assertEqual(tuple(row[k] for k in ('cash','inventory','equity')), tuple(map(D,state)))
        # Independent cumulative cashflow oracle: no engine arithmetic helpers.
        with localcontext() as ctx:
            ctx.prec = 50
            buys, sells, charges, positions, gross, costs = [], [], [], [], [], []
            for (_, raw), row in zip(bars(last), rows):
                if row['disposition'] == 'filled':
                    q = row['signed_quantity']
                    rate = D(rules.get('slippage_bps','0'))/D('10000')
                    px = D(raw) + (D(raw)*rate if q > 0 else -D(raw)*rate)
                    self.assertEqual(row['fill_price'],px)
                    charge = abs(q)*px*D(rules.get('fee_bps','0'))/D('10000')
                    self.assertEqual(row['fill_fee'],charge)
                    (buys if q > 0 else sells).append(abs(q)*px)
                    charges.append(charge); positions.append(q); gross.append(-q*D(raw))
                    costs.append(abs(q)*D(raw)*rate)
                cash = D('1000')-sum(buys)+sum(sells)-sum(charges)
                self.assertEqual(row['cash'],cash)
                self.assertEqual(row['inventory'],sum(positions))
                self.assertEqual(row['equity'],cash+sum(positions)*D(raw))
                self.assertEqual(row['diagnostic_return'],row['equity']/D('1000')-1)
                self.assertEqual(row['fees'],sum(charges))
                self.assertEqual(row['implicit'],sum(costs))
                self.assertEqual(row['gross_cashflow'],sum(gross))
        return rows

    def test_literal_cases(self):
        buy, sell = order(), order('sell',decision='01:30:00')
        cases = [
            ('flat',[], [('1000','0','1000'),('1000','0','1000')],'110',{}),
            ('profit',[buy,sell],[('800','2','1000'),('1020','0','1020')],'110',{}),
            ('loss',[buy,sell],[('800','2','1000'),('980','0','980')],'90',{}),
            ('fees',[buy,sell],[('799.8','2','999.8'),('999.6','0','999.6')],'100',{'fee_bps':'10'}),
            ('primary',[buy,sell],[('799.6999','2','999.6999'),('999.4','0','999.4')],'100',{'fee_bps':'10','slippage_bps':'5'}),
            ('stress',[buy,sell],[('799.5998','2','999.5998'),('999.2','0','999.2')],'100',{'fee_bps':'10','slippage_bps':'10'}),
            ('severe',[buy,sell],[('799.1992','2','999.1992'),('998.4','0','998.4')],'100',{'fee_bps':'20','slippage_bps':'20'}),
            ('rounding',[order(quantity='2.009')],[('800','2','1000'),('800','2','1000')],'100',{'step':'0.01'}),
            ('cash',[order(quantity='11')],[('1000','0','1000'),('1000','0','1000')],'100',{}),
            ('allocation',[order(quantity='3')],[('1000','0','1000'),('1000','0','1000')],'100',{}),
            ('delayed',[order(available='01:00:01')],[('1000','0','1000'),('780','2','1000')],'110',{}),
            ('equality',[order(decision='01:00:00')],[('1000','0','1000'),('780','2','1000')],'110',{}),
            ('terminal',[buy],[('800','2','1000'),('800','2','1020')],'110',{}),
            ('expiry',[order(decision='02:00:00')],[('1000','0','1000'),('1000','0','1000')],'100',{}),
            ('oversell',[buy,order('sell','3','01:30:00')],[('800','2','1000'),('800','2','1000')],'100',{}),
            ('partial',[buy,order('sell','1','01:30:00')],[('800','2','1000'),('910','1','1020')],'110',{}),
            ('zero',[order(quantity='0.0001')],[('1000','0','1000'),('1000','0','1000')],'100',{})]
        for name, orders, expected, last, rules in cases:
            with self.subTest(case=name):
                rows=self.check_case(orders,expected,last,**rules)
                states={
                    'flat':['hold','hold'], 'cash':['rejected','hold'],
                    'allocation':['rejected','hold'], 'zero':['rejected','hold'],
                    'delayed':['hold','filled'], 'equality':['hold','filled'],
                    'terminal':['filled','hold'], 'rounding':['filled','hold'],
                    'expiry':['hold','expired'], 'oversell':['filled','rejected']}
                self.assertEqual([r['disposition'] for r in rows[1:]],states.get(name,['filled','filled']))
                literal_costs={'fees':('0.2','0.4','0','0'),
                    'primary':('0.2001','0.4','0.1','0.2'),
                    'stress':('0.2002','0.4','0.2','0.4'),
                    'severe':('0.4008','0.8','0.4','0.8')}
                costs=literal_costs.get(name,('0','0','0','0'))
                self.assertEqual((rows[1]['fees'],rows[2]['fees'],rows[1]['implicit'],rows[2]['implicit']),tuple(map(D,costs)))
                self.assertEqual(rows[2]['expiries'],orders if name=='expiry' else [])

    def test_reasons_and_causality(self):
        for q, reason in [('11','insufficient_cash'),('3','allocation'),('0.0001','zero_quantity')]:
            self.assertEqual(run(bars(),[order(quantity=q)])[1]['reason'],reason)
        self.assertEqual(run(bars(),[order(),order(decision='01:30:00')])[2]['reason'],'existing_position')
        self.assertEqual(run(bars(),[order(),order('sell','3','01:30:00')])[2]['reason'],'inventory')
        self.assertEqual(run(bars(),[order(decision='02:00:00')])[2]['disposition'],'expired')
        self.assertEqual(run(bars(),[order(quantity='2.009')],step='0.01')[1]['unused_quantity'],D('.009'))
        self.assertEqual(run(bars('1'),[order()])[:2],run(bars('999'),[order()])[:2])
        before=getcontext().copy();run(bars(),[order()]);self.assertEqual(str(before),str(getcontext()))

    def test_invalid_inputs(self):
        b=bars()
        for invalid in [[],[b[0],b[1],b[1]],[b[0],b[2],b[1]],[b[0],b[2]]]:
            for orders in [[],[order()]]:
                with self.assertRaises(InputError):run(invalid,orders)
        for value in ['0','-1','NaN','Infinity',100.0]:
            with self.assertRaises(InputError):run([(b[0][0],value)]+b[1:],[])
        for value in ['2020-01-01T00:00:00','2020-01-01T00:00:00+00:00','2020-02-30T00:00:00Z']:
            with self.assertRaises(InputError):run([(value,'100')]+b[1:],[])
        for orders in [[order(quantity='-1')],[order(available='00:00:00')],[order(decision='03:00:00')],
                       [order(available='03:00:00')],[order(),order(decision='00:40:00')],
                       [order(),order()],[order(decision='01:30:00'),order()]]:
            with self.assertRaises(InputError):run(b,orders)
        for kwargs in [{'step':'0'},{'step':'-1'},{'fee_bps':'-1'},{'fee_bps':'101'}, {'slippage_bps':'101'}]:
            with self.assertRaises(InputError):run(b,[],**kwargs)
        early=order();early['decision']=early['available']='2019-12-31T23:59:59Z'
        with self.assertRaises(InputError):run(b,[early])

    def test_rounding_boundary_and_caller_context(self):
        quantity='1.'+'9'*54
        row=run(bars(),[order(quantity=quantity)],step='1')[1]
        self.assertEqual(row['quantity'],D('1'))
        self.assertGreaterEqual(row['unused_quantity'],0)
        expected=run(bars(),[order(quantity=quantity)],step='1')
        with localcontext() as ctx:
            ctx.prec=6
            ctx.traps[Inexact]=True
            self.assertEqual(run(bars(),[order(quantity=quantity)],step='1'),expected)


if __name__ == '__main__':
    unittest.main()
