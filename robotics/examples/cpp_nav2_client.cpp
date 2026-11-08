/**
 * @file cpp_nav2_client.cpp
 * @brief High-performance C++17 client example for ROS 2 Nav2 / MoveIt 2 behavior trees.
 *
 * Demonstrates querying SlashML spatial memory for active 6-DoF target poses
 * before planning mobile base trajectories or arm grasping motions.
 *
 * Compilation:
 *   g++ -std=c++17 -I../cpp/include cpp_nav2_client.cpp -o cpp_nav2_client
 */

#include <iostream>
#include <iomanip>
#include <string>
#include <vector>
#include <cmath>
#include <chrono>

#include <slashml/client.hpp>

namespace {

struct RobotPose2D {
    double x{0.0};
    double y{0.0};
    double theta{0.0};
};

double calculate_distance(const RobotPose2D& robot, double target_x, double target_y) {
    double dx = target_x - robot.x;
    double dy = target_y - robot.y;
    return std::sqrt(dx * dx + dy * dy);
}

} // namespace

int main(int argc, char** argv) {
    using namespace slashml::robotics;

    std::string base_url = (argc > 1) ? argv[1] : "http://localhost:8000";
    std::cout << "[SlashML Nav2 Client] Initializing client for: " << base_url << "\n";

    RoboticMemoryClient client(base_url, "sml_live_local_key", "amr_unit_04");

    // 1. Simulate camera detection of workpiece on assembly station
    std::cout << "\n--- 1. Ingesting perception detection (torque_wrench) ---\n";
    auto t0 = std::chrono::high_resolution_clock::now();
    client.add_observation(
        "torque_wrench",
        "assembly_station_3",
        Pose6D(2.45, -0.80, 0.92, 0.0, 0.0, 0.7071, 0.7071),
        {"tool", "fastening"},
        0.98
    );
    auto t1 = std::chrono::high_resolution_clock::now();
    double ingest_us = std::chrono::duration<double, std::micro>(t1 - t0).count();
    std::cout << "Ingested in " << std::fixed << std::setprecision(1) << ingest_us << " microseconds.\n";

    // 2. Nav2 Behavior Tree query: lookup active target coordinate
    std::cout << "\n--- 2. Behavior Tree query: where_is('torque_wrench') ---\n";
    auto q0 = std::chrono::high_resolution_clock::now();
    auto target_loc = client.where_is("torque_wrench");
    auto q1 = std::chrono::high_resolution_clock::now();
    double query_us = std::chrono::duration<double, std::micro>(q1 - q0).count();

    if (target_loc.has_value()) {
        const auto& loc = *target_loc;
        std::cout << "Target located in " << query_us << " microseconds:\n";
        std::cout << "  Zone:        " << loc.room_zone << "\n";
        std::cout << "  Coordinates: (" << loc.pose.x << ", " << loc.pose.y << ", " << loc.pose.z << ")\n";
        std::cout << "  Quaternion:  [" << loc.pose.qx << ", " << loc.pose.qy << ", " << loc.pose.qz << ", " << loc.pose.qw << "]\n";

        // Current robot base coordinates
        RobotPose2D amr{0.0, 0.0, 0.0};
        double dist = calculate_distance(amr, loc.pose.x, loc.pose.y);
        std::cout << "  Distance from AMR base: " << std::setprecision(2) << dist << " meters.\n";
        std::cout << "  Action: Dispatching Nav2 NavigateToPose goal...\n";
    } else {
        std::cerr << "Target object 'torque_wrench' not found in workspace belief.\n";
        return 1;
    }

    // 3. Inspect waypoint trajectory history
    std::cout << "\n--- 3. Trajectory history ---\n";
    auto traj = client.get_trajectory("torque_wrench");
    std::cout << "Found " << traj.waypoints.size() << " recorded waypoints for torque_wrench.\n";

    std::cout << "\n[SlashML Nav2 Client] Navigation dispatch check complete.\n";
    return 0;
}
