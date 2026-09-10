#!/usr/bin/env python3
"""Independent, fail-closed validation for E0-v11's C0-only design."""
from __future__ import annotations

import argparse, hashlib, json, math, re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ID = "btc-unified-backtest-engine-e0-v11-c0-authority-boundary"
CONTRACT = ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v11-c0-authority-boundary.json"
INTERFACE = ROOT / "research/btc/specs/btc-backtest-c0-authority-interface-e0-v11.json"
OBLIGATIONS = ROOT / "research/btc/specs/btc-backtest-c0-inherited-obligations-e0-v11.json"
BUNDLE = ROOT / "research/btc/candidates/unified-backtest-engine-e0-v11-c0-design/pre-review-bundle-manifest.json"
REVIEWS = [
    ROOT / "research/btc/reviews/btc-unified-backtest-engine-e0-v11-boundary-review.json",
    ROOT / "research/btc/reviews/btc-unified-backtest-engine-e0-v11-validator-review.json",
]

EXPECTED_FINDINGS = [{"finding_id":f"C0F{i:02d}","owner":"C0","probe_id":f"P{i:02d}"} for i in range(1,15)]
EXPECTED_CONSUMERS = {"caller","repository",*[f"C{i}" for i in range(7)]}
EXPECTED_COMPATIBILITY = {
 "allowed_mandate_adapter_modes":[
  {"adapter_id":"binance_spot","execution_mode":"candle_taker","mandate_id":"retail-btc-spot-v2"},
  {"adapter_id":"binance_spot","execution_mode":"book_taker","mandate_id":"retail-btc-spot-v2"},
  {"adapter_id":"binance_usdm_linear_perpetual","execution_mode":"candle_taker","mandate_id":"retail-btc-directional-perpetual-research-v1"},
  {"adapter_id":"binance_usdm_linear_perpetual","execution_mode":"book_taker","mandate_id":"retail-btc-directional-perpetual-research-v1"},
  {"adapter_id":"binance_spot_usdm_pair","execution_mode":"candle_taker","mandate_id":"retail-btc-delta-neutral-research-v1"},
  {"adapter_id":"binance_spot_usdm_pair","execution_mode":"book_taker","mandate_id":"retail-btc-delta-neutral-research-v1"}],
 "mandate_authorities":[
  {"mandate_id":"retail-btc-spot-v2","path":"config/retail_mandate.json","sha256":"7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041","size_bytes":2960},
  {"mandate_id":"retail-btc-directional-perpetual-research-v1","path":"config/mandates/retail-btc-directional-perpetual-research-v1.json","sha256":"1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d","size_bytes":1619},
  {"mandate_id":"retail-btc-delta-neutral-research-v1","path":"config/mandates/retail-btc-delta-neutral-research-v1.json","sha256":"d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba","size_bytes":2268}],
 "scenario_authority":{"path":"config/execution_scenarios.json","role":"scenario_registry","sha256":"a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36","size_bytes":2922},
 "scenario_modes":[
  {"execution_mode":"candle_taker","latency_ms":0,"row_sha256":"6713818bafe96982b63f3d00eed1e2971ea9be26de53909d1bb3bc5a3c78c1d4","scenario_id":"candle-fees-only-diagnostic-v1"},
  {"execution_mode":"candle_taker","latency_ms":0,"row_sha256":"7404a38d9b47f52cce3e35739d5d0711f8fc68776f3073cadbb9d29e5361be73","scenario_id":"candle-primary-30bps-rt-v1"},
  {"execution_mode":"candle_taker","latency_ms":0,"row_sha256":"f7dd43b2aa3c02e2a8e643e269ca481ece0b2c57a90a04a7417fc49e7a7c16f2","scenario_id":"candle-stress-40bps-rt-v1"},
  {"execution_mode":"candle_taker","latency_ms":0,"row_sha256":"262ecedfb88746ab40f30d9062c9bf4749cf966860d2e12ef231a6944c0f8443","scenario_id":"candle-severe-80bps-rt-v1"},
  {"execution_mode":"book_taker","latency_ms":250,"row_sha256":"e05e20661522d1a81656dbdb783602a4008fc6e3949c9d2f583d5921243193f4","scenario_id":"book-taker-primary-250ms-v1"}]}
