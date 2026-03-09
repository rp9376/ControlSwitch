"""
Physical Joystick Direct Reader Module

Reads joystick events directly from /dev/input/js0 using jstest --event.
Parses event output and updates shared state with normalized channel values.

Input Format (from jstest --event):
Event: type 2, time 3656941, number 1, value -171
  type: 1=button, 2=axis
  time: timestamp in milliseconds
  number: axis/button identifier
  value: raw value (-32767 to 32767 for axes)

Design Decisions:
- Runs as separate process for true concurrency
- Reads directly from joystick device (no UDP needed)
- Updates shared state atomically
- Normalizes joystick values to -1.0 to 1.0 range
- Detects switch channel and updates routing mode
"""

import re
import subprocess
import time
from multiprocessing import Process

import config

# Pattern to match jstest --event output
# Example: Event: type 2, time 3656941, number 1, value -171
EVENT_PATTERN = re.compile(
    r'Event: type\s+(\d+),\s+time\s+(\d+),\s+number\s+(\d+),\s+value\s+([-]?\d+)'
)


def normalize_value(raw_value: int) -> float:
    """
    Normalize raw joystick value to -1.0 to 1.0 range.
    
    Args:
        raw_value: Raw joystick value (typically -32767 to 32767)
    
    Returns:
        Normalized float value between -1.0 and 1.0
    """
    # Clamp to expected range
    clamped = max(config.JOYSTICK_RAW_MIN, min(config.JOYSTICK_RAW_MAX, raw_value))
    
    # Normalize to -1.0 to 1.0
    normalized = clamped / config.JOYSTICK_RAW_MAX
    
    return normalized


def process_joystick_event(event: dict, shared_state: dict) -> None:
    """
    Process a single joystick event and update shared state.
    
    Args:
        event: Parsed JSON event with type, time, number, value
        shared_state: Multiprocessing Manager dict for shared state
    """
    event_type = event.get("type")
    number = event.get("number")
    value = event.get("value", 0)
    
    # Check if this is the routing switch (BUTTON event)
    if event_type == config.EVENT_TYPE_BUTTON and number == config.SWITCH_BUTTON_NUMBER:
        # Button pressed = UDP mode, Released = Joystick mode
        if value > config.SWITCH_THRESHOLD:
            shared_state["switch_state"] = config.MODE_UDP
        else:
            shared_state["switch_state"] = config.MODE_JOYSTICK
        return
    
    # Store ALL button events for passthrough (except the mode switch button)
    if event_type == config.EVENT_TYPE_BUTTON:
        buttons = dict(shared_state.get("joystick_buttons", {}))
        buttons[number] = value
        shared_state["joystick_buttons"] = buttons
        return
    
    # Process axis events for control channels
    if event_type == config.EVENT_TYPE_AXIS:
        # Check if this axis maps to a known channel
        if number in config.JOYSTICK_AXIS_MAP:
            channel_idx = config.JOYSTICK_AXIS_MAP[number]
            # Pass through raw values without normalization
            
            # Update the channel in shared state
            # We need to get, modify, and set the list atomically
            channels = list(shared_state["joystick_channels"])
            channels[channel_idx] = value  # Use raw value directly
            shared_state["joystick_channels"] = channels
            shared_state["joystick_last_update"] = time.time()
        else:
            # Store unmapped axes for passthrough
            other_axes = dict(shared_state.get("joystick_other_axes", {}))
            other_axes[number] = value
            shared_state["joystick_other_axes"] = other_axes


