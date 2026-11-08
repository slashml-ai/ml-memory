"""Embodied Agentic MCP Server for SlashML Robotics.

Exposes Model Context Protocol (MCP) tools for LLM planners, VLA agents, and
embodied physical assistants to query and update 3D physical workspace memory.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from slashml_robotics import (
    LocationResult,
    Pose6D,
    RoboticMemory,
    Trajectory,
)

# Standard MCP Tool Definitions
ROBOTICS_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "locate_physical_object",
        "description": "Get the current active 6-DoF location, room zone, and observation timestamp of a physical object in the robot's workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name or canonical label of the object (e.g. 'torque_wrench', 'digital_caliper', 'parts_bin').",
                },
            },
            "required": ["object_name"],
        },
    },
    {
        "name": "record_sensor_observation",
        "description": "Record a new camera/perception observation of a physical object. Automatically supersedes older coordinates in O(1) time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name or label of the object.",
                },
                "room_zone": {
                    "type": "string",
                    "description": "Room or workstation zone (e.g. 'machining_bay', 'tool_crib', 'assembly_station').",
                },
                "pose": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "3D position [x, y, z] or 6-DoF pose [x, y, z, qx, qy, qz, qw] in meters.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional semantic tags or affordances (e.g. ['tool', 'fastening']).",
                },
                "confidence": {
                    "type": "number",
                    "description": "Detection confidence score between 0.0 and 1.0.",
                },
            },
            "required": ["object_name", "room_zone", "pose"],
        },
    },
    {
        "name": "query_object_trajectory",
        "description": "Reconstruct the chronological movement trajectory and waypoint history for an object across workspaces.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name of the object whose movement path is to be inspected.",
                },
            },
            "required": ["object_name"],
        },
    },
    {
        "name": "find_objects_by_affordance",
        "description": "Find active physical objects in the workspace that support a given task affordance (e.g. 'fastening', 'measuring', 'stripping').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "affordance": {
                    "type": "string",
                    "description": "Functional capability or action (e.g. 'fastening', 'measuring', 'cutting', 'soldering').",
                },
                "room_zone": {
                    "type": "string",
                    "description": "Optional room zone filter (e.g. 'machining_bay').",
                },
            },
            "required": ["affordance"],
        },
    },
]


class EmbodiedRoboticsMCPServer:
    """Dispatches tool calls from embodied LLM agents to RoboticMemory."""

    def __init__(self, memory: Optional[RoboticMemory] = None) -> None:
        self.memory = memory or RoboticMemory()

    def get_tool_list(self) -> List[Dict[str, Any]]:
        return ROBOTICS_TOOLS

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a robotics spatial tool call."""
        if name == "locate_physical_object":
            obj_name = arguments.get("object_name", "")
            loc = self.memory.where_is(obj_name)
            if loc is None:
                return {
                    "status": "not_found",
                    "message": f"Object '{obj_name}' has no active observation in memory.",
                }
            return {
                "status": "found",
                "object_name": loc.object_name,
                "room_zone": loc.room_zone,
                "pose": loc.pose.to_dict(),
                "timestamp": loc.timestamp,
                "confidence": loc.confidence,
                "age_seconds": round(loc.age_seconds, 2),
            }

        elif name == "record_sensor_observation":
            obj_name = arguments.get("object_name", "")
            zone = arguments.get("room_zone", "")
            pose_raw = arguments.get("pose", [0.0, 0.0, 0.0])
            tags = arguments.get("tags", [])
            conf = float(arguments.get("confidence", 1.0))
            
            pose = Pose6D.from_list(pose_raw)
            loc = self.memory.add_observation(
                object_name=obj_name,
                room_zone=zone,
                pose=pose,
                tags=tags,
                confidence=conf,
            )
            return {
                "status": "recorded",
                "observation_id": loc.observation_id,
                "object_name": loc.object_name,
                "room_zone": loc.room_zone,
                "pose": loc.pose.to_dict(),
            }

        elif name == "query_object_trajectory":
            obj_name = arguments.get("object_name", "")
            traj = self.memory.get_trajectory(obj_name)
            return traj.to_dict()

        elif name == "find_objects_by_affordance":
            affordance = arguments.get("affordance", "")
            zone = arguments.get("room_zone")
            matches = self.memory.find_by_affordance(affordance, room_zone=zone)
            return {
                "affordance": affordance,
                "total_matches": len(matches),
                "objects": [m.to_dict() for m in matches],
            }

        else:
            raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    """Standard stdio MCP server loop for robotics agents."""
    server = EmbodiedRoboticsMCPServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")

            if method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": server.get_tool_list()}}
            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})
                res = server.execute_tool(name, args)
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}}
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not found"}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(e)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
