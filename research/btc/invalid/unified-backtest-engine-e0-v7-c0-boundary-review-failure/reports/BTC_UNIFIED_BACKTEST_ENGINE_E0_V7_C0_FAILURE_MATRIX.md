# E0-v7 C0 failure matrix

| ID | Single owner | Independent probe | Required disposition |
|---|---|---|---|
| C0F01 | C0 | P01 | Duplicate JSON key or non-finite number is rejected. |
| C0F02 | C0 | P02 | Absolute, parent-traversing, empty, or non-normalized path is rejected. |
| C0F03 | C0 | P03 | File size or SHA-256 mismatch is rejected. |
| C0F04 | C0 | P04 | Duplicate path or semantic role is rejected. |
| C0F05 | C0 | P05 | Unknown or mutable RunSpec identity is rejected. |
| C0F06 | C0 | P06 | Mandate, adapter, mode, latency, or scenario incompatibility is rejected. |
| C0F07 | C0 | P07 | Missing, rejected, or hash-mismatched dependency acceptance is rejected. |
| C0F08 | C0 | P08 | Incomplete C0 implementation-manifest or transitive lineage is rejected. |
| C0F09 | C0 | P09 | Caller-supplied economic fields are impossible at the supported public boundary. |
| C0F10 | C0 | P10 | Any premature C1-C6 implementation, test, candidate, contract, or oracle path is rejected. |
| C0F11 | C0 | P11 | Interface field/type/nullability/producer/consumer drift is rejected. |
| C0F12 | C0 | P12 | Obligation pointer/value/owner/probe drift is rejected. |
| C0F13 | C0 | P13 | Bundle path/role/size/digest drift is rejected. |
| C0F14 | C0 | P14 | Missing independent reviewer, missing required review finding, or non-pass verdict is rejected. |

Each finding has exactly one owner. The validator binds this complete mapping, not merely the set
of identifiers. No C1-C6 economic requirement is claimed closed by this matrix.
