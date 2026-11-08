import test from 'node:test';
import assert from 'node:assert';
import { RoboticMemoryClient, distancePose6D } from '../dist/index.js';

test('distancePose6D calculates Euclidean distance correctly', () => {
  const p1 = { x: 1.0, y: 2.0, z: 3.0 };
  const p2 = { x: 4.0, y: 6.0, z: 3.0 };
  const dist = distancePose6D(p1, p2);
  assert.strictEqual(Math.round(dist), 5);
});

test('RoboticMemoryClient supersession and whereIs', () => {
  const client = new RoboticMemoryClient();
  client.addObservation({
    objectName: 'wire_stripper',
    roomZone: 'tool_crib',
    pose: { x: 1, y: 0, z: 0.8 },
  });

  const loc1 = client.whereIs('wire_stripper');
  assert.ok(loc1);
  assert.strictEqual(loc1.roomZone, 'tool_crib');

  // Relocate
  client.addObservation({
    objectName: 'wire_stripper',
    roomZone: 'assembly_station',
    pose: { x: 2.5, y: 1.2, z: 0.9 },
  });

  const loc2 = client.whereIs('wire_stripper');
  assert.ok(loc2);
  assert.strictEqual(loc2.roomZone, 'assembly_station');
  assert.strictEqual(loc2.pose.x, 2.5);
});

test('RoboticMemoryClient trajectory reconstruction', () => {
  const client = new RoboticMemoryClient();
  client.addObservation({ objectName: 'screwdriver', roomZone: 'zone_a', pose: { x: 0, y: 0, z: 0 }, timestamp: 100 });
  client.addObservation({ objectName: 'screwdriver', roomZone: 'zone_b', pose: { x: 1, y: 0, z: 0 }, timestamp: 200 });

  const traj = client.getTrajectory('screwdriver');
  assert.strictEqual(traj.waypoints.length, 2);
  assert.strictEqual(traj.waypoints[0].roomZone, 'zone_a');
  assert.strictEqual(traj.waypoints[1].roomZone, 'zone_b');
});