EXPECTED_DIGEST_DOMAINS = {
 "C0Manifest.manifest_digest":"lowercase_SHA256_of_UTF8_canonical_JSON_of_complete_C0Manifest_after_removing_only_manifest_digest",
 "RunContext.run_context_digest":"lowercase_SHA256_of_UTF8_canonical_JSON_of_complete_RunContext_after_removing_only_run_context_digest",
 "RunSpec.run_spec_digest":"lowercase_SHA256_of_UTF8_canonical_JSON_of_complete_RunSpec_after_removing_only_run_spec_digest",
 "RunSpecRegistry.registry_digest":"lowercase_SHA256_of_UTF8_canonical_JSON_of_complete_RunSpecRegistry_after_removing_only_registry_digest"}
EXPECTED_RECORD_CONSTRAINTS = {
 "AuthorityRef":["recursively_immutable"], "C0FileRef":["recursively_immutable"],
 "C0Manifest":["recursively_immutable","component_id_is_C0","contains_exactly_one_file_for_each_C0FileRole","files_unique_by_path_and_role","authorities_are_exactly_one_each_of_c0_design_contract_and_inherited_e0_v1_v2_v3_v4_contract_roles","authorities_unique_by_path_and_role","has_no_dependency_acceptances","manifest_digest_matches_declared_digest_domain"],
 "RunContext":["recursively_immutable","partition_start_strictly_before_partition_end","exact_projection_of_verified_RunSpec_RunSpecRegistry_and_C0Manifest","all_RunSpec_authority_paths_roles_sizes_and_digests_are_preserved","run_context_digest_matches_declared_digest_domain"],
 "RunSpec":["recursively_immutable","run_spec_digest_matches_declared_digest_domain","mandate_id_maps_to_exact_mandate_authority","scenario_id_maps_to_exact_scenario_authority_row_mode_latency","every_AuthorityRef_field_has_its_field_named_role","selection_is_in_allowed_mandate_adapter_modes","partition_start_strictly_before_partition_end"],
 "RunSpecRegistry":["recursively_immutable","run_spec_ids_are_unique","registry_digest_matches_declared_digest_domain","unknown_run_spec_id_rejected"]}
