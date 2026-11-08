"""Tests for ROS 2 Bridge Node and Embodied MCP Server."""

import json
from slashml_robotics import Pose6D, RoboticMemory
from slashml_robotics.ros2 import SlashMLSpatialBridgeNode
from slashml_robotics.mcp import EmbodiedRoboticsMCPServer
from test_robotics_client import MockSlashMLBackend


def test_package_exports() -> None:
    """Verify package submodules export bridge node and MCP server cleanly."""
    assert SlashMLSpatialBridgeNode is not None
    assert EmbodiedRoboticsMCPServer is not None



def test_ros2_spatial_bridge_node() -> None:
    backend = MockSlashMLBackend()
    memory = RoboticMemory(client=backend)
    node = SlashMLSpatialBridgeNode(node_name="test_bridge", memory_client=memory)

    node.set_current_room_zone("machining_bay")
    
    # 1. Ingest detection via perception callback
    res = node.handle_detection(
        class_name="hex_key",
        pose_x=1.5,
        pose_y=-0.2,
        pose_z=0.8,
        confidence=0.98,
        tags=["tool", "hardware"],
    )
    assert res.object_name == "hex_key"
    assert res.room_zone == "machining_bay"

    # 2. Query where_is service
    loc_resp = node.service_where_is("hex_key")
    assert loc_resp is not None
    assert loc_resp["room_zone"] == "machining_bay"
    assert loc_resp["pose"]["x"] == 1.5

    # 3. Query find_by_affordance service
    fastening_tools = node.service_find_by_affordance("fastening")
    assert len(fastening_tools) >= 1
    assert any(t["object_name"] == "hex_key" for t in fastening_tools)

    # 4. Trajectory service
    traj = node.service_get_trajectory("hex_key")
    assert traj["total_waypoints"] == 1


def test_embodied_mcp_server_tools() -> None:
    backend = MockSlashMLBackend()
    memory = RoboticMemory(client=backend)
    server = EmbodiedRoboticsMCPServer(memory=memory)

    # Verify tool list schema
    tools = server.get_tool_list()
    tool_names = [t["name"] for t in tools]
    assert "locate_physical_object" in tool_names
    assert "record_sensor_observation" in tool_names
    assert "query_object_trajectory" in tool_names
    assert "find_objects_by_affordance" in tool_names

    # Test record observation tool call
    rec_res = server.execute_tool(
        "record_sensor_observation",
        {
            "object_name": "digital_caliper",
            "room_zone": "quality_inspection",
            "pose": [2.0, 1.0, 0.85, 0.0, 0.0, 0.0, 1.0],
            "tags": ["tool", "inspection"],
            "confidence": 0.99,
        },
    )
    assert rec_res["status"] == "recorded"
    assert rec_res["object_name"] == "digital_caliper"

    # Test locate tool call
    loc_res = server.execute_tool(
        "locate_physical_object",
        {"object_name": "digital_caliper"},
    )
    assert loc_res["status"] == "found"
    assert loc_res["room_zone"] == "quality_inspection"
    assert loc_res["pose"]["x"] == 2.0

    # Test affordance tool call
    aff_res = server.execute_tool(
        "find_objects_by_affordance",
        {"affordance": "measuring"},
    )
    assert aff_res["total_matches"] >= 1
    assert aff_res["objects"][0]["object_name"] == "digital_caliper"

    # Test missing object
    missing = server.execute_tool("locate_physical_object", {"object_name": "non_existent_part"})
    assert missing["status"] == "not_found"
