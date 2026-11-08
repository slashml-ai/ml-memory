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

export function createPose6D(
  x: number,
  y: number,
  z: number,
  qx: number = 0,
  qy: number = 0,
  qz: number = 0,
  qw: number = 1
): Pose6D {
  return { x, y, z, qx, qy, qz, qw };
}


export function distancePose6D(a: Pose6D, b: Pose6D): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

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

export class RoboticMemoryClient {
  private baseUrl: string;
  private apiKey: string;
  private robotId: string;
  private obsCounter = 0;
  private activeBeliefs = new Map<string, LocationResult>();
  private trajectories = new Map<string, Waypoint[]>();

  constructor(options?: { baseUrl?: string; apiKey?: string; robotId?: string }) {
    this.baseUrl = options?.baseUrl || 'http://localhost:8000';
    this.apiKey = options?.apiKey || '';
    this.robotId = options?.robotId || 'robot_default';
  }

  public addObservation(params: {
    objectName: string;
    roomZone: string;
    pose: Pose6D;
    tags?: string[];
    confidence?: number;
    timestamp?: number;
  }): LocationResult {
    const ts = params.timestamp !== undefined ? params.timestamp : Date.now() / 1000;
    const conf = params.confidence !== undefined ? params.confidence : 1.0;
    this.obsCounter += 1;
    const obsId = `ts_obs_${this.obsCounter}`;

    const loc: LocationResult = {
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

  public whereIs(objectName: string): LocationResult | null {
    return this.activeBeliefs.get(objectName) || null;
  }

  public getTrajectory(objectName: string): Trajectory {
    const waypoints = (this.trajectories.get(objectName) || []).slice();
    waypoints.sort((a, b) => a.timestamp - b.timestamp);
    return {
      objectName,
      waypoints,
    };
  }

  public async addObservationRemote(params: {
    objectName: string;
    roomZone: string;
    pose: Pose6D;
    tags?: string[];
    confidence?: number;
    timestamp?: number;
  }): Promise<LocationResult> {
    const p = params.pose;
    const poseArray = [
      p.x,
      p.y,
      p.z,
      p.qx ?? 0,
      p.qy ?? 0,
      p.qz ?? 0,
      p.qw ?? 1,
    ];
    const payload = {
      object_name: params.objectName,
      room_zone: params.roomZone,
      pose: poseArray,
      confidence: params.confidence ?? 1.0,
      tags: params.tags ?? [],
      timestamp: params.timestamp,
    };
    const res = await fetch(`${this.baseUrl}/v1/robotics/observations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to add observation: ${res.status} ${await res.text()}`);
    }
    const data = (await res.json()) as any;
    return {
      objectName: data.object_name,
      roomZone: data.room_zone,
      pose: {
        x: data.pose.x,
        y: data.pose.y,
        z: data.pose.z,
        qx: data.pose.qx,
        qy: data.pose.qy,
        qz: data.pose.qz,
        qw: data.pose.qw,
      },
      timestamp: data.timestamp,
      confidence: data.confidence,
      isSuperseded: data.is_superseded,
      observationId: data.observation_id,
    };
  }

  public async whereIsRemote(objectName: string): Promise<LocationResult | null> {
    const res = await fetch(
      `${this.baseUrl}/v1/robotics/where_is/${encodeURIComponent(objectName)}`,
      {
        headers: { Authorization: `Bearer ${this.apiKey}` },
      }
    );
    if (res.status === 404) {
      return null;
    }
    if (!res.ok) {
      throw new Error(`Failed to query location: ${res.status} ${await res.text()}`);
    }
    const data = (await res.json()) as any;
    return {
      objectName: data.object_name,
      roomZone: data.room_zone,
      pose: {
        x: data.pose.x,
        y: data.pose.y,
        z: data.pose.z,
        qx: data.pose.qx,
        qy: data.pose.qy,
        qz: data.pose.qz,
        qw: data.pose.qw,
      },
      timestamp: data.timestamp,
      confidence: data.confidence,
      isSuperseded: data.is_superseded,
      observationId: data.observation_id,
    };
  }

  public async getTrajectoryRemote(objectName: string): Promise<Trajectory> {
    const res = await fetch(
      `${this.baseUrl}/v1/robotics/trajectory/${encodeURIComponent(objectName)}`,
      {
        headers: { Authorization: `Bearer ${this.apiKey}` },
      }
    );
    if (!res.ok) {
      throw new Error(`Failed to query trajectory: ${res.status} ${await res.text()}`);
    }
    const data = (await res.json()) as any;
    return {
      objectName: data.object_name,
      waypoints: (data.waypoints || []).map((wp: any) => ({
        timestamp: wp.timestamp,
        roomZone: wp.room_zone,
        pose: {
          x: wp.pose.x,
          y: wp.pose.y,
          z: wp.pose.z,
          qx: wp.pose.qx,
          qy: wp.pose.qy,
          qz: wp.pose.qz,
          qw: wp.pose.qw,
        },
        confidence: wp.confidence,
      })),
    };
  }

  public async findByAffordanceRemote(action: string): Promise<LocationResult[]> {
    const res = await fetch(
      `${this.baseUrl}/v1/robotics/affordance/${encodeURIComponent(action)}`,
      {
        headers: { Authorization: `Bearer ${this.apiKey}` },
      }
    );
    if (!res.ok) {
      throw new Error(`Failed to query affordance: ${res.status} ${await res.text()}`);
    }
    const data = (await res.json()) as any;
    const items = data.matches || data.objects || [];
    return items.map((m: any) => ({
      objectName: m.object_name,
      roomZone: m.room_zone,
      pose: {
        x: m.pose.x,
        y: m.pose.y,
        z: m.pose.z,
        qx: m.pose.qx,
        qy: m.pose.qy,
        qz: m.pose.qz,
        qw: m.pose.qw,
      },
      timestamp: m.timestamp,
      confidence: m.confidence,
      isSuperseded: m.is_superseded,
      observationId: m.observation_id,
    }));
  }
}

