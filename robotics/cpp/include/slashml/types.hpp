#pragma once

#include <cmath>
#include <cstdint>
#include <string>
#include <vector>
#include <chrono>

namespace slashml {
namespace robotics {

/**
 * @brief 6-DoF pose in 3D Cartesian space with quaternion orientation.
 * 
 * Translation in meters (x, y, z).
 * Orientation normalized quaternion (qx, qy, qz, qw).
 */
struct Pose6D {
    double x{0.0};
    double y{0.0};
    double z{0.0};
    double qx{0.0};
    double qy{0.0};
    double qz{0.0};
    double qw{1.0};

    Pose6D() = default;
    Pose6D(double x_, double y_, double z_)
        : x(x_), y(y_), z(z_), qx(0.0), qy(0.0), qz(0.0), qw(1.0) {}
    Pose6D(double x_, double y_, double z_, double qx_, double qy_, double qz_, double qw_)
        : x(x_), y(y_), z(z_), qx(qx_), qy(qy_), qz(qz_), qw(qw_) {}

    [[nodiscard]] double distance_to(const Pose6D& other) const noexcept {
        const double dx = x - other.x;
        const double dy = y - other.y;
        const double dz = z - other.z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    }
};

/**
 * @brief 3D Bounding Box for physical object detection.
 */
struct BoundingBox3D {
    Pose6D center{};
    double size_x{0.0};
    double size_y{0.0};
    double size_z{0.0};
};

/**
 * @brief Historical waypoint along an object's trajectory.
 */
struct Waypoint {
    double timestamp{0.0};
    std::string room_zone{};
    Pose6D pose{};
    double confidence{1.0};
};

/**
 * @brief Active spatial belief for an object in the world model.
 */
struct LocationResult {
    std::string object_name{};
    std::string room_zone{};
    Pose6D pose{};
    double timestamp{0.0};
    double confidence{1.0};
    bool is_superseded{false};
    std::string observation_id{};

    [[nodiscard]] double age_seconds() const noexcept {
        const auto now = std::chrono::duration_cast<std::chrono::duration<double>>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
        const double diff = now - timestamp;
        return diff > 0.0 ? diff : 0.0;
    }
};

/**
 * @brief Chronological trajectory history for an object.
 */
struct Trajectory {
    std::string object_name{};
    std::vector<Waypoint> waypoints{};

    [[nodiscard]] size_t total_waypoints() const noexcept {
        return waypoints.size();
    }

    [[nodiscard]] const Waypoint* latest_waypoint() const noexcept {
        return waypoints.empty() ? nullptr : &waypoints.back();
    }

    [[nodiscard]] const Waypoint* initial_waypoint() const noexcept {
        return waypoints.empty() ? nullptr : &waypoints.front();
    }
};

/**
 * @brief Ingested observation record.
 */
struct PhysicalObservation {
    std::string object_name{};
    std::string room_zone{};
    Pose6D pose{};
    std::vector<std::string> tags{};
    double confidence{1.0};
    double timestamp{0.0};
    std::string observation_id{};
};

} // namespace robotics
} // namespace slashml
