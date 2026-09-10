from __future__ import annotations
import copy, importlib.util, json, unittest

S=importlib.util.spec_from_file_location("e0v10","scripts/validate_btc_unified_engine_e0_v10.py")
M=importlib.util.module_from_spec(S); assert S.loader; S.loader.exec_module(M)

class E0V10Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.c,cls.i,cls.o=M.load(M.CONTRACT),M.load(M.INTERFACE),M.load(M.OBLIGATIONS)
 def bad(self,c=None,i=None,o=None):
  with self.assertRaises(M.ValidationError): M.validate_semantics(c or self.c,i or self.i,o or self.o)
 def test_semantics_pass(self): M.validate_semantics(self.c,self.i,self.o)
 def test_duplicate_and_nonfinite_fail(self):
  with self.assertRaises(M.ValidationError): json.loads('{"x":1,"x":2}',object_pairs_hook=M._pairs)
  with self.assertRaises(M.ValidationError): json.loads('{"x":NaN}',parse_constant=M._constant)
 def test_safe_paths(self):
  for x in ('','/x','../x','a/../x','a//x','a\\x'):
   with self.subTest(x=x),self.assertRaises(M.ValidationError): M.safe_path(x)
 def test_real_exact_utc(self):
  self.assertTrue(M.valid_utc('2025-12-31T23:59:59.123456Z'))
  for x in ('2025-12-31T23:59:59Z','2025-12-31T23:59:59.1Z','2025-02-30T00:00:00.000000Z','2025-01-01T24:00:00.000000Z','2025-01-01T00:00:00.000000+00:00'):
   with self.subTest(x=x): self.assertFalse(M.valid_utc(x))
 def test_future_path_variants(self):
  values=['src/trading_platform/btc-backtest-authorities-c0-v1.py','src/trading_platform/btc_backtest_authorities_c1_v1.py','src/trading_platform/btc_unified_backtest_ledger_c1.py','src/trading_platform/btc-backtest-candle-adapter-c2-v1.py','src/trading_platform/btc_backtest_l2_c3.py','src/trading_platform/btc-backtest-pair-coordinator-c4-v1.py','research/btc/contracts/btc-backtest-risk-c5-v1.json','research/btc/candidates/btc-backtest-reporting-c6-v1/x','research/btc/contracts/btc-unified-backtest-engine-c1-v1.json','research/btc/contracts/unified_backtest_engine_e1_v15.json','research/btc/candidates/unified-backtest-engine-e2/x','research/btc/oracles/c6/answer.json']
  for x in values:
   with self.subTest(x=x): self.assertTrue(M.forbidden_future_path(x))
  self.assertFalse(M.forbidden_future_path('research/btc/invalid/btc-backtest-ledger-c1.py'))
 def test_public_economic_argument_fails_semantically(self):
  x=copy.deepcopy(self.i);x['supported_public_api']['arguments'].append({'consumers':['C0'],'name':'price','nullable':False,'producer':'caller','type':'NonNegativeInteger'});self.bad(i=x)
 def test_compatibility_mutation_fails_semantically(self):
  x=copy.deepcopy(self.i);x['compatibility']['scenario_modes'][0]['scenario_id']='book-taker-primary-250ms-v1';self.bad(i=x)
 def test_digest_domain_mutation_fails_semantically(self):
  x=copy.deepcopy(self.i);x['digest_domains']['RunContext.run_context_digest']='whole_record';self.bad(i=x)
 def test_type_mutation_fails_semantically(self):
  x=copy.deepcopy(self.i);x['types']['RunContext']['fields'][0]['type']='NonEmptyIdentifier';self.bad(i=x)
 def test_nullability_mutation_fails_semantically(self):
  x=copy.deepcopy(self.i);x['types']['RunSpec']['fields'][6]['nullable']=False;self.bad(i=x)
 def test_producer_mutation_fails_semantically(self):
  x=copy.deepcopy(self.i);x['types']['C0Manifest']['fields'][0]['producer']='repository';self.bad(i=x)
 def test_consumer_mutation_fails_semantically(self):
  x=copy.deepcopy(self.i);x['types']['RunContext']['fields'][0]['consumers']=['C0'];self.bad(i=x)
 def test_immutability_mutation_fails_semantically(self):
  x=copy.deepcopy(self.i);x['types']['RunContext']['constraints'].remove('recursively_immutable');self.bad(i=x)
 def test_obligation_pointer_owner_probe_mutations_fail_semantically(self):
  for key,value in [('source_pointer','/data_contract'),('owner','C1'),('probe_id','P14')]:
   x=copy.deepcopy(self.o);x['c0_owned_obligations'][0][key]=value
   with self.subTest(key=key): self.bad(o=x)
 def test_finding_gate_and_boundary_mutations_fail_semantically(self):
  for mutate in ('finding','gate','boundary'):
   x=copy.deepcopy(self.c)
   if mutate=='finding': x['failure_findings'][0]['probe_id']='P02'
   elif mutate=='gate': x['qualification_gates'][0]='changed'
   else: x['future_component_boundary']['C3']='implemented'
   with self.subTest(mutate=mutate): self.bad(c=x)
 def test_review_descriptor_mutation_fails_semantically(self):
  x=copy.deepcopy(self.c);x['required_review_artifacts'][1]['reviewer_id']='Jason';self.bad(c=x)
 def test_bundle_path_role_swap_fails(self):
  b=M.load(M.BUNDLE);x=copy.deepcopy(b);x['files'][0],x['files'][1]=x['files'][1],x['files'][0]
  with self.assertRaises(M.ValidationError): M.validate_bundle(self.c,x)

if __name__=='__main__': unittest.main()
