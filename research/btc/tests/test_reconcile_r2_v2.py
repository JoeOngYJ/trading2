import copy
import hashlib
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from decimal import Decimal as D
from research.btc.reconcile_r2_v2 import SCENARIOS, LOW, HIGH, decode, gate, replay, close, checked_bytes


def fixture():
    rows=[]
    for s in SCENARIOS:
        for n in range(67):
            rows.append(dict(scenario_id=s,signal_ms=D(LOW+n*600000),entry_ms=D(LOW+n*600000),exit_ms=D(LOW+n*600000+300000),
                quantity=D('1'),entry_fill=D('100'),exit_fill=D('100'),entry_reference=D('100'),exit_reference=D('100'),
                cash_before=D('1000'),remaining_cash=D('900'),cash_after=D('1000'),pnl_quote=D('0')))
    return rows


class R2Tests(unittest.TestCase):
    def test_replay_and_corruption(self):
        rows=fixture();self.assertEqual(replay(rows)['status'],'reconciled')
        rows[0]['cash_after']+=D('.01');self.assertEqual(replay(rows)['status'],'discrepancy')
        rows=fixture();rows[0]['quantity']=D('11');result=replay(rows)
        self.assertEqual(result['status'],'discrepancy')
        self.assertEqual(set(result['scenarios']),set(SCENARIOS))
        self.assertEqual(result['scenarios'][SCENARIOS[0]]['status'],'accounting_or_oracle_failure')
        self.assertTrue(result['scenarios'][SCENARIOS[1]]['passed'])

    def test_gates(self):
        for key,value in [('scenario_id','bad'),('entry_ms',D(LOW-1)),('exit_ms',D(LOW-1000)),('quantity',D('-1')),
                          ('exit_ms',D(HIGH)),('entry_ms',D(LOW)+D('.1')),('exit_ms',D(LOW+1)),('cash_before',D('-1'))]:
            r=fixture();r[0][key]=value
            with self.assertRaises(ValueError):gate(r)
        r=fixture();del r[0]['quantity']
        with self.assertRaises(ValueError):gate(r)
        with self.assertRaises(ValueError):gate(fixture()[:-1])
        r=fixture();r[0]['scenario_id']=SCENARIOS[1]
        with self.assertRaises(ValueError):gate(r)
        r=fixture();r[1]['signal_ms']=r[1]['entry_ms']=r[0]['entry_ms']
        with self.assertRaises(ValueError):gate(r)
        r=fixture();r[0]['quantity']=D('0.0000000000000000000000000001')
        with patch('research.btc.reconcile_r2_v2.account',side_effect=AssertionError('must not account')):
            self.assertEqual(replay(r)['status'],'blocked_numeric_compatibility')
        for raw in ['{"x":1,"x":2}','{"x":NaN}']:
            with self.assertRaises(ValueError):decode(raw)
        self.assertEqual(decode('{"x":0.00000000000001}')['x'],D('0.00000000000001'))

    def test_checksum(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with self.assertRaises(ValueError):checked_bytes(Path(tmp.name),'bad')
            digest=hashlib.sha256(b'').hexdigest()
            with self.assertRaises(ValueError):checked_bytes(Path(tmp.name),digest,1)
            with tempfile.TemporaryDirectory() as directory:
                link=Path(directory)/'link';link.symlink_to(tmp.name)
                with self.assertRaises(ValueError):checked_bytes(link,digest,0)

    def test_float_tolerance(self):
        for price in (100.,1000.,60000.,100000.):
            for side in (.0015,.002,.004):
                from fractions import Fraction as F
                cash=1000.
                exact_cash=F(1000)
                for _ in range(1000):
                    budget=cash*.1;p=price*(1+side);q=budget/p;exit=price*(1-side)
                    after=cash-budget+q*exit
                    before=exact_cash
                    remaining=before-F(str(q))*F(str(p))
                    exact_cash=remaining+F(str(q))*F(str(exit))
                    for exact,stored in [(before,cash),(remaining,cash-budget),(exact_cash,after),(exact_cash-before,after-cash)]:
                        self.assertTrue(close(exact,D(str(stored))))
                        self.assertFalse(close(exact+F('.01'),D(str(stored))))
                    cash=after


if __name__=='__main__':unittest.main()
