"""
Secondary UDP Input Receiver Module

Receives control corrections via UDP and applies adjustment logic.

Input Format: {"dx": <int>, "dy": <int>}
"""

import socket
import json
import time
from multiprocessing import Process

import config


# Throttle control state (persistent between calls)
_throttle_state = {
    "integral": 0.0,      # Integral term for I control
    "last_error": 0.0,    # Previous error for D control
    "last_time": 0.0,     # Last update time
    "current_pitch": 0.0  # Current pitch value for ramping
}


def reset_pitch_ramp():
    """Reset pitch ramp to zero when switching to UDP mode."""
    _throttle_state["current_pitch"] = 0.0


def apply_correction_logic(dx: int, dy: int, shared_state: dict = None) -> tuple:
    """
    Apply adjustment logic to incoming correction values.
    
    This is where you can add filtering, scaling, deadbands, 
    rate limiting, or other processing logic.
    
    Args:
        dx: Raw correction value for roll
        dy: Raw correction value for pitch
        shared_state: Shared state dict for reset signals
    
    Returns:
        (roll, pitch, yaw, throttle) tuple of normalized values (-1.0 to 1.0)
    """
    # Check for pitch reset signal from router
    if shared_state and shared_state.get("reset_pitch_ramp", False):
        _throttle_state["current_pitch"] = 0.0
        shared_state["reset_pitch_ramp"] = False
        print("[UDP Input] Pitch ramp reset to 0")
    
    # Roll/Yaw control based on dx
    max_correction = 1000  # Max correction value
    if dx > 10:
        roll = min(max_correction, dx * 40)
        yaw = min(max_correction, dx * 40)
    elif dx < -10:
        roll = max(-max_correction, dx * 40)
        yaw = max(-max_correction, dx * 40)
    else:
        roll = 0.0
        yaw = 0.0

    # ===== PITCH RAMPING =====
    target_pitch = 20000
    ramp_rate = 200  # Units per update (adjust for faster/slower ramp)
    
    current_pitch = _throttle_state["current_pitch"]
    
    # Ramp towards target
    if current_pitch < target_pitch:
        current_pitch = min(current_pitch + ramp_rate, target_pitch)
    elif current_pitch > target_pitch:
        current_pitch = max(current_pitch - ramp_rate, target_pitch)
    
    _throttle_state["current_pitch"] = current_pitch
    pitch = current_pitch
    
    # ===== THROTTLE ALGORITHM - PID Controller =====
    hover_throttle = 1550  # Fixed baseline throttle
    target_dy = 100  # Target position (negative = target above center)
    
    # PID gains - MORE AGGRESSIVE (increased for faster response, less overshoot)
    Kp = 500.0   # Proportional gain - much more aggressive immediate response
    Ki = 20.0    # Integral gain - faster correction of steady-state error
    Kd = 80.0   # Derivative gain - stronger dampening to prevent overshoot
    
    # Calculate error (how far we are from target)
    error = target_dy - dy
    
    # Time delta for integral/derivative
    current_time = time.time()
    dt = current_time - _throttle_state["last_time"]
    if _throttle_state["last_time"] == 0.0 or dt > 1.0:
        dt = 0.02  # Default to 50Hz if first call or too long
    _throttle_state["last_time"] = current_time
    
    # Proportional term
    P = Kp * error
    
    # Integral term (accumulated error over time)
    _throttle_state["integral"] += error * dt
    # Anti-windup: clamp integral to prevent runaway (tighter limit)
    _throttle_state["integral"] = max(-200, min(200, _throttle_state["integral"]))
    I = Ki * _throttle_state["integral"]
    
    # Derivative term (rate of change of error)
    D = Kd * (error - _throttle_state["last_error"]) / dt if dt > 0 else 0.0
    _throttle_state["last_error"] = error
    
    # Calculate throttle: baseline + PID adjustment
    throttle_adjustment = P + I + D
    throttle = hover_throttle + throttle_adjustment
    
    # Clamp to safe limits
    throttle = max(-30000, min(30000, throttle))
    
    # Debug output (uncomment to tune)
    #print(f"dy={dy:4d} err={error:6.1f} P={P:6.1f} I={I:6.1f} D={D:6.1f} thr={throttle:6.0f}")
    print(f"Pitch: {pitch:6.0f}, Throttle: {throttle:6.0f}")
    return roll, pitch, throttle, yaw


def process_udp_input(data: dict, shared_state: dict) -> None:
    """Process incoming UDP data and update shared state."""
    dx = data.get("dx", 0)
    dy = data.get("dy", 0)
    
    # Apply correction logic
    roll, pitch, yaw, throttle = apply_correction_logic(dx, dy, shared_state)
    
    # Update shared state
    channels = [0.0] * config.NUM_CHANNELS
    channels[config.CHANNEL_ROLL] = roll
    channels[config.CHANNEL_PITCH] = pitch
    channels[config.CHANNEL_YAW] = yaw
    channels[config.CHANNEL_THROTTLE] = throttle
    
    shared_state["udp_channels"] = channels
    shared_state["udp_last_update"] = time.time()


def udp_input_receiver_loop(shared_state: dict, verbose: bool = False) -> None:
    """Main UDP receiver loop."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", config.CONTROL_UDP_PORT))
    sock.settimeout(config.UDP_RECV_TIMEOUT)
    
    print(f"[UDPInputReceiver] Listening on port {config.CONTROL_UDP_PORT}")
    
    packet_count = 0
    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                packet_count += 1
                
                if verbose:
                    print(f"[DEBUG] Packet #{packet_count}: {data[:100]}")
                
                try:
                    input_data = json.loads(data.decode("utf-8"))
                    if verbose:
                        print(f"[DEBUG] Parsed: {input_data}")
                    process_udp_input(input_data, shared_state)
                except json.JSONDecodeError as e:
                    print(f"[UDPInputReceiver] Parse error: {e} | Raw: {data}")
                    
            except socket.timeout:
                pass  # Expected - retains last values
                
    except KeyboardInterrupt:
        print("\n[UDPInputReceiver] Shutting down...")
    finally:
        sock.close()


def start_udp_input_receiver(shared_state: dict) -> Process:
    """Start UDP receiver as separate process."""
    process = Process(
        target=udp_input_receiver_loop,
        args=(shared_state,),
        name="UDPInputReceiver",
        daemon=True
    )
    process.start()
    return process


if __name__ == "__main__":
    """Standalone test mode - prints received values in real-time."""
    from multiprocessing import Manager
    
    manager = Manager()
    shared_state = manager.dict()
    shared_state["udp_channels"] = [0.0] * config.NUM_CHANNELS
    shared_state["udp_last_update"] = 0.0
    
    print(f"[TEST] UDP Input Receiver - Listening on port {config.CONTROL_UDP_PORT}")
    print(f"[TEST] Send test: echo '{{\"dx\": 50, \"dy\": -30}}' | nc -u 127.0.0.1 {config.CONTROL_UDP_PORT}\n")
    
    def monitor_values(shared_state):
        """Monitor and display received values."""
        last_channels = None
        while True:
            channels = shared_state.get("udp_channels", [0.0] * config.NUM_CHANNELS)
            if channels != last_channels:
                print(f"[RECEIVED] Roll: {channels[0]:+.3f}, Pitch: {channels[1]:+.3f}, "
                      f"Yaw: {channels[2]:+.3f}, Throttle: {channels[3]:+.3f}")
                last_channels = list(channels)
            time.sleep(0.1)
    
    Process(target=monitor_values, args=(shared_state,), daemon=True).start()
    udp_input_receiver_loop(shared_state, verbose=True)