from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from .contracts import ArtifactRef, EvidenceManifest, SourceObservation


def persist_artifact(connection: Connection, artifact: ArtifactRef) -> None:
    connection.execute(
        """
        INSERT INTO artifacts(digest,media_type,byte_length,storage_path)
        VALUES (%s,%s,%s,%s) ON CONFLICT (digest) DO NOTHING
        """,
        (artifact.digest, artifact.media_type, artifact.byte_length, artifact.storage_path),
    )


def persist_observation(connection: Connection, observation: SourceObservation) -> None:
    persist_artifact(connection, observation.artifact)
    connection.execute(
        """
        INSERT INTO source_observations(
            observation_id,category,vendor,symbol_or_query,external_id,canonical_url,
            event_at,published_at,first_seen_at,retrieved_at,artifact_digest,
            request_parameters,status,error_code,quality_flags,replay_safe,replay_unsafe_reason
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (observation_id) DO NOTHING
        """,
        (
            observation.observation_id, observation.category, observation.vendor,
            observation.symbol_or_query, observation.external_id, observation.canonical_url,
            observation.event_at, observation.published_at, observation.first_seen_at,
            observation.retrieved_at, observation.artifact.digest,
            Jsonb(observation.request_parameters), observation.status, observation.error_code,
            Jsonb(observation.quality_flags), observation.replay_safe,
            observation.replay_unsafe_reason,
        ),
    )


def manifest_digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def seal_manifest(
    connection: Connection,
    *,
    manifest_id: UUID,
    run_id: UUID,
    instrument_id: str,
    execution_snapshot_id: UUID,
    observation_ids: list[UUID],
    configured_vendors: dict[str, str],
    required_sources: dict[str, str],
    collection_started_at: datetime,
    quality_flags: list[str] | None = None,
    mode: str = "live",
    replay_safe: bool = True,
) -> EvidenceManifest:
    completed_at = datetime.now(timezone.utc)
    digest_data = {
        "manifest_id": str(manifest_id),
        "run_id": str(run_id),
        "instrument_id": instrument_id,
        "execution_snapshot_id": str(execution_snapshot_id),
        "mode": mode,
        "collection_started_at": collection_started_at.isoformat(),
        "collection_completed_at": completed_at.isoformat(),
        "observation_ids": [str(value) for value in observation_ids],
        "configured_vendors": configured_vendors,
        "vendor_fallbacks": [],
        "required_sources": required_sources,
        "replay_safe": replay_safe,
        "quality_flags": quality_flags or [],
    }
    digest = manifest_digest(digest_data)
    manifest = EvidenceManifest(**digest_data, digest=digest)
    connection.execute(
        """
        INSERT INTO evidence_manifests(
            manifest_id,run_id,instrument_id,execution_snapshot_id,mode,status,
            collection_started_at,collection_completed_at,configured_vendors,
            vendor_fallbacks,required_sources,replay_safe,quality_flags,digest
        ) VALUES (%s,%s,%s,%s,%s,'collecting',%s,NULL,%s,%s,%s,NULL,%s,NULL)
        """,
        (
            manifest.manifest_id, manifest.run_id, manifest.instrument_id,
            manifest.execution_snapshot_id, manifest.mode, manifest.collection_started_at,
            Jsonb(manifest.configured_vendors),
            Jsonb(manifest.vendor_fallbacks), Jsonb(manifest.required_sources),
            Jsonb(manifest.quality_flags),
        ),
    )
    for ordinal, observation_id in enumerate(observation_ids):
        connection.execute(
            "INSERT INTO manifest_observations(manifest_id,observation_id,ordinal) VALUES (%s,%s,%s)",
            (manifest.manifest_id, observation_id, ordinal),
        )
    connection.execute(
        """
        UPDATE evidence_manifests
        SET status='sealed',collection_completed_at=%s,replay_safe=%s,digest=%s
        WHERE manifest_id=%s AND status='collecting'
        """,
        (manifest.collection_completed_at, manifest.replay_safe, manifest.digest, manifest.manifest_id),
    )
    return manifest
