# Prospective liquidation boot auto-start

Run ID: `prospective-liquidation-production-service-20260913-v1`

## Result

The automatic collection service is prepared and qualified, but it is **not registered or enabled**. The attempted `systemctl --user link` action was rejected by automatic approval review because it would create persistent behavior that launches the year-long collector at the frozen start boundary. No unit was linked, no market socket opened, and no prospective dataset started.

The user systemd manager supports boot persistence: user lingering is enabled. The prepared service is designed to start at every boot and the timer covers the initial frozen boundary at `2026-09-16T00:00:00Z`. Before that boundary, the runner exits without checking storage, creating the research namespace, or opening a market socket. After the boundary it fails closed unless the pinned runtime and source hashes, designated Samsung SSD, capacity, archive, and clock admission all qualify.

## Qualified release

- Release root: `research/btc/review_runs/prospective-liquidation-production-service-20260913-v1/`
- Authorization SHA-256: `39ee3c1690ac6225288359010283de668e4d720c2525bfcacac722d8612c3686`
- Production runner SHA-256: `83de062733d88114c6ac5072170c76f29fe027f472bd53a4bef65c3039c30621`
- Backup-mount preflight SHA-256: `6f5d7bf7eb7556572079b064e25b110abcfb92549159145f6aa7210514fe816b`
- Service SHA-256: `8c64bfc1c9c9778886343a78488cf36e41fa4948281b7e1b99ca58f31d6225ed`
- Timer SHA-256: `37b34f81f1e89100f22a55e3e617bcf17545d1a48b89b158336f8983d392bb17`
- Full regression log SHA-256: `20dc9f55d3422162d517c8a14608633ed72af11a7631adc6c5a0b8374b0e4305`
- Tests: **394/394 passed**, zero failures, errors, or skips.
- Source/runtime qualification-only command: PASS; network started: false.
- `systemd-analyze verify`: exit 0. Its output contained only unrelated host-unit warnings.

The release adds only the continuous process wrapper, exact production namespace admission, configured clock-proof location, boot-boundary behavior, and designated-volume mount preflight. The frozen feeds, clock protocol v2, compact archive, 15-minute rotation, compression, independent backup, retirement, health reducer, capacity guard, prospective boundaries, and stopping rule remain unchanged. It contains no event-threshold, outcome, matching, strategy, or profitability calculation.

## Remaining SSD condition

The designated Samsung T7 Shield is present at `/media/joe/ShieldT7`, UUID `EF5F-FBD3`, but currently mounted `ro` with `errors=remount-ro`. The physical block device is not hardware write-locked. A production start would therefore fail before archive creation or any market connection. The filesystem needs an administrator-run exFAT check/repair and a confirmed `rw` remount before the frozen start.

## Automatic approval-review rejection

The rejected action was registration of the prepared user service and timer. The stated reason was that persistent boot/start behavior would automatically launch the long-running collector at the frozen date, while the prior reviewed package required separate final authorization. The reviewer required explicit approval after this risk was disclosed. No workaround was attempted.

## Evidence boundary

Alpha/outcome computation: **NO**. Liquidation thresholds, event membership/counts, returns, matching, profitability, and protected preexisting 2026 evidence were not accessed. The long-running production namespace does not exist and collection has not begun.
