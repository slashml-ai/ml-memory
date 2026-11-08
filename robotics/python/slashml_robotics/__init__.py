"""SlashML Robotics: Ultra-low-latency spatial memory SDK for embodied AI.

Public interface for physical robotics stacks, perception pipelines, and task planners.
"""

from slashml_robotics.client import RoboticMemory
from slashml_robotics.types import (
    BoundingBox3D,
    LocationResult,
    PhysicalObservation,
    Pose6D,
    Trajectory,
    Waypoint,
)
from slashml_robotics.vocabulary import (
    AFFORDANCES_AND_STATES,
    AFFORDANCE_TO_OBJECTS,
    CONTAINERS_AND_STORAGE,
    ELECTRONICS_AND_COMPONENTS,
    TOOLS_AND_HARDWARE,
    ZONES_AND_FURNITURE,
    get_objects_for_affordance,
    is_known_tool,
)

__version__ = "1.0.0"

__all__ = [
    "RoboticMemory",
    "Pose6D",
    "BoundingBox3D",
    "Waypoint",
    "LocationResult",
    "Trajectory",
    "PhysicalObservation",
    "get_objects_for_affordance",
    "is_known_tool",
    "TOOLS_AND_HARDWARE",
    "CONTAINERS_AND_STORAGE",
    "ELECTRONICS_AND_COMPONENTS",
    "ZONES_AND_FURNITURE",
    "AFFORDANCES_AND_STATES",
    "AFFORDANCE_TO_OBJECTS",
]
