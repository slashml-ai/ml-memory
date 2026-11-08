#include "slashml/client.hpp"
#include <cassert>
#include <iostream>
#include <cmath>

int main() {
    using namespace slashml::robotics;

    // Test 1: Pose6D geometry
    Pose6D p1(1.0, 2.0, 3.0);
    Pose6D p2(4.0, 6.0, 3.0);
    double dist = p1.distance_to(p2);
    assert(std::abs(dist - 5.0) < 1e-6);
    std::cout << "[PASS] Pose6D geometry\n";

    // Test 2: Ingestion & where_is
    RoboticMemoryClient client("http://localhost:8000", "test_key", "robot_arm_1");
    auto loc1 = client.add_observation("torque_wrench", "tool_crib", Pose6D(1.0, 0.5, 0.8), {"tool"});
    assert(loc1.room_zone == "tool_crib");
    
    auto active1 = client.where_is("torque_wrench");
    assert(active1.has_value());
    assert(active1->room_zone == "tool_crib");
    assert(std::abs(active1->pose.x - 1.0) < 1e-6);
    std::cout << "[PASS] Ingestion & where_is\n";

    // Test 3: Relocation supersession
    client.add_observation("torque_wrench", "machining_bay", Pose6D(3.2, -1.5, 0.9), {"tool"});
    auto active2 = client.where_is("torque_wrench");
    assert(active2.has_value());
    assert(active2->room_zone == "machining_bay");
    assert(std::abs(active2->pose.x - 3.2) < 1e-6);
    std::cout << "[PASS] Dynamic spatial supersession\n";

    // Test 4: Trajectory reconstruction
    auto traj = client.get_trajectory("torque_wrench");
    assert(traj.total_waypoints() == 2);
    assert(traj.initial_waypoint()->room_zone == "tool_crib");
    assert(traj.latest_waypoint()->room_zone == "machining_bay");
    std::cout << "[PASS] Trajectory reconstruction\n";

    std::cout << "All C++ robotics client tests passed successfully.\n";
    return 0;
}