def joystick_receiver_loop(shared_state: dict, device: str = "/dev/input/js0", verbose: bool = False) -> None:
    """
    Main loop for joystick direct reader.
    
    Reads joystick events directly from device using jstest --event.
    Updates shared state with normalized channel values.
    Runs until terminated.
    
    Args:
        shared_state: Multiprocessing Manager dict for shared state
        device: Path to joystick device (default: /dev/input/js0)
        verbose: Print joystick events to console (default: False)
    """
    print(f"[JoystickReceiver] Reading from {device} using jstest")
    
    channel_names = ["Roll", "Pitch", "Throttle", "Yaw"]
    
    try:
        # Start jstest as a subprocess
        process = subprocess.Popen(
            ["jstest", "--event", device],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Read output line by line
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            match = EVENT_PATTERN.search(line)
            if match:
                event_type, time, number, value = match.groups()
                # Convert to integers
                event = {
                    "type": int(event_type),
                    "time": int(time),
                    "number": int(number),
                    "value": int(value)
                }
                
                # Print events if verbose
                if verbose:
                    evt_type = int(event_type)
                    num = int(number)
                    val = int(value)
                    
                    # Check if it's the switch button
                    if evt_type == config.EVENT_TYPE_BUTTON and num == config.SWITCH_BUTTON_NUMBER:
                        mode = "JOYSTICK" if val > config.SWITCH_THRESHOLD else "UDP"
                        print(f"[BUTTON {num}] Mode: {mode:8s} (raw: {val:6d})")
                    # Check if it's a mapped axis
                    elif evt_type == config.EVENT_TYPE_AXIS and num in config.JOYSTICK_AXIS_MAP:
                        channel_idx = config.JOYSTICK_AXIS_MAP[num]
                        normalized = normalize_value(val)
                        channel_name = channel_names[channel_idx] if channel_idx < len(channel_names) else f"Ch{channel_idx}"
                        print(f"[AXIS {num}] {channel_name:8s}: {normalized:+7.3f} (raw: {val:6d})")
                    # Print unmapped axes/buttons if desired
                    elif verbose:
                        type_name = "AXIS" if evt_type == config.EVENT_TYPE_AXIS else "BUTTON"
                        print(f"[{type_name} {num}] value: {val:6d}")
                
                # Process the event (same logic as before)
                process_joystick_event(event, shared_state)
                
    except FileNotFoundError:
        print("[JoystickReceiver] Error: jstest not found. Install with: sudo apt install joystick")
    except KeyboardInterrupt:
        print("[JoystickReceiver] Shutting down...")
    except Exception as e:
        print(f"[JoystickReceiver] Error: {e}")
    finally:
        if 'process' in locals():
            process.terminate()
            process.wait()


def start_joystick_receiver(shared_state: dict, device: str = "/dev/input/js0") -> Process:
    """
    Start the joystick receiver as a separate process.
    
    Args:
        shared_state: Multiprocessing Manager dict for shared state
        device: Path to joystick device (default: /dev/input/js0)
    
    Returns:
        Process object that can be joined/terminated
    """
    process = Process(
        target=joystick_receiver_loop,
        args=(shared_state, device),
        name="JoystickReceiver",
        daemon=True
    )
    process.start()
    return process


if __name__ == "__main__":
    """
    Test function to run joystick receiver standalone.
    Prints joystick events to console for testing.
    """
    from multiprocessing import Manager
    
    print("=" * 60)
    print("Joystick Receiver Test Mode")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print()
    
    # Create a shared state manager
    manager = Manager()
    shared_state = manager.dict()
    
    # Initialize shared state
    shared_state["joystick_channels"] = [0.0] * config.NUM_CHANNELS
    shared_state["switch_state"] = config.MODE_UDP
    shared_state["joystick_last_update"] = 0.0
    
    # Print initial state
    print(f"Device: /dev/input/js0")
    print(f"Channels: {config.NUM_CHANNELS} (Roll, Pitch, Yaw, Throttle)")
    print(f"Switch button: {config.SWITCH_BUTTON_NUMBER}")
    print(f"Axis mapping: {config.JOYSTICK_AXIS_MAP}")
    print()
    print("Monitoring joystick events...")
    print("-" * 60)
    
    try:
        # Run the receiver loop directly (not as subprocess for testing)
        joystick_receiver_loop(shared_state, verbose=True)
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("Test stopped")
        print("=" * 60)
