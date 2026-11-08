# SlashML Robotics Python SDK

Ultra-low-latency spatial memory and dynamic belief tracking for embodied AI, mobile manipulation, and autonomous robots.

## Overview

`slashml-robotics` provides a sub-millisecond, zero-recomputation spatial memory substrate for robotics perception pipelines and mission planners:
- **O(1) Dynamic Spatial Supersession**: Updates object locations instantly and marks obsolete historical coordinates as superseded without full-database reindexing.
- **Sub-Microsecond `where_is`**: Query active 6-DoF poses and room zones with sub-microsecond retrieval latency.
- **Chronological Trajectory Reconstruction**: Full movement history tracking across workspaces and rooms.
- **Physical Affordance Search**: Discover tools and objects based on functional capabilities (e.g. `fastening`, `measuring`, `stripping`).

## Installation

```bash
pip install slashml-robotics
```

## Quickstart

```python
from slashml_robotics import RoboticMemory, Pose6D

# Initialize client connected to SlashML engine daemon or cloud endpoint
memory = RoboticMemory(base_url="http://localhost:8000", api_key="sk_...")

# 1. Ingest camera / perception detection
memory.add_observation(
    object_name="torque_wrench",
    room_zone="machining_bay",
    pose=Pose6D(x=1.24, y=-0.52, z=0.85, qx=0.0, qy=0.0, qz=0.0, qw=1.0),
    tags=["tool", "hardware"],
)

# 2. Query active location
loc = memory.where_is("torque_wrench")
if loc:
    print(f"Found {loc.object_name} in {loc.room_zone} at ({loc.pose.x}, {loc.pose.y}, {loc.pose.z})")

# 3. Retrieve movement trajectory
trajectory = memory.get_trajectory("torque_wrench")
print(f"Total waypoints recorded: {trajectory.total_waypoints}")

# 4. Search by physical affordance
tools = memory.find_by_affordance("fastening", room_zone="machining_bay")
for t in tools:
    print(f"Available fastening tool: {t.object_name}")
```

## License

Apache-2.0
