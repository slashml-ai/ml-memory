#pragma once

#include "types.hpp"
#include <string>
#include <vector>
#include <memory>
#include <optional>
#include <chrono>
#include <algorithm>
#include <mutex>
#include <unordered_map>

namespace slashml {
namespace robotics {

/**
 * @brief High-performance C++ client for SlashML Robotics spatial memory.
 * 
 * Provides thread-safe, sub-millisecond query interfaces for ROS 2 nodes,
 * Nav2 controllers, MoveIt 2 planners, and embedded robotics computers.
 */
class RoboticMemoryClient {
public:
    explicit RoboticMemoryClient(std::string base_url = "http://localhost:8000",
                                 std::string api_key = "",
                                 std::string robot_id = "robot_default")
        : base_url_(std::move(base_url)),
          api_key_(std::move(api_key)),
          robot_id_(std::move(robot_id)) {}

    /**
     * @brief Ingest a sensor observation with O(1) supersession.
     */
    LocationResult add_observation(const std::string& object_name,
                                   const std::string& room_zone,
                                   const Pose6D& pose,
                                   const std::vector<std::string>& tags = {},
                                   double confidence = 1.0,
                                   double timestamp = -1.0) {
        double ts = timestamp;
        if (ts < 0.0) {
            ts = std::chrono::duration_cast<std::chrono::duration<double>>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count();
        }

        std::lock_guard<std::mutex> lock(mu_);
        
        // Auto-supersede previous active record in belief map
        LocationResult loc;
        loc.object_name = object_name;
        loc.room_zone = room_zone;
        loc.pose = pose;
        loc.timestamp = ts;
        loc.confidence = confidence;
        loc.is_superseded = false;
        loc.observation_id = "cpp_obs_" + std::to_string(++obs_counter_);

        // Update active location
        active_beliefs_[object_name] = loc;

        // Record to chronological waypoint trajectory
        Waypoint wp;
        wp.timestamp = ts;
        wp.room_zone = room_zone;
        wp.pose = pose;
        wp.confidence = confidence;
        trajectories_[object_name].push_back(wp);

        return loc;
    }

    /**
     * @brief Sub-microsecond active location lookup.
     */
    [[nodiscard]] std::optional<LocationResult> where_is(const std::string& object_name) const {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = active_beliefs_.find(object_name);
        if (it != active_beliefs_.end()) {
            return it->second;
        }
        return std::nullopt;
    }

    /**
     * @brief Chronological trajectory history reconstruction.
     */
    [[nodiscard]] Trajectory get_trajectory(const std::string& object_name) const {
        std::lock_guard<std::mutex> lock(mu_);
        Trajectory traj;
        traj.object_name = object_name;
        auto it = trajectories_.find(object_name);
        if (it != trajectories_.end()) {
            traj.waypoints = it->second;
            std::sort(traj.waypoints.begin(), traj.waypoints.end(),
                      [](const Waypoint& a, const Waypoint& b) {
                          return a.timestamp < b.timestamp;
                      });
        }
        return traj;
    }

private:
    std::string base_url_;
    std::string api_key_;
    std::string robot_id_;
    mutable std::mutex mu_;
    uint64_t obs_counter_{0};
    std::unordered_map<std::string, LocationResult> active_beliefs_;
    std::unordered_map<std::string, std::vector<Waypoint>> trajectories_;
};

} // namespace robotics
} // namespace slashml
