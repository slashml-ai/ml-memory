/**
 * SlashML Robotics TypeScript SDK.
 *
 * Provides spatial primitives, 6-DoF poses, and dynamic belief tracking
 * for fleet management dashboards, Foxglove Studio, and WebRTC teleoperation consoles.
 */
export function distancePose6D(a, b) {
    const dx = a.x - b.x;
    const dy = a.y - b.y;
    const dz = a.z - b.z;
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
}
export class RoboticMemoryClient {
    baseUrl;
    apiKey;
    robotId;
    obsCounter = 0;
    activeBeliefs = new Map();
    trajectories = new Map();
    constructor(options) {
        this.baseUrl = options?.baseUrl || 'http://localhost:8000';
        this.apiKey = options?.apiKey || '';
        this.robotId = options?.robotId || 'robot_default';
    }
    addObservation(params) {
        const ts = params.timestamp !== undefined ? params.timestamp : Date.now() / 1000;
        const conf = params.confidence !== undefined ? params.confidence : 1.0;
        this.obsCounter += 1;
        const obsId = `ts_obs_${this.obsCounter}`;
        const loc = {
            objectName: params.objectName,
            roomZone: params.roomZone,
            pose: { ...params.pose, qx: params.pose.qx || 0, qy: params.pose.qy || 0, qz: params.pose.qz || 0, qw: params.pose.qw !== undefined ? params.pose.qw : 1 },
            timestamp: ts,
            confidence: conf,
            isSuperseded: false,
            observationId: obsId,
        };
        // Auto-supersede prior belief
        this.activeBeliefs.set(params.objectName, loc);
        // Append to trajectory
        const wpList = this.trajectories.get(params.objectName) || [];
        wpList.push({
            timestamp: ts,
            roomZone: params.roomZone,
            pose: loc.pose,
            confidence: conf,
        });
        this.trajectories.set(params.objectName, wpList);
        return loc;
    }
    whereIs(objectName) {
        return this.activeBeliefs.get(objectName) || null;
    }
    getTrajectory(objectName) {
        const waypoints = (this.trajectories.get(objectName) || []).slice();
        waypoints.sort((a, b) => a.timestamp - b.timestamp);
        return {
            objectName,
            waypoints,
        };
    }
}
