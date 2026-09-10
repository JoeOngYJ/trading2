# Unqualified E1-v3 attempt — stale E0-v3 lineage

This directory preserves the exact clean-room E1 candidate that functionally passed 38 focused
and 46 combined synthetic tests. Its qualification is revoked and it must not be imported,
executed, copied, repaired or used by E2.

E0-v3 bound the then-paused E1 module and test at their active paths. After E0-v3 passed, those
same paths were modified while implementing the authorized successor, without first archiving the
old bytes. The expected old hashes are no longer present in the repository. Consequently the
E0-v3 paused-draft evidence gate cannot be reproduced, even though the economic specification was
frozen before the implementation changes.

This is a provenance failure, not a known accounting failure. The stricter fail-closed remedy was
chosen: revoke the PASS, archive this candidate exactly, create a lineage-only E0-v4 contract, and
require a new clean implementation identity. Never claim the missing E0-v3-bound bytes verify.

Preserved candidate hashes before relocation:

- module: `d70cca4f0a51e3873b92023a7fadd3f1d3d7440a541e7d5a0121b26e9e8c89f5`;
- tests: `ba56c8011312279f2ade79d9e54a1a017e02051798748a142b8c8c092f7662b0`;
- result: `b6e09255b22275a6267bc02b00b8128bd3a6916b055a413dedc8d255d6f5de72`;
- qualification report: `20bcc600c4f600ed7a063282e0020c1dd797cf102af6f19e2910affa30428ec9`;
- evidence manifest: `5a5b0adad698e04cf7e081e575fab60124a8881436c1118d0bed0c48b83a5dc8`.

No historical market row, strategy result, 2026 data, partial OB0 data, credential, external
service or executable action was involved.
