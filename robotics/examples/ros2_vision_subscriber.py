#!/usr/bin/env python3
"""ROS 2 Vision Perception Subscriber Example for SlashML Robotics.

Demonstrates connecting camera / 3D object detection pipelines (e.g. YOLO-World,
RT-DETR, SAM, FoundationPose) to SlashML spatial memory with O(1) dynamic supersession.

Usage:
    # Standalone simulation check:
    python examples/ros2_vision_subscriber.py --simulate

    # In a live ROS 2 workspace:
    ros2 run slashml_robotics vision_subscriber --ros-args -p base_url:="http://localhost:8000"
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("slashml.ros2.example")

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import PoseStamped, TransformStamped
    _HAVE_ROS2 = True
except ImportError:
    _HAVE_ROS2 = False
    logger.info("ROS 2 (rclpy) not found in current environment; running in simulation fallback mode.")

from slashml_robotics import Pose6D, RoboticMemory
from slashml_robotics.ros2 import SlashMLSpatialBridgeNode


class VisionPerceptionSubscriber:
    """Subscribes to vision detections and bridges them to SlashML spatial memory."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = "sml_local_appliance",
        robot_id: str = "robot_companion_1",
        default_zone: str = "machining_bay",
        use_mock: bool = False,
    ) -> None:
        memory_client = None
        if use_mock:
            # Inline in-memory backend for simulation without external daemon
            class _SimulatedBackend:
                def __init__(self) -> None:
                    self.records: List[Dict[str, Any]] = []
                    self._next_id = 1
                def add(self, messages: Any, user_id: str, metadata: Any = None, filters: Any = None) -> Dict[str, Any]:
                    meta = dict(metadata or {})
                    rec_id = f"sim_{self._next_id}"
                    self._next_id += 1
                    obj_name = meta.get("object_name", "").lower().strip()
                    if obj_name:
                        for rec in self.records:
                            if rec.get("metadata", {}).get("object_name", "").lower().strip() == obj_name:
                                rec["metadata"]["is_superseded"] = True
                    meta["is_superseded"] = False
                    self.records.append({
                        "id": rec_id,
                        "metadata": meta,
                        "created_at_epoch": time.time(),
                    })
                    return {"id": rec_id, "status": "success"}
                def get_all(self, user_id: str, filters: Any = None, limit: int = 100) -> List[Dict[str, Any]]:
                    filt = filters or {}
                    req_superseded = filt.get("is_superseded")
                    results = []
                    for rec in reversed(self.records):
                        if req_superseded is not None and rec["metadata"].get("is_superseded") != req_superseded:
                            continue
                        results.append(rec)
                    return results[:limit]

            memory_client = RoboticMemory(client=_SimulatedBackend(), robot_id=robot_id)

        self.bridge = SlashMLSpatialBridgeNode(
            node_name="slashml_vision_subscriber",
            base_url=base_url,
            api_key=api_key,
            robot_id=robot_id,
            default_room_zone=default_zone,
            memory_client=memory_client,
        )
        mode = "in-memory simulation" if use_mock else f"remote server ({base_url})"
        logger.info("Initialized SlashML vision bridge for robot '%s' [%s]", robot_id, mode)


    def on_vision_detection(
        self,
        label: str,
        x: float,
        y: float,
        z: float,
        qx: float = 0.0,
        qy: float = 0.0,
        qz: float = 0.0,
        qw: float = 1.0,
        confidence: float = 0.95,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Callback invoked whenever the visual detector outputs a 3D bounding box."""
        t0 = time.perf_counter()
        loc = self.bridge.handle_detection(
            class_name=label,
            pose_x=x,
            pose_y=y,
            pose_z=z,
            qx=qx,
            qy=qy,
            qz=qz,
            qw=qw,
            confidence=confidence,
            tags=tags or ["tool"],
        )
        latency_us = (time.perf_counter() - t0) * 1e6
        logger.info(
            "Observation ingested: '%s' in zone '%s' at (%.2f, %.2f, %.2f) [latency: %.1f us]",
            loc.object_name,
            loc.room_zone,
            loc.pose.x,
            loc.pose.y,
            loc.pose.z,
            latency_us,
        )

    def query_target_for_planner(self, object_name: str) -> Optional[Dict[str, Any]]:
        """Behavior tree service callback: lookup target location for manipulation."""
        loc = self.bridge.service_where_is(object_name)
        if loc:
            logger.info("Planner lookup: '%s' active at %s (%.2f, %.2f, %.2f)",
                        object_name, loc["room_zone"], loc["pose"]["x"], loc["pose"]["y"], loc["pose"]["z"])
        else:
            logger.warning("Planner lookup: '%s' not found in workspace", object_name)
        return loc


def run_simulation(base_url: str, use_mock: bool = True) -> None:
    """Simulate a dynamic workspace scenario with spatial supersession and trajectory tracking."""
    subscriber = VisionPerceptionSubscriber(base_url=base_url, use_mock=use_mock)

    logger.info("--- Step 1: Initial camera observation of digital_caliper on inspection_bench ---")
    subscriber.bridge.set_current_room_zone("inspection_bench")
    subscriber.on_vision_detection("digital_caliper", 1.20, 0.45, 0.88, confidence=0.98, tags=["tool", "measuring"])

    logger.info("--- Step 2: Query active location ---")
    loc1 = subscriber.query_target_for_planner("digital_caliper")
    assert loc1 is not None
    assert loc1["room_zone"] == "inspection_bench"

    logger.info("--- Step 3: Human technician moves digital_caliper to tool_crib ---")
    subscriber.bridge.set_current_room_zone("tool_crib")
    subscriber.on_vision_detection("digital_caliper", 3.50, -1.20, 1.10, confidence=0.99, tags=["tool", "measuring"])

    logger.info("--- Step 4: Verify O(1) dynamic supersession (new coordinates active) ---")
    loc2 = subscriber.query_target_for_planner("digital_caliper")
    assert loc2 is not None
    assert loc2["room_zone"] == "tool_crib"
    assert abs(loc2["pose"]["x"] - 3.50) < 1e-3

    logger.info("--- Step 5: Query movement trajectory history ---")
    traj = subscriber.bridge.service_get_trajectory("digital_caliper")
    logger.info("Trajectory for digital_caliper has %d waypoints:", traj["total_waypoints"])
    for i, wp in enumerate(traj["waypoints"]):
        logger.info("  Waypoint %d: zone='%s', pos=(%.2f, %.2f, %.2f)",
                    i + 1, wp["room_zone"], wp["pose"]["x"], wp["pose"]["y"], wp["pose"]["z"])

    logger.info("--- Step 6: Query tools by affordance ('measuring') ---")
    tools = subscriber.bridge.service_find_by_affordance("measuring")
    logger.info("Found %d tools for affordance 'measuring': %s",
                len(tools), [t["object_name"] for t in tools])

    logger.info("Simulation completed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ROS 2 Vision Perception Subscriber for SlashML")
    parser.add_argument("--base-url", default="http://localhost:8000", help="SlashML server base URL")
    parser.add_argument("--simulate", action="store_true", help="Run standalone simulation workflow")
    args = parser.parse_args()

    if args.simulate or not _HAVE_ROS2:
        run_simulation(args.base_url)
    else:
        logger.info("Starting ROS 2 node...")
        rclpy.init()
        # Node lifecycle loop would spin here in a live ROS 2 distribution
        rclpy.shutdown()


if __name__ == "__main__":
    main()
