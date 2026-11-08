/**
 * @file visualize_markers.mjs
 * @brief Foxglove Studio & Web Teleoperation 3D Scene Marker Generator.
 *
 * Demonstrates querying @slashml/robotics spatial memory and generating
 * 3D Scene Marker payloads (compatible with Foxglove Studio, Rviz Web, and Three.js).
 *
 * Usage:
 *   node visualize_markers.mjs
 */

import { RoboticMemoryClient, createPose6D } from "../../typescript/dist/index.js";

function createSphereMarker(id, name, pose, color = { r: 0.2, g: 0.8, b: 0.2, a: 0.9 }) {
  return {
    id,
    type: "SPHERE",
    action: "ADD",
    pose: {
      position: { x: pose.x, y: pose.y, z: pose.z },
      orientation: { x: pose.qx, y: pose.qy, z: pose.qz, w: pose.qw },
    },
    scale: { x: 0.12, y: 0.12, z: 0.12 },
    color,
    text: name,
  };
}

function createTrajectoryLineStrip(id, name, waypoints, color = { r: 0.2, g: 0.4, b: 0.9, a: 0.8 }) {
  return {
    id,
    type: "LINE_STRIP",
    action: "ADD",
    points: waypoints.map((wp) => ({
      x: wp.pose.x,
      y: wp.pose.y,
      z: wp.pose.z,
    })),
    scale: { x: 0.02, y: 0.0, z: 0.0 },
    color,
    text: `${name}_trajectory`,
  };
}

async function main() {
  console.log("[SlashML Foxglove Viz] Initializing 3D visualization exporter...");

  const client = new RoboticMemoryClient({
    baseUrl: "http://localhost:8000",
    apiKey: "sml_live_local_key",
    robotId: "teleop_console_1",
  });

  // 1. Simulate workspace observations
  console.log("Simulating dynamic workspace observations...");
  client.addObservation({
    objectName: "digital_caliper",
    roomZone: "inspection_bench",
    pose: createPose6D(1.2, 0.5, 0.85),
    tags: ["tool", "measuring"],
    confidence: 0.98,
  });

  client.addObservation({
    objectName: "digital_caliper",
    roomZone: "assembly_station_1",
    pose: createPose6D(2.1, -0.4, 0.92),
    tags: ["tool", "measuring"],
    confidence: 0.99,
  });

  client.addObservation({
    objectName: "torque_wrench",
    roomZone: "assembly_station_1",
    pose: createPose6D(2.25, -0.35, 0.92, 0.0, 0.0, 0.7071, 0.7071),
    tags: ["tool", "fastening"],
    confidence: 0.95,
  });


  // 2. Query active objects
  const activeItems = ["digital_caliper", "torque_wrench"];
  const markers = [];

  for (let i = 0; i < activeItems.length; i++) {
    const item = activeItems[i];
    const loc = client.whereIs(item);
    if (loc) {
      markers.push(
        createSphereMarker(
          `marker_${item}`,
          `${item} (${loc.roomZone})`,
          loc.pose,
          item.includes("caliper")
            ? { r: 0.1, g: 0.8, b: 0.3, a: 0.9 }
            : { r: 0.9, g: 0.5, b: 0.1, a: 0.9 }
        )
      );

      // Trajectory trail
      const traj = client.getTrajectory(item);
      if (traj.waypoints.length > 1) {
        markers.push(createTrajectoryLineStrip(`trail_${item}`, item, traj.waypoints));
      }
    }
  }

  // 3. Format output payload for Foxglove Studio / Rviz Web
  const scenePayload = {
    timestamp: Date.now(),
    frame_id: "map",
    marker_count: markers.length,
    markers,
  };

  console.log("\nGenerated 3D Scene Marker Payload for Foxglove Studio:");
  console.log(JSON.stringify(scenePayload, null, 2));
  console.log("\n[SlashML Foxglove Viz] 3D markers generated successfully.");
}

main().catch((err) => {
  console.error("Error generating markers:", err);
  process.exit(1);
});
