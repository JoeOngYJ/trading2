"""Create an isolated operational continuation; no market input or sockets."""
from pathlib import Path
import hashlib,json,shutil
from datetime import datetime,timezone
ROOT=Path('/data/Trading')
OLD=ROOT/'research/btc/review_runs/prospective-liquidation-launch-qualification-20260912-v1'
RUN=ROOT/'research/btc/review_runs/prospective-liquidation-final-launch-20260912-v1'
RUN.mkdir(exist_ok=False)
for directory in ('documents','candidate','clock','health','durability','logs','pilot','metadata'):(RUN/directory).mkdir()
authorities=['AGENTS.md','docs/STRATEGY_RESEARCH_STANDARD.md','docs/RETAIL_TRADING_MANDATE.md','docs/EXECUTION_COST_MODEL.md','docs/RESEARCH_TRACKER.md','research/btc/CODEX_REVIEW_STATUS.md','research/PROSPECTIVE_LIQUIDATION_COLLECTION_PLAN.md','research/PROSPECTIVE_LIQUIDATION_LAUNCH_QUALIFICATION.md','research/ALPHA_DISCOVERY_PHASE2.md','research/btc/review_runs/prospective-and-alpha-phase2-20260912-v1/proposed_stopping_rule.json',str((OLD/'stage_manifest.json').relative_to(ROOT))]
records=[]
for name in authorities:
 p=ROOT/name;raw=p.read_bytes();out=RUN/'documents'/(name.replace('/','__')+'.before');out.write_bytes(raw)
 records.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'copy':str(out.relative_to(RUN))})
for directory in ('candidate','clock','health'):
 for p in (OLD/'attempt2'/directory).glob('*.py'):
  if p.name.startswith('verify_retained'):continue
  target=RUN/directory/p.name;shutil.copyfile(p,target)
for p in (OLD/'durability').glob('*.py'):shutil.copyfile(p,RUN/'durability'/p.name)
manifest={'run_id':RUN.name,'created_utc':datetime.now(timezone.utc).isoformat(),'authorities':records,
 'prior_run':str(OLD),'prior_disposition_preserved':'B. OPERATIONAL BLOCKER REMAINS','repository_git_identity':'UNKNOWN',
 'scope':'versioned timing uncertainty, sealed compression, actual backup qualification and excluded bounded pilot only',
 'production_launch_authorized':False,'outcomes_authorized':False}
(RUN/'authority_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
copies=[]
for directory in ('candidate','clock','health','durability'):
 for p in (RUN/directory).glob('*.py'):copies.append({'path':str(p.relative_to(RUN)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size})
(RUN/'baseline_sources.json').write_text(json.dumps(copies,indent=2)+'\n')
status=ROOT/'research/btc/CODEX_REVIEW_STATUS.md'
status.write_text('# Codex persistent review status\n\nStatus: **IN_PROGRESS**\nStage: final prospective launch operational qualification.\nRun: `'+RUN.name+'`.\nPrior accepted B report and source evidence preserved. New isolated timing protocol, compression and backup qualification only. No alpha or protected-data access; no production launch. Backup destination path requested and pending.\n\n---\n\n'+status.read_text())
print(json.dumps({'status':'INITIALIZED','run':str(RUN),'authorities_preserved':len(records),'sources_copied':len(copies)}))
