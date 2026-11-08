# SlashML Robotics Examples & Integration Recipes

Runnable, production-grade integration examples for physical robotics stacks, perception pipelines, real-time motion planners, and web dashboards.

---

## 1. ROS 2 Vision Perception Subscriber (`ros2_vision_subscriber.py`)

Connects continuous 3D perception models (YOLO-World, RT-DETR, SAM, FoundationPose) to SlashML spatial memory with O(1) dynamic spatial supersession and advertises ROS 2 services for behavior tree planners (`/slashml/where_is`, `/slashml/get_trajectory`, `/slashml/find_by_affordance`).

### Running Standalone Simulation
```bash
python ros2_vision_subscriber.py --simulate
```

### Running in a Live ROS 2 Workspace
```bash
ros2 run slashml_robotics vision_subscriber --ros-args -p base_url:="http://localhost:8000"
```

---

## 2. Hard Real-Time C++17 Nav2 & MoveIt 2 Client (`cpp_nav2_client.cpp`)

Sub-microsecond active target pose lookup for high-frequency control loops, BehaviorTree.CPP actions, and Nav2 `NavigateToPose` goal dispatch.

### Compilation & Execution
```bash
g++ -std=c++17 -I../cpp/include cpp_nav2_client.cpp -o cpp_nav2_client
./cpp_nav2_client http://localhost:8000
```

---

## 3. Foxglove Studio & Web Teleoperation 3D Scene Markers (`foxglove_panel/visualize_markers.mjs`)

Queries active workspace locations and chronological trajectories using `@slashml/robotics` and formats standard 3D Scene Marker payloads (compatible with Foxglove Studio, Rviz Web, and Three.js).

### Running Marker Generator
```bash
node foxglove_panel/visualize_markers.mjs
```
