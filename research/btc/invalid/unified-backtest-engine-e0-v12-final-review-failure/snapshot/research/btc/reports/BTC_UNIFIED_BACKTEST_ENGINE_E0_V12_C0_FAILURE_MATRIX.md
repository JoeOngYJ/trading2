# E0-v12 exact C0 failure matrix

| ID | Owner | Probe | Failure disposition |
|---|---|---|---|
| C0F01 | C0 | P01 | Reject duplicate keys and non-finite JSON. |
| C0F02 | C0 | P02 | Reject unsafe/non-normalized repository paths. |
| C0F03 | C0 | P03 | Reject path, role, byte-size or digest mismatch. |
| C0F04 | C0 | P04 | Reject duplicate paths, roles or RunSpec identities. |
| C0F05 | C0 | P05 | Reject caller input other than `run_spec_id`. |
| C0F06 | C0 | P06 | Reject invalid real UTC or non-increasing partition bounds. |
| C0F07 | C0 | P07 | Reject any selection outside the exact compatibility tuples. |
| C0F08 | C0 | P08 | Reject non-C0, dependent or incomplete C0 manifests. |
| C0F09 | C0 | P09 | Reject a manifest/context digest outside its exact self-excluding domain. |
| C0F10 | C0 | P10 | Reject mutable returned records or nested collections. |
| C0F11 | C0 | P11 | Reject interface type/nullability/producer/explicit-consumer drift. |
| C0F12 | C0 | P12 | Reject inherited pointer/value/owner/probe drift. |
| C0F13 | C0 | P13 | Reject any premature active C0-C6, E1-v15 or E2 path. |
| C0F14 | C0 | P14 | Reject missing, same-identity, same-role, unbound or non-pass reviews. |

The validator binds this exact ordered mapping. These are C0 failures only; no downstream economic
obligation is assigned or closed.
