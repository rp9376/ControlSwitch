"""
Configuration constants for the FPV Drone Command Switch system.

This module defines all shared constants including:
- UDP port assignments
- Channel mappings and ordering
- Switch configuration
- Default values

Design Decision: Centralized configuration makes it easy to adjust
ports, mappings, and defaults without touching module logic.
"""

# =============================================================================
# UDP PORT CONFIGURATION
# =============================================================================


# Port for receiving secondary control input (dx, dy)
CONTROL_UDP_PORT = 5001

# Port for sending output commands to drone control system
OUTPUT_UDP_PORT = 5005
OUTPUT_UDP_HOST = "192.168.178.200"  # Destination for output commands

# =============================================================================
# CHANNEL CONFIGURATION
# =============================================================================

# Number of control channels (roll, pitch, yaw, throttle)
NUM_CHANNELS = 4

# Channel indices (order: roll, pitch, yaw, throttle)
CHANNEL_ROLL = 0
CHANNEL_PITCH = 1
CHANNEL_YAW = 2
CHANNEL_THROTTLE = 3

# Joystick axis number -> channel mapping
# Maps "number" field from joystick events to our channel indices
JOYSTICK_AXIS_MAP = {
    0: CHANNEL_ROLL,      # Joystick axis 0 -> Roll
    1: CHANNEL_PITCH,     # Joystick axis 1 -> Pitch
    2: CHANNEL_YAW,       # Joystick axis 2 -> Yaw
    3: CHANNEL_THROTTLE,  # Joystick axis 3 -> Throttle
}

# =============================================================================
# SWITCH CONFIGURATION
# =============================================================================

# The switch is a BUTTON on the controller for mode selection.
# This joystick button number controls input source selection.
SWITCH_BUTTON_NUMBER = 3  # Which joystick button represents the switch

# Joystick event types
EVENT_TYPE_BUTTON = 1  # Button/switch event
EVENT_TYPE_AXIS = 2    # Axis event

# Switch value thresholds for buttons
# Button pressed (value=1) = Joystick mode, Released (value=0) = UDP mode
SWITCH_THRESHOLD = 0  # Values > 0 = JOYSTICK, values <= 0 = UDP

# Routing modes
MODE_JOYSTICK = "JOYSTICK"
MODE_UDP = "UDP"

# =============================================================================
# VALUE NORMALIZATION
# =============================================================================

# Raw joystick value range (standard Linux joystick)
JOYSTICK_RAW_MIN = -32767
JOYSTICK_RAW_MAX = 32767

# Normalized output range
NORMALIZED_MIN = -1.0
NORMALIZED_MAX = 1.0

# Default channel values (neutral position)
DEFAULT_CHANNEL_VALUE = 0.0

# Throttle default (may differ from other axes)
DEFAULT_THROTTLE_VALUE = 0.0  # Or set to mid-range if needed

# =============================================================================
# TIMING
# =============================================================================

# Main loop rate (Hz) - how often router checks and sends
ROUTER_LOOP_HZ = 50

# UDP socket timeout (seconds) - prevents blocking
UDP_RECV_TIMEOUT = 0.001  # 1ms timeout for non-blocking receive

# =============================================================================
# DEFAULT CHANNEL STATE
# =============================================================================

def get_default_channels():
    """Return a fresh list of default channel values."""
    return [DEFAULT_CHANNEL_VALUE] * NUM_CHANNELS