EXPECTED_FUTURE_BOUNDARY={"C0":"authority_manifest_and_RunContext_only_design_no_implementation","C1":"deferred_unresolved_accounting_ledger","C2":"deferred_unresolved_candle_execution","C3":"deferred_unresolved_L2_execution","C4":"deferred_unresolved_atomic_pair_execution","C5":"deferred_unresolved_controls","C6":"deferred_unresolved_integration_and_reporting"}
EXPECTED_GATES=["canonical_JSON_rejects_duplicate_keys_and_nonfinite_numbers","all_authority_and_design_bindings_verify","exact_public_API_types_compatibility_and_digest_domains_verify","fields_have_exact_type_nullability_producer_and_explicit_consumers","exact_nested_C0_obligation_pointer_value_owner_probe_mapping_verifies","failure_findings_have_exact_unique_owner_probe_mapping","complete_bundle_exact_path_role_size_digest_mapping_verifies","semantic_mutations_are_rejected_without_relying_on_document_digest_pinning","all_planned_hyphenated_and_underscored_C0_C6_E1_v15_E2_paths_fail","two_separate_bound_independent_review_artifacts_pass","no_implementation_or_economic_evidence_was_created_or_opened","only_no_trade_is_actionable"]
EXPECTED_REVIEW_FINDINGS=["scope_is_C0_only_and_downstream_is_unresolved","public_API_and_selection_compatibility_are_exact","interface_types_immutability_and_digest_domains_are_complete","C0_obligation_subset_uses_exact_nested_pointers_without_downstream_closure","finding_owner_probe_mapping_is_exact","bundle_path_role_size_digest_and_semantic_mutations_are_bound","premature_C0_C6_and_later_stage_paths_fail_closed","no_prohibited_data_service_action_or_self_certified_review"]
EXPECTED_C0_CLAIM={"input":"run_spec_id_only","output":"recursively_immutable_identity_and_lineage_only_RunContext","security_model":"supported_public_API_under_ordinary_offline_Python_execution_not_hostile_code_security"}
EXPECTED_SCOPE="offline_synthetic_design_qualification_only"
EXPECTED_PROHIBITED=["any_C0_C6_implementation_before_E0_v11_pass","E1_v15_or_E2","historical_market_data_or_strategy_evaluation","sealed_2026_or_partial_OB0_data","credentials_network_exchange_database_NATS_Freqtrade_or_protected_soak_access","paper_or_live_trading","any_actionable_arm_other_than_no_trade"]
EXPECTED_OBLIGATION_TUPLES=[
 ("C0O01","P03","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/bound_authorities","c38311c021efe5a61cf81906dcb2efc4bf544ff6e67eb449afbc7c0f7a3f7d78"),
 ("C0O02","P01","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/data_contract/duplicate_policy","67f347f593a7a1eb3b530a30595d5bb67bb9d8cb375cc1566205df6d4c0131f4"),
 ("C0O03","P06","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/data_contract/timestamp","4392fa070fc12f198cbea388f87c543a9421de80e33f5287fe761cb122703f2a"),
 ("C0O04","P03","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/data_contract/validation/5","c17c13e49bd78a5c57be9c9ad782dedc7542e3fd73cc08b2b88ed02aa988a3e5"),
 ("C0O05","P07","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/execution_adapter_capabilities/unsupported_capability","6586ac1f1de5b7417aabb4e51e20a96cc3ac391bf216c4a61150dc3002ec8161"),
 ("C0O06","P03","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/serialization_and_digest_contract/artifact_file_sha256","2163435a32c642792bef04afeb79ecdd8fd40320e534c64196b972c19afa3cce"),
 ("C0O07","P01","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/serialization_and_digest_contract/canonical_JSON","1c1fd2fa6c226f126b702331828391b848be08d4dbae7981ca59cd9793ade2b7"),
 ("C0O08","P09","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/serialization_and_digest_contract/digest_domain","d8f81b7f06725217cc334ea1537a31d4b04fa12fd4c222ac081b1925d20ceb76"),
 ("C0O09","P01","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/serialization_and_digest_contract/duplicate_object_keys","a8837e1822384c56931b35accb26ac7a18c433c2dd51caea2afacca53608d3a1"),
 ("C0O10","P03","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/serialization_and_digest_contract/manifest_entry","6a59b833c5be1911dfb5f567683bc08063ae71c2edfa5e5f8dd66a314314fd8a"),
 ("C0O11","P06","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/serialization_and_digest_contract/timestamp_encoding","543d5f09d51565d64cdacfae7ddff912db005241c0362a3470dc8bfdc06e3e1a"),
 ("C0O12","P05","research/btc/contracts/btc-unified-backtest-engine-e0-v1.json","/action_boundary","cdbf7f41d7d5fbc3eb4d87257c5e992b4deb9cea6a06f1c4cdd27d459eba45f7"),
 ("C0O13","P12","research/btc/contracts/btc-unified-backtest-engine-e0-v2.json","/predecessor","b718997dd9559787e3bc8f57647f6ed5adb875684edcc9847629b4b3dca44946"),
 ("C0O14","P12","research/btc/contracts/btc-unified-backtest-engine-e0-v3-pair-close.json","/inheritance","3c489ca2047d79d9261116515484e55a7d0ab38deb218634b54b224fdad53827"),
 ("C0O15","P05","research/btc/contracts/btc-unified-backtest-engine-e0-v3-pair-close.json","/action_boundary","a526f725dfe2e5ca9cb1aeee72432a9b44f06c431db52ca1f31f0e00cc5a8283")]

