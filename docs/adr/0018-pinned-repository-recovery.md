# ADR 0018: Pinned repository snapshots for read-only recovery

- Status: Accepted for Phase 5H
- Date: 2026-09-29

## Decision

Add an explicit snapshot mode to the existing repository bindings. Capture the
sorted, deduplicated operator allowlist through the existing descriptor-relative
reader: at most 128 files, 64 KiB per file, 1 MiB total, valid UTF-8 without NUL.
Read/search then operate only on captured immutable strings for the binding's
lifetime. Live mode retains its existing behavior. Capture is not an atomic Git
revision: operators must keep the selected local files stable during capture.

Version-9 runtime configuration requires a workspace identity with three SHA-256
fingerprints: canonical root path plus opened root device/inode; sorted selected
paths and content hashes; and the installed repository/filesystem/core-tool/core-
model source modules plus Python/Pydantic versions. Root paths and file contents
are not embedded in the identity. The implementation digest is conservative code
identity, not an attestation of the entire dependency graph or protection against
hostile local Python. Changing a covered module, even harmless formatting, changes
identity. Fixed provider/profile semantics still require versioned profile IDs.

The new `repository-read-v1` worker profile captures a fresh snapshot at submission
and on each explicit work invocation. It pins the complete expected runtime
configuration. A mismatched root, allowlist, bytes or implementation rejects start
or resume before any model/tool dispatch or history write. Workspace-bound runs
require an expected configuration; a generic store without that binding refuses
execution. The existing live lease may remain after mismatch, as for other profile
errors. Do not silently rebind or adopt a new snapshot.

The CLI requires `--repository-root` and repeated `--file` allowlist entries on
both commands, plus `work --once --run-id` to avoid selecting another workspace's
job. No discovery, automatic tracked-file trust or model-controlled root is added.
The fixed offline provider reads the first excerpt of the first selected file and finishes; both read
and search retain their existing registry/policy boundaries. Usage and pricing
are synthetic. Normal budgets, ownership fences, checkpoints and conservative
failure of uncertain intent apply. No hosted calls, mutation or tool replay.

## Limits and trade-offs

The snapshot is memory-resident, not a durable content archive. Recovery requires
reconstructing identical selected bytes at the same root identity. Edits after
capture cannot change a running binding, but a subsequent process rejects them.
Replacing the root inode or moving its canonical path also rejects recovery, even
with identical content. Unselected files do not participate. Root/allowlist/content
fingerprints are identifiers, not encryption; operators must approve disclosure
before capture and remain responsible for secrets in selected text.

No migration is needed; identity lives in the immutable agent version. The worker
adds a workspace dependency on `runveil-tool-runtime`. PostgreSQL polling remains
the durable transport. Next, define a broker delivery/outbox consistency boundary
for an offline-tested SQS adapter; preserve PostgreSQL ownership as authoritative.
