"""ROS 2 Bridge Node for SlashML Robotics Spatial Memory.

Subscribes to standard vision perception topics:
- /detections (vision_msgs/msg/Detection3DArray)
- /tf (geometry_msgs/msg/TransformStamped)

Publishes observations into SlashML Robotic Memory with O(1) dynamic supersession.
Advertises ROS 2 services for task planners and behavior trees:
- /slashml/where_is
- /slashml/get_trajectory
- /slashml/find_by_affordance
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("slashml.ros2")

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Pose, TransformStamped
    _HAVE_ROS2 = True
except ImportError:
    _HAVE_ROS2 = False
    # Mock base class for environments without rclpy installed
    class Node:  # type: ignore[no-redef]
        def __init__(self, node_name: str) -> None:
            self.node_name = node_name

from slashml_robotics import (
    LocationResult,
    Pose6D,
    RoboticMemory,
    Trajectory,
)


class SlashMLSpatialBridgeNode(Node):
    """ROS 2 Node interfacing onboard perception with SlashML spatial memory."""

    def __init__(
        self,
        node_name: str = "slashml_spatial_bridge",
        base_url: str = "http://localhost:8000",
        api_key: str = "",
        robot_id: str = "robot_companion_1",
        default_room_zone: str = "active_workspace",
        memory_client: Optional[RoboticMemory] = None,
    ) -> None:
        super().__init__(node_name)
        self.default_room_zone = default_room_zone
        self.robot_id = robot_id
        
        if memory_client is not None:
            self.memory = memory_client
        else:
            self.memory = RoboticMemory(
                base_url=base_url,
                api_key=api_key,
                robot_id=robot_id,
            )

        self._active_zone = default_room_zone
        self._processed_detections_count = 0

    def set_current_room_zone(self, room_zone: str) -> None:
        """Update current active topological room zone from navigation stack."""
        self._active_zone = room_zone

    def handle_detection(
        self,
        class_name: str,
        pose_x: float,
        pose_y: float,
        pose_z: float,
        qx: float = 0.0,
        qy: float = 0.0,
        qz: float = 0.0,
        qw: float = 1.0,
        confidence: float = 1.0,
        timestamp: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> LocationResult:
        """Process an individual 3D detection and update spatial belief."""
        pose = Pose6D(x=pose_x, y=pose_y, z=pose_z, qx=qx, qy=qy, qz=qz, qw=qw)
        ts = timestamp if timestamp is not None else time.time()
        
        res = self.memory.add_observation(
            object_name=class_name,
            room_zone=self._active_zone,
            pose=pose,
            tags=tags or [],
            confidence=confidence,
            timestamp=ts,
        )
        self._processed_detections_count += 1
        return res

    def service_where_is(self, object_name: str) -> Optional[Dict[str, Any]]:
        """Handler for /slashml/where_is service requests from behavior trees."""
        loc = self.memory.where_is(object_name)
        if loc is None:
            return None
        return loc.to_dict()

    def service_find_by_affordance(
        self,
        action: str,
        room_zone: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Handler for /slashml/find_by_affordance service."""
        zone = room_zone or self._active_zone
        matches = self.memory.find_by_affordance(action, room_zone=zone)
        return [m.to_dict() for m in matches]

    def service_get_trajectory(self, object_name: str) -> Dict[str, Any]:
        """Handler for /slashml/get_trajectory service."""
        traj = self.memory.get_trajectory(object_name)
        return traj.to_dict()