def fs(type_name, producer, consumers, nullable=False): return (type_name,nullable,producer,tuple(consumers))
ALL = [f"C{i}" for i in range(7)]
EXPECTED_FIELDS = {
 "AuthorityRef":{"path":fs("SafeRelativePath","repository",["C0"]),"sha256":fs("Sha256Hex","repository",["C0"]),"size_bytes":fs("NonNegativeInteger","repository",["C0"]),"role":fs("AuthorityRole","repository",["C0"])},
 "C0FileRef":{"path":fs("SafeRelativePath","C0",["C0"]),"sha256":fs("Sha256Hex","C0",["C0"]),"size_bytes":fs("NonNegativeInteger","C0",["C0"]),"role":fs("C0FileRole","C0",["C0"])},
 "C0Manifest":{"schema_version":fs("NonEmptyIdentifier","C0",["C0"]),"experiment_id":fs("NonEmptyIdentifier","C0",["C0"]),"component_id":fs("C0Literal","C0",["C0"]),"files":fs("List[C0FileRef]","C0",["C0"]),"authorities":fs("List[AuthorityRef]","C0",["C0"]),"created_at":fs("UtcTimestamp","C0",["C0"]),"manifest_digest":fs("Sha256Hex","C0",["C0"])},
 "RunContext":{name:fs(t,"C0",ALL,n) for name,t,n in [
  ("run_context_digest","Sha256Hex",False),("run_spec_id","NonEmptyIdentifier",False),("run_spec_digest","Sha256Hex",False),("run_spec_registry","AuthorityRef",False),("run_spec_registry_digest","Sha256Hex",False),("mandate_id","MandateId",False),("mandate","AuthorityRef",False),("adapter_id","AdapterId",False),("execution_mode","ExecutionMode",False),("scenario_id","ScenarioId",False),("scenario_row_digest","Sha256Hex",False),("latency_ms","LatencyMilliseconds",False),("source_manifest","AuthorityRef",False),("rule_manifest","AuthorityRef",False),("margin_manifest","AuthorityRef",False),("settings","AuthorityRef",False),("scenario","AuthorityRef",False),("implementation_manifest_digest","Sha256Hex",False),("partition_start","UtcTimestamp",False),("partition_end","UtcTimestamp",False)]},
 "RunSpec":{name:fs(t,"repository",["C0"],n) for name,t,n in [
  ("run_spec_id","NonEmptyIdentifier",False),("run_spec_digest","Sha256Hex",False),("mandate_id","MandateId",False),("mandate","AuthorityRef",False),("adapter_id","AdapterId",False),("execution_mode","ExecutionMode",False),("scenario_id","ScenarioId",False),("scenario_row_digest","Sha256Hex",False),("latency_ms","LatencyMilliseconds",False),("scenario","AuthorityRef",False),("source_manifest","AuthorityRef",False),("rule_manifest","AuthorityRef",False),("margin_manifest","AuthorityRef",False),("settings","AuthorityRef",False),("implementation_manifest","C0Manifest",False),("partition_start","UtcTimestamp",False),("partition_end","UtcTimestamp",False)]},
 "RunSpecRegistry":{name:fs(t,"repository",["C0"],False) for name,t in [("schema_version","NonEmptyIdentifier"),("registry_id","NonEmptyIdentifier"),("run_specs","List[RunSpec]"),("registry_digest","Sha256Hex")]}}
