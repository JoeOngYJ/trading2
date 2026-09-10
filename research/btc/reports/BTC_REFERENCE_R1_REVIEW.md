# Independent R1-v2 synthetic accounting review

Reviewer: `/root/r1_review`, independent review agent. Date: 2026-09-08.
Disposition: PASS for `btc-reference-fill-accounting-r1-v2` synthetic explicit-fill bookkeeping only.

Reviewed frozen contract, literal expectations, engine and tests. Both input references match
`contracts/btc-reference-r1-v2-input-manifest.json`; its SHA-256 is
`08e6e5426cb5fbc7f6d2fd5dd13f81d18990afe11d61a5b5b47d163b05875821`.

Reviewed implementation SHA-256:

- `research/btc/reference_r1.py`: `b86d6d3be65f2d6b4b5e5c3e0e797b811ef4a33f04effa0a6341358f68d438ad`
- `research/btc/tests/test_reference_r1.py`: `bf4d4ce930aa4ffabd56e3ee0bf952d91e2426f7c08ab10e102d115ba51bedd7`

Verification: `python3 -m unittest research.btc.tests.test_reference_r1 -v` passes all four
methods, including eight literal scenarios, invalid inputs, output-corruption detection,
caller-context independence, future-mark isolation and mixed-scale regressions.
The Fraction oracle independently derives each state from input quantities, prices and fees;
it does not reuse engine arithmetic or infer expected values from engine output.

Additional reviewer adversarial run reconciled 10000 events exactly. Its first three fills
were buy 1 at 1, sell 1 at 999999999999999999, and buy 0.000000000001 at
0.000000000001, all with zero fees. Events 4–10000 each bought 999999999999999999
at 0.000000000001 with fee 0.000000000001 and mark 999999999999999999.
All appended events shared the third timestamp and had consecutive sequence numbers.
Every row matched the Fraction oracle. Repeating under caller precision 1, ROUND_UP,
Emax 1, Emin -1 and enabled Inexact/Rounded traps returned identical rows.

R1-v1 was correctly rejected: its precision 50 rounded an allowed mixed-scale equity value.
V2's precision 80 covers the stated domain: at most 10000 events, amounts below 1e18,
inventory below 1e22, aggregate notionals and valuation bounded by approximately 2e40,
and products with at most 24 fractional places. Thus 65 digits suffice for relevant
accounting intermediates; the independent tests also exercise mixed extremes.

No blocking findings remain within this narrow contract. This review does not establish
historical execution correctness, realistic fill selection, strategy profitability, data
continuity or causal availability of supplied fills. No historical rows, network calls,
protected services or trading actions were used. Action remains `no_trade`.
