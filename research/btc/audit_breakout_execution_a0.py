"""Source-only synthetic counterexamples; never opens historical inputs."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from trading_platform.research_breakout import resolve_exit


def run():
    def bar(n,open=100,low=99,close=100,segment=1):
        return SimpleNamespace(open_ms=n*300000,open=open,low=low,close=close,segment=segment)
    a=[bar(0),bar(1,open=110,low=95,close=108),bar(2,open=108,low=100,close=108)]
    b=[bar(0,close=105)]
    same=[bar(0),bar(1,close=105),bar(2,close=110)]
    changed=[bar(0),bar(1,close=105),bar(2,close=110,segment=2)]
    observed_a=resolve_exit(a,0,{1:'exit_channel'},.04,14)
    observed_b=resolve_exit(b,0,{},.04,14)
    observed_c=[resolve_exit(same,0,{},.04,14),resolve_exit(changed,0,{},.04,14)]
    assert observed_a==(1,96.,'protective_stop')
    assert observed_b==(0,105,'source_segment_end')
    assert observed_c==[(2,110,'source_segment_end'),(1,105,'source_segment_end')]
    path=Path('src/trading_platform/research_breakout.py')
    return dict(identity='btc-breakout-execution-source-audit-a0-v1',synthetic_only=True,
                source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                scheduled_open_exit=dict(observed=observed_a,chronological_reference_price=110),
                close_exit=dict(observed=observed_b,recorded_exit_ms=0,close_available_ms=300000),
                segment_future_dependence=dict(unchanged_future=observed_c[0],changed_future=observed_c[1]),
                outcome='execution_chronology_and_boundary_findings_confirmed',actionable_arm_id='no_trade')


if __name__=='__main__':print(json.dumps(run(),indent=2,sort_keys=True))
