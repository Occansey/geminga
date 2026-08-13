"""Concrete stores: Firestore + Cloud Storage, with in-memory doubles for tests.

These are the Google Cloud infrastructure services the rules require, and the
only modules in the package that import a cloud SDK.
"""

from __future__ import annotations

from .config import settings
from .ports import Plan


class MemoryPlanStore:
    """Test double. Never select this in a submission run — see config.require_cloud."""

    def __init__(self) -> None:
        self._plans: dict[str, dict] = {}

    def load(self, session_id: str) -> Plan | None:
        raw = self._plans.get(session_id)
        return Plan.from_dict(raw) if raw else None

    def save(self, plan: Plan) -> None:
        self._plans[plan.session_id] = plan.to_dict()


class FirestorePlanStore:
    COLLECTION = "agent_plans"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore  # imported lazily: tests run without creds

        self._db = firestore.Client(project=project or settings().google_cloud_project)

    def load(self, session_id: str) -> Plan | None:
        snap = self._db.collection(self.COLLECTION).document(session_id).get()
        return Plan.from_dict(snap.to_dict()) if snap.exists else None

    def save(self, plan: Plan) -> None:
        self._db.collection(self.COLLECTION).document(plan.session_id).set(plan.to_dict())


class MemoryArtifactStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._blobs[key] = data
        return f"memory://{key}"

    def get(self, key: str) -> bytes:
        return self._blobs[key]


class GcsArtifactStore:
    def __init__(self, bucket: str | None = None) -> None:
        from google.cloud import storage

        name = bucket or settings().agent_bucket
        if not name:
            raise RuntimeError("AGENT_BUCKET is unset — see .env.example")
        self._bucket = storage.Client(project=settings().google_cloud_project).bucket(name)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        blob = self._bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{self._bucket.name}/{key}"

    def get(self, key: str) -> bytes:
        return self._bucket.blob(key).download_as_bytes()


def make_plan_store():
    return MemoryPlanStore() if settings().agent_store == "memory" else FirestorePlanStore()


def make_artifact_store():
    return MemoryArtifactStore() if settings().agent_store == "memory" else GcsArtifactStore()
