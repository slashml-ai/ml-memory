"""Data types and schemas for SlashML Robotics spatial memory.

Defines canonical spatial primitives including 6-DoF poses, 3D bounding boxes,
observations, location results, and trajectory waypoints.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class Pose6D:
    """Represents a 6-DoF pose in 3D Cartesian space with quaternion orientation.
    
    Coordinates are in meters; orientation is a normalized unit quaternion (x, y, z, w).
    """

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0

    def to_list(self) -> List[float]:
        """Convert to standard 7-element list [x, y, z, qx, qy, qz, qw]."""
        return [self.x, self.y, self.z, self.qx, self.qy, self.qz, self.qw]

    @classmethod
    def from_list(cls, values: Sequence[float]) -> "Pose6D":
        """Instantiate from a 3-element [x, y, z] or 7-element [x, y, z, qx, qy, qz, qw] sequence."""
        if len(values) == 3:
            return cls(x=float(values[0]), y=float(values[1]), z=float(values[2]))
        if len(values) >= 7:
            return cls(
                x=float(values[0]),
                y=float(values[1]),
                z=float(values[2]),
                qx=float(values[3]),
                qy=float(values[4]),
                qz=float(values[5]),
                qw=float(values[6]),
            )
        raise ValueError(f"Expected at least 3 elements for Pose6D, got {len(values)}")

    def distance_to(self, other: "Pose6D") -> float:
        """Euclidean translation distance to another pose in meters."""
        return math.sqrt(
            (self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2
        )

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class BoundingBox3D:
    """Axis-aligned or oriented 3D bounding box for detected physical objects."""

    center: Pose6D = field(default_factory=Pose6D)
    size_x: float = 0.0
    size_y: float = 0.0
    size_z: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center": self.center.to_dict(),
            "size_x": self.size_x,
            "size_y": self.size_y,
            "size_z": self.size_z,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BoundingBox3D":
        center_raw = data.get("center", {})
        if isinstance(center_raw, list):
            center = Pose6D.from_list(center_raw)
        elif isinstance(center_raw, dict):
            center = Pose6D(**center_raw)
        else:
            center = Pose6D()
        return cls(
            center=center,
            size_x=float(data.get("size_x", 0.0)),
            size_y=float(data.get("size_y", 0.0)),
            size_z=float(data.get("size_z", 0.0)),
        )


@dataclass
class Waypoint:
    """Historical waypoint along an object's physical trajectory."""

    timestamp: float
    room_zone: str
    pose: Pose6D
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "room_zone": self.room_zone,
            "pose": self.pose.to_dict(),
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Waypoint":
        pose_raw = data.get("pose", {})
        if isinstance(pose_raw, list):
            pose = Pose6D.from_list(pose_raw)
        elif isinstance(pose_raw, dict):
            pose = Pose6D(**pose_raw)
        else:
            pose = Pose6D()
        return cls(
            timestamp=float(data.get("timestamp", 0.0)),
            room_zone=str(data.get("room_zone", "")),
            pose=pose,
            confidence=float(data.get("confidence", 1.0)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class LocationResult:
    """Current active spatial belief for a physical entity."""

    object_name: str
    room_zone: str
    pose: Pose6D
    timestamp: float
    confidence: float = 1.0
    is_superseded: bool = False
    observation_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        """Elapsed time in seconds since this location was recorded."""
        return max(0.0, time.time() - self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_name": self.object_name,
            "room_zone": self.room_zone,
            "pose": self.pose.to_dict(),
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "is_superseded": self.is_superseded,
            "observation_id": self.observation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LocationResult":
        pose_raw = data.get("pose", {})
        if isinstance(pose_raw, list):
            pose = Pose6D.from_list(pose_raw)
        elif isinstance(pose_raw, dict):
            pose = Pose6D(**pose_raw)
        else:
            pose = Pose6D()
        return cls(
            object_name=str(data.get("object_name", "")),
            room_zone=str(data.get("room_zone", "")),
            pose=pose,
            timestamp=float(data.get("timestamp", 0.0)),
            confidence=float(data.get("confidence", 1.0)),
            is_superseded=bool(data.get("is_superseded", False)),
            observation_id=str(data.get("observation_id", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Trajectory:
    """Complete chronological trajectory history for an object."""

    object_name: str
    waypoints: List[Waypoint] = field(default_factory=list)

    @property
    def total_waypoints(self) -> int:
        return len(self.waypoints)

    @property
    def latest_waypoint(self) -> Optional[Waypoint]:
        return self.waypoints[-1] if self.waypoints else None

    @property
    def initial_waypoint(self) -> Optional[Waypoint]:
        return self.waypoints[0] if self.waypoints else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_name": self.object_name,
            "total_waypoints": self.total_waypoints,
            "waypoints": [w.to_dict() for w in self.waypoints],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trajectory":
        raw_waypoints = data.get("waypoints", [])
        return cls(
            object_name=str(data.get("object_name", "")),
            waypoints=[Waypoint.from_dict(w) for w in raw_waypoints],
        )


@dataclass
class PhysicalObservation:
    """A single sensor observation submitted to the SlashML memory engine."""

    object_name: str
    room_zone: str
    pose: Pose6D
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0
    timestamp: Optional[float] = None
    observation_id: Optional[str] = None
    bounding_box: Optional[BoundingBox3D] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        ts = self.timestamp if self.timestamp is not None else time.time()
        d: Dict[str, Any] = {
            "object_name": self.object_name,
            "room_zone": self.room_zone,
            "pose": self.pose.to_dict(),
            "tags": list(self.tags),
            "confidence": self.confidence,
            "timestamp": ts,
            "metadata": dict(self.metadata),
        }
        if self.observation_id:
            d["observation_id"] = self.observation_id
        if self.bounding_box:
            d["bounding_box"] = self.bounding_box.to_dict()
        return d
