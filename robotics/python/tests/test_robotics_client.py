"""Unit and integration tests for the public slashml-robotics Python SDK.

Verifies:
1. Spatial data structures (Pose6D, BoundingBox3D, Waypoint, LocationResult, Trajectory)
2. In-memory / mock SlashML transport interaction
3. Add observation, where_is lookup, and trajectory reconstruction
4. Affordance taxonomy queries and filtering
"""

import math
import time
from typing import Any, Dict, List, Optional

import pytest

from slashml import MemoryClient
from slashml_robotics import (
    BoundingBox3D,
    LocationResult,
    PhysicalObservation,
    Pose6D,
    RoboticMemory,
    Trajectory,
    Waypoint,
    get_objects_for_affordance,
    is_known_tool,
)


class MockSlashMLBackend:
    """Mock SlashML client backend storing structured observations in-memory for testing."""

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self._next_id = 1

    def add(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = dict(metadata or {})
        rec_id = f"obs_{self._next_id}"
        self._next_id += 1

        # Simulate engine-side O(1) supersession: mark prior records of same object as superseded
        obj_name = meta.get("object_name", "").lower().strip()
        if obj_name:
            for rec in self.records:
                if rec.get("metadata", {}).get("object_name", "").lower().strip() == obj_name:
                    rec["metadata"]["is_superseded"] = True

        meta["is_superseded"] = False
        record = {
            "id": rec_id,
            "memory": messages[0]["content"] if messages else "",
            "user_id": user_id,
            "metadata": meta,
            "filters": filters or {},
            "created_at_epoch": time.time(),
        }
        self.records.append(record)
        return {"id": rec_id, "status": "success"}

    def get_all(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        filt = filters or {}
        req_tags = filt.get("tags", [])
        req_superseded = filt.get("is_superseded")

        for rec in reversed(self.records):
            if rec["user_id"] != user_id:
                continue
            rec_meta = rec.get("metadata", {})
            if req_superseded is not None and rec_meta.get("is_superseded") != req_superseded:
                continue
            if req_tags:
                rec_tags = rec.get("filters", {}).get("tags", [])
                if not any(t in rec_tags for t in req_tags):
                    continue
            results.append(rec)
            if len(results) >= limit:
                break
        return results

    def search(
        self,
        query: str,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        # Simple text matching for mock search
        filt = filters or {}
        req_zone = filt.get("room_zone")
        req_superseded = filt.get("is_superseded")

        matched: List[Dict[str, Any]] = []
        q_lower = query.lower()
        for rec in reversed(self.records):
            if rec["user_id"] != user_id:
                continue
            meta = rec.get("metadata", {})
            if req_superseded is not None and meta.get("is_superseded") != req_superseded:
                continue
            if req_zone and meta.get("room_zone", "").lower() != req_zone.lower():
                continue
            if q_lower in rec["memory"].lower() or q_lower in meta.get("object_name", "").lower():
                item = dict(rec)
                item["score"] = 0.95
                matched.append(item)
            if len(matched) >= limit:
                break
        return matched


def test_pose_6d_geometry() -> None:
    """Test Pose6D instantiation, vector export, and Euclidean distance calculation."""
    p1 = Pose6D(x=1.0, y=2.0, z=3.0)
    assert p1.to_list() == [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0]

    p2 = Pose6D.from_list([4.0, 6.0, 3.0])
    assert p2.x == 4.0 and p2.y == 6.0 and p2.z == 3.0

    dist = p1.distance_to(p2)
    assert math.isclose(dist, 5.0, rel_tol=1e-5)


def test_bounding_box_3d() -> None:
    """Test BoundingBox3D serialization and deserialization."""
    bbox = BoundingBox3D(
        center=Pose6D(x=0.5, y=1.5, z=0.8),
        size_x=0.2,
        size_y=0.1,
        size_z=0.05,
    )
    d = bbox.to_dict()
    restored = BoundingBox3D.from_dict(d)
    assert restored.center.x == 0.5
    assert restored.size_x == 0.2


def test_robotic_memory_observation_and_where_is() -> None:
    """Test observation ingestion and sub-microsecond where_is lookup."""
    mock_backend = MockSlashMLBackend()
    memory = RoboticMemory(client=mock_backend)

    # 1. Initial observation in machining_bay
    res1 = memory.add_observation(
        object_name="digital_caliper",
        room_zone="machining_bay",
        pose=[1.2, -0.4, 0.9, 0.0, 0.0, 0.0, 1.0],
        tags=["tool", "inspection"],
    )
    assert res1.room_zone == "machining_bay"
    assert res1.pose.x == 1.2

    # Query active location
    loc1 = memory.where_is("digital_caliper")
    assert loc1 is not None
    assert loc1.room_zone == "machining_bay"
    assert loc1.pose.x == 1.2

    # 2. Relocate object to quality_inspection (supersession)
    res2 = memory.add_observation(
        object_name="digital_caliper",
        room_zone="quality_inspection",
        pose=[3.5, 2.1, 1.0, 0.0, 0.0, 0.0, 1.0],
        tags=["tool", "inspection"],
    )
    assert res2.room_zone == "quality_inspection"

    # Query active location again: must return updated zone, never obsolete historical zone
    loc2 = memory.where_is("digital_caliper")
    assert loc2 is not None
    assert loc2.room_zone == "quality_inspection"
    assert loc2.pose.x == 3.5


def test_robotic_trajectory_reconstruction() -> None:
    """Test full chronological trajectory reconstruction across multiple moves."""
    mock_backend = MockSlashMLBackend()
    memory = RoboticMemory(client=mock_backend)

    t0 = 1000.0
    # Simulate movement across 3 locations over time
    memory.add_observation("torque_wrench", "tool_crib", [0.5, 0.5, 0.8], timestamp=t0)
    memory.add_observation("torque_wrench", "assembly_station", [2.0, 1.5, 0.9], timestamp=t0 + 10.0)
    memory.add_observation("torque_wrench", "machining_bay", [4.5, -1.0, 0.85], timestamp=t0 + 25.0)

    traj = memory.get_trajectory("torque_wrench")
    assert traj.total_waypoints == 3
    assert traj.initial_waypoint.room_zone == "tool_crib"
    assert traj.latest_waypoint.room_zone == "machining_bay"
    assert traj.latest_waypoint.pose.x == 4.5


def test_affordance_vocabulary_queries() -> None:
    """Test affordance taxonomy lookup."""
    fastening_tools = get_objects_for_affordance("fastening")
    assert "screwdriver" in fastening_tools
    assert "torque wrench" in fastening_tools

    assert is_known_tool("torque wrench")
    assert not is_known_tool("space_shuttle")


def test_find_by_affordance_in_memory() -> None:
    """Test finding tools in the workspace by functional affordance."""
    mock_backend = MockSlashMLBackend()
    memory = RoboticMemory(client=mock_backend)

    # Ingest a screwdriver in machining_bay and a caliper in tool_crib
    memory.add_observation("screwdriver", "machining_bay", [1.0, 0.0, 0.8])
    memory.add_observation("caliper", "tool_crib", [2.0, 0.0, 0.8])

    fasteners = memory.find_by_affordance("fastening")
    assert len(fasteners) == 1
    assert fasteners[0].object_name == "screwdriver"
    assert fasteners[0].room_zone == "machining_bay"