EXPECTED_PRIMITIVES = {
 "AdapterId":{"kind":"enum","values":["binance_spot","binance_usdm_linear_perpetual","binance_spot_usdm_pair"]},
 "AuthorityRole":{"kind":"enum","values":["mandate","scenario_registry","source_manifest","rule_manifest","margin_manifest","settings","run_spec_registry","c0_design_contract","inherited_e0_v1_contract","inherited_e0_v2_contract","inherited_e0_v3_contract","inherited_e0_v4_contract"]},
 "C0FileRole":{"kind":"enum","values":["c0_module","c0_contract","c0_validator","c0_tests"]},
 "C0Literal":{"kind":"literal","value":"C0"},
 "ExecutionMode":{"kind":"enum","values":["candle_taker","book_taker"]},
 "LatencyMilliseconds":{"kind":"integer","maximum":86400000,"minimum":0},
 "MandateId":{"kind":"enum","values":["retail-btc-spot-v2","retail-btc-directional-perpetual-research-v1","retail-btc-delta-neutral-research-v1"]},
 "NonEmptyIdentifier":{"kind":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"},
 "NonNegativeInteger":{"kind":"integer","minimum":0},
 "SafeRelativePath":{"constraints":["non_empty","POSIX_normalized","not_absolute","no_parent_segment","resolves_within_repository_root"],"kind":"string"},
 "ScenarioId":{"kind":"enum","values":["candle-fees-only-diagnostic-v1","candle-primary-30bps-rt-v1","candle-stress-40bps-rt-v1","candle-severe-80bps-rt-v1","book-taker-primary-250ms-v1"]},
 "Sha256Hex":{"kind":"string","pattern":"^[0-9a-f]{64}$"},
 "UtcTimestamp":{"constraints":["real_Gregorian_calendar_and_clock_value"],"kind":"string","pattern":"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}Z$"}}

class ValidationError(ValueError): pass
def _constant(v): raise ValidationError(f"non-finite JSON constant: {v}")
def _pairs(pairs):
 d={}
 for k,v in pairs:
  if k in d: raise ValidationError(f"duplicate JSON key: {k}")
  d[k]=v
 return d
def load(path): return json.loads(path.read_text(),object_pairs_hook=_pairs,parse_constant=_constant)
def canonical(v):
 def walk(x):
  if isinstance(x,float) and not math.isfinite(x): raise ValidationError("non-finite")
  if isinstance(x,dict):
   for y in x.values(): walk(y)
  elif isinstance(x,list):
   for y in x: walk(y)
 walk(v); return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def digest_bytes(b): return hashlib.sha256(b).hexdigest()
def digest_file(p): return digest_bytes(p.read_bytes())
def safe_path(s):
 if not isinstance(s,str) or not s: raise ValidationError("empty path")
 q=PurePosixPath(s)
 if q.is_absolute() or ".." in q.parts or str(q)!=s or "\\" in s: raise ValidationError(f"unsafe path {s}")
 p=(ROOT/s).resolve()
 if ROOT!=p and ROOT not in p.parents: raise ValidationError(f"escaping path {s}")
 return p
def pointer(d,p):
 if not p.startswith('/'): raise ValidationError("bad pointer")
 for token in p[1:].split('/'):
  token=token.replace('~1','/').replace('~0','~'); d=d[int(token)] if isinstance(d,list) else d[token]
 return d
def valid_utc(s):
 if not isinstance(s,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",s): return False
 try: datetime.strptime(s,"%Y-%m-%dT%H:%M:%S.%fZ")
 except ValueError: return False
 return True

def validate_interface(d):
 expected_api={"arguments":[{"consumers":["C0"],"name":"run_spec_id","nullable":False,"producer":"caller","type":"NonEmptyIdentifier"}],"name":"build_run_context","return_type":"RunContext","security_claim":"deterministic_fail_closed_supported_public_API_not_hostile_Python_security"}
 if d.get("supported_public_api")!=expected_api: raise ValidationError("public API drift")
 if d.get("compatibility")!=EXPECTED_COMPATIBILITY: raise ValidationError("compatibility drift")
 for row in d["compatibility"]["mandate_authorities"]:
  path=safe_path(row["path"])
  if not path.is_file() or path.stat().st_size!=row["size_bytes"] or digest_file(path)!=row["sha256"]: raise ValidationError("mandate authority mapping drift")
 scenario_authority=d["compatibility"]["scenario_authority"]; scenario_path=safe_path(scenario_authority["path"])
 if scenario_path.stat().st_size!=scenario_authority["size_bytes"] or digest_file(scenario_path)!=scenario_authority["sha256"]: raise ValidationError("scenario authority mapping drift")
 rows={row["scenario_id"]:row for row in load(scenario_path)["scenarios"]}
 for selected in d["compatibility"]["scenario_modes"]:
  source=rows.get(selected["scenario_id"])
  if source is None or source["mode"]!=selected["execution_mode"] or source["latency_ms"]!=selected["latency_ms"] or digest_bytes(canonical(source))!=selected["row_sha256"]: raise ValidationError("scenario row mapping drift")
 if d.get("digest_domains")!=EXPECTED_DIGEST_DOMAINS: raise ValidationError("digest domain drift")
 types=d.get("types",{})
 if set(types)!=set(EXPECTED_FIELDS)|set(EXPECTED_PRIMITIVES): raise ValidationError("type set drift")
 for name,expected in EXPECTED_PRIMITIVES.items():
  if types[name]!=expected: raise ValidationError(f"primitive drift {name}")
 for name,expected in EXPECTED_FIELDS.items():
  definition=types[name]
  if definition.get("kind")!="record" or definition.get("constraints")!=EXPECTED_RECORD_CONSTRAINTS[name]: raise ValidationError(f"record constraints drift {name}")
  actual={}
  for f in definition.get("fields",[]):
   if set(f)!={"name","type","nullable","producer","consumers"}: raise ValidationError(f"incomplete field {name}")
   if f["producer"] not in EXPECTED_CONSUMERS or not f["consumers"] or not set(f["consumers"])<=EXPECTED_CONSUMERS: raise ValidationError(f"ownership drift {name}.{f['name']}")
   actual[f["name"]]=(f["type"],f["nullable"],f["producer"],tuple(f["consumers"]))
  if actual!=expected: raise ValidationError(f"field signature drift {name}")

def validate_obligations(d):
 rows=d.get("c0_owned_obligations",[])
 actual=[(r.get("obligation_id"),r.get("probe_id"),r.get("source_path"),r.get("source_pointer"),r.get("value_sha256")) for r in rows]
 if actual!=EXPECTED_OBLIGATION_TUPLES or any(r.get("owner")!="C0" or set(r)!={"obligation_id","owner","probe_id","source_path","source_pointer","value_sha256"} for r in rows): raise ValidationError("exact obligation mapping drift")
 for r in rows:
  source=load(safe_path(r["source_path"])); got=digest_bytes(canonical(pointer(source,r["source_pointer"])))
  if got!=r.get("value_sha256"): raise ValidationError(f"obligation value drift {r['obligation_id']}")
 if [x.get("future_owner") for x in d.get("deferred_inherited_domains",[])]!=[f"C{i}" for i in range(1,7)]: raise ValidationError("deferred owners drift")
 if any(x.get("status")!="unresolved_not_closed" for x in d["deferred_inherited_domains"]): raise ValidationError("downstream improperly closed")

def validate_semantics(contract,interface,obligations):
 if any(d.get("experiment_id")!=ID for d in (contract,interface,obligations)): raise ValidationError("identity drift")
 validate_interface(interface); validate_obligations(obligations)
 if contract.get("failure_findings")!=EXPECTED_FINDINGS: raise ValidationError("finding mapping drift")
 expected_roles=[
  {"path":"research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V11_C0_AUTHORITY_PLAN.md","role":"c0_plan"},{"path":"research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V11_C0_FAILURE_MATRIX.md","role":"c0_failure_matrix"},{"path":"research/btc/specs/btc-backtest-c0-authority-interface-e0-v11.json","role":"c0_interface_spec"},{"path":"research/btc/specs/btc-backtest-c0-inherited-obligations-e0-v11.json","role":"c0_obligation_registry"},{"path":"research/btc/contracts/btc-unified-backtest-engine-e0-v11-c0-authority-boundary.json","role":"c0_contract"},{"path":"scripts/validate_btc_unified_engine_e0_v11.py","role":"c0_validator"},{"path":"research/btc/tests/test_unified_engine_e0_v11.py","role":"c0_tests"}]
 if contract.get("required_bundle_path_roles")!=expected_roles: raise ValidationError("path-role map drift")
 if contract.get("action_boundary")!={"actionable_arm_id":"no_trade","may_create_order_intent_or_signal_payload":False,"may_route_or_trade":False}: raise ValidationError("action drift")
 if contract.get("c0_claim")!=EXPECTED_C0_CLAIM or contract.get("scope")!=EXPECTED_SCOPE or contract.get("prohibited")!=EXPECTED_PROHIBITED: raise ValidationError("scope, claim, or prohibition drift")
 if contract.get("future_component_boundary")!=EXPECTED_FUTURE_BOUNDARY: raise ValidationError("future boundary drift")
 if contract.get("qualification_gates")!=EXPECTED_GATES: raise ValidationError("gate drift")
 expected_reviews=[{"path":"research/btc/reviews/btc-unified-backtest-engine-e0-v11-boundary-review.json","reviewer_id":"Jason","reviewer_role":"boundary_reviewer"},{"path":"research/btc/reviews/btc-unified-backtest-engine-e0-v11-validator-review.json","reviewer_id":"Harvey","reviewer_role":"validator_reviewer"}]
 if contract.get("required_review_artifacts")!=expected_reviews: raise ValidationError("review descriptors drift")
 if contract.get("required_review_findings")!=EXPECTED_REVIEW_FINDINGS: raise ValidationError("review findings drift")

WHITELIST={"research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V11_C0_AUTHORITY_PLAN.md","research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V11_C0_FAILURE_MATRIX.md","research/btc/specs/btc-backtest-c0-authority-interface-e0-v11.json","research/btc/specs/btc-backtest-c0-inherited-obligations-e0-v11.json","research/btc/contracts/btc-unified-backtest-engine-e0-v11-c0-authority-boundary.json","scripts/validate_btc_unified_engine_e0_v11.py","research/btc/tests/test_unified_engine_e0_v11.py","research/btc/candidates/unified-backtest-engine-e0-v11-c0-design","research/btc/candidates/unified-backtest-engine-e0-v11-c0-design/pre-review-bundle-manifest.json"}
def forbidden_future_path(s):
 if s in WHITELIST: return False
 n=s.lower().replace('_','-')
 if '/invalid/' in f'/{n}/': return False
 if 'btc' not in n: return False
 token=bool(re.search(r"(?:^|[-/])c[0-6](?:[-./]|$)",n))
 stage=bool(re.search(r"(?:^|[-/])(?:e1-v15|e2)(?:[-./]|$)",n))
 return stage or token

def validate_refs(contract):
 for key in ("bound_authorities","design_bindings"):
  rows=contract[key]
  if len({r['path'] for r in rows})!=len(rows) or len({r['role'] for r in rows})!=len(rows): raise ValidationError("duplicate reference")
  for r in rows:
   p=safe_path(r['path'])
   if not p.is_file() or digest_file(p)!=r['sha256'] or ('size_bytes' in r and p.stat().st_size!=r['size_bytes']): raise ValidationError(f"reference mismatch {r['path']}")
def validate_bundle(contract,bundle):
 if bundle.get('experiment_id')!=ID or bundle.get('status')!='frozen_pre_review': raise ValidationError('bundle identity')
 expected=contract['required_bundle_path_roles']; files=bundle.get('files',[])
 if [{"path":r.get('path'),"role":r.get('role')} for r in files]!=expected: raise ValidationError('bundle path-role mapping')
 for r in files:
  p=safe_path(r['path'])
  if not p.is_file() or p.stat().st_size!=r.get('size_bytes') or digest_file(p)!=r.get('sha256'): raise ValidationError(f"bundle mismatch {r.get('path')}")
def scan_future():
 for base in [ROOT/'src',ROOT/'scripts',ROOT/'research/btc/tests',ROOT/'research/btc/contracts',ROOT/'research/btc/candidates',ROOT/'research/btc/oracles']:
  if base.exists():
   for p in base.rglob('*'):
    rel=p.relative_to(ROOT).as_posix()
    if forbidden_future_path(rel): raise ValidationError(f"premature future path {rel}")
def validate_reviews(contract):
 bundle_hash=digest_file(BUNDLE); seen_ids=set(); seen_roles=set()
 for descriptor,path in zip(contract['required_review_artifacts'],REVIEWS):
  r=load(path)
  if r.get('experiment_id')!=ID or r.get('verdict')!='pass' or r.get('bundle_manifest_sha256')!=bundle_hash: raise ValidationError('review identity/verdict/binding')
  if r.get('reviewer_id')!=descriptor['reviewer_id'] or r.get('reviewer_role')!=descriptor['reviewer_role'] or r.get('author_role')!='independent_reviewer': raise ValidationError('reviewer identity/role')
  if r['reviewer_id'] in seen_ids or r['reviewer_role'] in seen_roles: raise ValidationError('reviews not independent')
  seen_ids.add(r['reviewer_id']); seen_roles.add(r['reviewer_role'])
  if [x.get('finding') for x in r.get('findings',[])]!=contract['required_review_findings'] or any(x.get('verdict')!='pass' for x in r['findings']): raise ValidationError('review findings')

def validate(qualification=False):
 c,i,o=load(CONTRACT),load(INTERFACE),load(OBLIGATIONS); validate_semantics(c,i,o); validate_refs(c); validate_bundle(c,load(BUNDLE)); scan_future()
 if qualification: validate_reviews(c)
 return {"actionable_arm_id":"no_trade","checks_passed":10 if qualification else 9,"experiment_id":ID,"mode":"qualification" if qualification else "preflight","status":"passed" if qualification else "frozen_pending_independent_review"}
def main():
 p=argparse.ArgumentParser();p.add_argument('--qualification',action='store_true');a=p.parse_args();print(json.dumps(validate(a.qualification),sort_keys=True,separators=(',',':')))
if __name__=='__main__': main()
