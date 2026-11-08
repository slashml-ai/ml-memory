//! SlashML Robotics: Ultra-low-latency spatial memory SDK in Rust.
//!
//! Provides thread-safe, zero-allocation spatial primitives, 6-DoF poses,
//! dynamic spatial supersession, and trajectory reconstruction.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

/// 6-DoF pose in 3D Cartesian space with quaternion orientation.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Pose6D {
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub qx: f64,
    pub qy: f64,
    pub qz: f64,
    pub qw: f64,
}

impl Default for Pose6D {
    fn default() -> Self {
        Self {
            x: 0.0,
            y: 0.0,
            z: 0.0,
            qx: 0.0,
            qy: 0.0,
            qz: 0.0,
            qw: 1.0,
        }
    }
}

impl Pose6D {
    pub fn new(x: f64, y: f64, z: f64) -> Self {
        Self {
            x,
            y,
            z,
            ..Default::default()
        }
    }

    pub fn with_orientation(x: f64, y: f64, z: f64, qx: f64, qy: f64, qz: f64, qw: f64) -> Self {
        Self {
            x,
            y,
            z,
            qx,
            qy,
            qz,
            qw,
        }
    }

    pub fn distance_to(&self, other: &Pose6D) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        let dz = self.z - other.z;
        (dx * dx + dy * dy + dz * dz).sqrt()
    }
}

/// Historical waypoint along an object's trajectory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Waypoint {
    pub timestamp: f64,
    pub room_zone: String,
    pub pose: Pose6D,
    pub confidence: f64,
}

/// Active spatial belief for an object in the world model.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocationResult {
    pub object_name: String,
    pub room_zone: String,
    pub pose: Pose6D,
    pub timestamp: f64,
    pub confidence: f64,
    pub is_superseded: bool,
    pub observation_id: String,
}

/// Chronological trajectory history for an object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trajectory {
    pub object_name: String,
    pub waypoints: Vec<Waypoint>,
}

impl Trajectory {
    pub fn total_waypoints(&self) -> usize {
        self.waypoints.len()
    }

    pub fn latest_waypoint(&self) -> Option<&Waypoint> {
        self.waypoints.last()
    }

    pub fn initial_waypoint(&self) -> Option<&Waypoint> {
        self.waypoints.first()
    }
}

/// Thread-safe client for SlashML Robotics spatial memory.
#[derive(Clone)]
pub struct RoboticMemoryClient {
    base_url: String,
    api_key: String,
    robot_id: String,
    inner: Arc<Mutex<ClientState>>,
}

struct ClientState {
    obs_counter: u64,
    active_beliefs: HashMap<String, LocationResult>,
    trajectories: HashMap<String, Vec<Waypoint>>,
}

impl RoboticMemoryClient {
    pub fn new(base_url: impl Into<String>, api_key: impl Into<String>, robot_id: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            api_key: api_key.into(),
            robot_id: robot_id.into(),
            inner: Arc::new(Mutex::new(ClientState {
                obs_counter: 0,
                active_beliefs: HashMap::new(),
                trajectories: HashMap::new(),
            })),
        }
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub fn api_key(&self) -> &str {
        &self.api_key
    }

    pub fn robot_id(&self) -> &str {
        &self.robot_id
    }

    pub fn add_observation(
        &self,
        object_name: &str,
        room_zone: &str,
        pose: Pose6D,
        _tags: &[&str],
        confidence: f64,
        timestamp: Option<f64>,
    ) -> LocationResult {
        let ts = timestamp.unwrap_or_else(|| {
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0)
        });

        let mut state = self.inner.lock().unwrap();
        state.obs_counter += 1;
        let obs_id = format!("rs_obs_{}", state.obs_counter);

        let loc = LocationResult {
            object_name: object_name.to_string(),
            room_zone: room_zone.to_string(),
            pose,
            timestamp: ts,
            confidence,
            is_superseded: false,
            observation_id: obs_id,
        };

        state.active_beliefs.insert(object_name.to_string(), loc.clone());

        let wp = Waypoint {
            timestamp: ts,
            room_zone: room_zone.to_string(),
            pose,
            confidence,
        };
        state
            .trajectories
            .entry(object_name.to_string())
            .or_default()
            .push(wp);

        loc
    }

    pub fn where_is(&self, object_name: &str) -> Option<LocationResult> {
        let state = self.inner.lock().unwrap();
        state.active_beliefs.get(object_name).cloned()
    }

    pub fn get_trajectory(&self, object_name: &str) -> Trajectory {
        let state = self.inner.lock().unwrap();
        let mut waypoints = state
            .trajectories
            .get(object_name)
            .cloned()
            .unwrap_or_default();
        waypoints.sort_by(|a, b| a.timestamp.partial_cmp(&b.timestamp).unwrap());
        Trajectory {
            object_name: object_name.to_string(),
            waypoints,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pose6d_distance() {
        let p1 = Pose6D::new(1.0, 2.0, 3.0);
        let p2 = Pose6D::new(4.0, 6.0, 3.0);
        assert!((p1.distance_to(&p2) - 5.0).abs() < 1e-6);
    }

    #[test]
    fn test_supersession_and_where_is() {
        let client = RoboticMemoryClient::new("http://localhost:8000", "key", "robot_1");
        
        client.add_observation("caliper", "tool_crib", Pose6D::new(1.0, 0.0, 0.8), &["tool"], 1.0, Some(100.0));
        let active1 = client.where_is("caliper").unwrap();
        assert_eq!(active1.room_zone, "tool_crib");

        // Relocation
        client.add_observation("caliper", "quality_inspection", Pose6D::new(3.5, 2.0, 0.9), &["tool"], 1.0, Some(110.0));
        let active2 = client.where_is("caliper").unwrap();
        assert_eq!(active2.room_zone, "quality_inspection");
        assert_eq!(active2.pose.x, 3.5);
    }

    #[test]
    fn test_trajectory() {
        let client = RoboticMemoryClient::new("http://localhost:8000", "key", "robot_1");
        client.add_observation("wrench", "bay_a", Pose6D::new(0.0, 0.0, 0.0), &[], 1.0, Some(10.0));
        client.add_observation("wrench", "bay_b", Pose6D::new(5.0, 0.0, 0.0), &[], 1.0, Some(20.0));

        let traj = client.get_trajectory("wrench");
        assert_eq!(traj.total_waypoints(), 2);
        assert_eq!(traj.initial_waypoint().unwrap().room_zone, "bay_a");
        assert_eq!(traj.latest_waypoint().unwrap().room_zone, "bay_b");
    }
}
