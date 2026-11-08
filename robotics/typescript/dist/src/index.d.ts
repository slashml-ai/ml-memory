/**
 * SlashML Robotics TypeScript SDK.
 *
 * Provides spatial primitives, 6-DoF poses, and dynamic belief tracking
 * for fleet management dashboards, Foxglove Studio, and WebRTC teleoperation consoles.
 */
export interface Pose6D {
    x: number;
    y: number;
    z: number;
    qx?: number;
    qy?: number;
    qz?: number;
    qw?: number;
}
export declare function distancePose6D(a: Pose6D, b: Pose6D): number;
export interface Waypoint {
    timestamp: number;
    roomZone: string;
    pose: Pose6D;
    confidence: number;
}
export interface LocationResult {
    objectName: string;
    roomZone: string;
    pose: Pose6D;
    timestamp: number;
    confidence: number;
    isSuperseded: boolean;
    observationId: string;
}
export interface Trajectory {
    objectName: string;
    waypoints: Waypoint[];
}
export declare class RoboticMemoryClient {
    private baseUrl;
    private apiKey;
    private robotId;
    private obsCounter;
    private activeBeliefs;
    private trajectories;
    constructor(options?: {
        baseUrl?: string;
        apiKey?: string;
        robotId?: string;
    });
    addObservation(params: {
        objectName: string;
        roomZone: string;
        pose: Pose6D;
        tags?: string[];
        confidence?: number;
        timestamp?: number;
    }): LocationResult;
    whereIs(objectName: string): LocationResult | null;
    getTrajectory(objectName: string): Trajectory;
}
