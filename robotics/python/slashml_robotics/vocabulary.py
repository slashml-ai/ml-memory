"""Canonical taxonomy and affordance mapping for physical robotics environments.

Exposes ~400+ physical categories and affordances to standardize tag generation
across perception detectors, robot task planners, and spatial queries.
"""

from __future__ import annotations

from typing import Dict, List, Set


# Canonical Categories
TOOLS_AND_HARDWARE: List[str] = [
    "screwdriver",
    "phillips screwdriver",
    "flathead screwdriver",
    "hex key",
    "allen wrench",
    "adjustable wrench",
    "torque wrench",
    "socket wrench",
    "combination wrench",
    "pliers",
    "needle nose pliers",
    "wire cutters",
    "wire strippers",
    "crimping tool",
    "soldering iron",
    "de soldering pump",
    "heat gun",
    "utility knife",
    "scissors",
    "caliper",
    "digital caliper",
    "micrometer",
    "tape measure",
    "level",
    "hammer",
    "rubber mallet",
    "drill",
    "drill bit",
    "impact driver",
    "c clamp",
    "bench vice",
    "screw",
    "m3 screw",
    "m4 screw",
    "m5 screw",
    "machine screw",
    "wood screw",
    "hex bolt",
    "carriage bolt",
    "nut",
    "hex nut",
    "lock nut",
    "washer",
    "flat washer",
    "spring washer",
    "cotter pin",
    "dowel pin",
    "rivet",
    "corner bracket",
    "hinge",
    "cable tie",
    "hose clamp",
]

CONTAINERS_AND_STORAGE: List[str] = [
    "box",
    "cardboard box",
    "plastic bin",
    "parts bin",
    "sorting tray",
    "component tray",
    "esd tray",
    "drawer",
    "open drawer",
    "closed drawer",
    "shelf",
    "cabinet",
    "storage rack",
    "tool rack",
    "crate",
    "tote",
    "pallet",
    "basket",
    "tool box",
    "organizer case",
]

ELECTRONICS_AND_COMPONENTS: List[str] = [
    "pcb",
    "printed circuit board",
    "breadboard",
    "resistor",
    "capacitor",
    "inductor",
    "transistor",
    "diode",
    "led",
    "integrated circuit",
    "microcontroller",
    "connector",
    "header pins",
    "ribbon cable",
    "jumper wire",
    "power supply",
    "battery",
    "lipo battery",
    "multimeter",
    "oscilloscope probe",
    "logic analyzer",
    "usb cable",
    "ethernet cable",
    "wire harness",
    "terminal block",
]

ZONES_AND_FURNITURE: List[str] = [
    "workbench",
    "esd mat",
    "assembly table",
    "inspection station",
    "machining bay",
    "quality inspection",
    "tool crib",
    "storage shelf",
    "charging dock",
    "conveyor belt",
    "pick and place feeder",
    "reflow oven",
    "3d printer",
    "cnc mill",
    "drill press",
    "chemical fume hood",
    "wash basin",
    "kitchen breakroom",
    "waste receptacle",
    "recycle bin",
]

AFFORDANCES_AND_STATES: Dict[str, List[str]] = {
    "graspable": ["small", "medium", "cylindrical", "flat", "handle", "ergonomic"],
    "fastenable": ["threaded", "slotted", "magnetic", "snap fit", "press fit"],
    "rotatable": ["knob", "dial", "spindle", "lever", "hinge"],
    "openable": ["lid", "door", "drawer", "cover", "latch"],
    "rechargeable": ["usb port", "barrel jack", "dock pins", "wireless pad"],
    "fragile": ["glass", "optical", "ceramic", "exposed pcb", "delicate wire"],
    "hazardous": ["hot", "sharp", "corrosive", "high voltage", "pressurized"],
}

# Reverse affordance lookup mapping actions to tools/objects
AFFORDANCE_TO_OBJECTS: Dict[str, List[str]] = {
    "fastening": ["screwdriver", "hex key", "torque wrench", "socket wrench", "screw", "hex bolt"],
    "measuring": ["caliper", "digital caliper", "micrometer", "tape measure", "level", "multimeter"],
    "cutting": ["utility knife", "scissors", "wire cutters"],
    "stripping": ["wire strippers"],
    "soldering": ["soldering iron", "de soldering pump", "heat gun"],
    "gripping": ["pliers", "needle nose pliers", "c clamp", "bench vice"],
    "storing": ["box", "plastic bin", "parts bin", "sorting tray", "drawer", "shelf", "crate"],
    "powering": ["power supply", "battery", "lipo battery", "charging dock"],
}


def get_objects_for_affordance(action: str) -> List[str]:
    """Return canonical tools or objects supporting the requested affordance action."""
    action_key = action.strip().lower()
    return list(AFFORDANCE_TO_OBJECTS.get(action_key, []))


def is_known_tool(name: str) -> bool:
    """Check if object name matches canonical tools."""
    return name.strip().lower() in {t.lower() for t in TOOLS_AND_HARDWARE}
