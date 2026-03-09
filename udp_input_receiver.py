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
    "current_pitch": 0.0, # Current pitch value for ramping
    "initial_dy": None,   # Initial dy value when switching to UDP mode
    "filtered_dy": None,  # EMA-filtered dy used only for D term
}


def reset_pitch_ramp():
    """Reset pitch ramp to zero when switching to UDP mode."""
    _throttle_state["current_pitch"] = 0.0
    _throttle_state["initial_dy"] = None
    _throttle_state["filtered_dy"] = None  # Reset EMA so it seeds cleanly
    _throttle_state["integral"] = 0.0      # Clear integrator windup
    _throttle_state["last_error"] = 0.0
    _throttle_state["last_time"] = 0.0
    # print("[UDP Input] Pitch ramp reset to 0")


def apply_correction_logic(dx: int, dy: int, bw: int, bh: int, shared_state: dict = None) -> tuple:
    """
    Apply adjustment logic to incoming correction values.
    
    This is where you can add filtering, scaling, deadbands, 
    rate limiting, or other processing logic.
    
    Args:
        dx: Raw correction value for roll
        dy: Raw correction value for pitch/throttle
        shared_state: Shared state dict for reset signals
    
    Returns:
        (roll, pitch, throttle, yaw) tuple of real control values
    """
    
    # Print joystick channel values if available
    if shared_state:
        joystick_channels = shared_state.get("joystick_channels", [0.0] * config.NUM_CHANNELS)
        if False:
            print(f"[UDP Input] Joystick channels: Roll={joystick_channels[0]:+8.1f}, "
              f"Pitch={joystick_channels[1]:+8.1f}, Throttle={joystick_channels[2]:+8.1f}, "
              f"Yaw={joystick_channels[3]:+8.1f}")
    
    # Check for pitch reset signal from router
    if shared_state and shared_state.get("reset_pitch_ramp", False):
        # Start pitch ramp from current joystick pitch to avoid jerk
        if shared_state:
            joystick_channels = shared_state.get("joystick_channels", [0.0] * config.NUM_CHANNELS)
            joystick_pitch = joystick_channels[config.CHANNEL_PITCH]
            _throttle_state["current_pitch"] = joystick_pitch
            #print(f"[UDP Input] Starting pitch ramp from joystick pitch: {joystick_pitch:.1f}")
        else:
            _throttle_state["current_pitch"] = 0.0
        
        _throttle_state["initial_dy"] = None
        _throttle_state["filtered_dy"] = None  # Reset EMA filter
        _throttle_state["integral"] = 0.0       # Clear integrator
        _throttle_state["last_error"] = 0.0
        _throttle_state["last_time"] = 0.0
        shared_state["reset_pitch_ramp"] = False
        
    
    # Roll/Yaw control based on dx
    max_correction = 2500  # Max correction value
    if dx > 10:
        roll = min(max_correction, dx * 40)
        yaw = min(max_correction, dx * 40)
    elif dx < -10:
        roll = max(-max_correction, dx * 40)
        yaw = max(-max_correction, dx * 40)
    else:
        roll = 0.0
        yaw = 0.0

    roll_multiplier = 3.0
    roll = roll * roll_multiplier


    # ===== PITCH RAMPING =====
    target_pitch = 23000
    ramp_rate = 300  # Units per update (adjust for faster/slower ramp)
    
    current_pitch = _throttle_state["current_pitch"]
    
    # Ramp towards target
    if current_pitch < target_pitch:
        current_pitch = min(current_pitch + ramp_rate, target_pitch)
    elif current_pitch > target_pitch:
        current_pitch = max(current_pitch - ramp_rate, target_pitch)
    
    _throttle_state["current_pitch"] = current_pitch
    pitch = current_pitch
    pitch_ratio = pitch / target_pitch if target_pitch != 0 else 0.0
    #print(f"Pitch ramp: {pitch:.1f} (ratio: {pitch_ratio:.3f})")
    
    # ===== THROTTLE ALGORITHM - PID Controller with Soft Target =====
    #hover_throttle = -23000  # Fixed baseline throttle
    hover_throttle = -15000  # Fixed baseline throttle
    final_target_dy = 40 # Final target position (negative = target above center)
    
    # Capture initial dy value when first switching to UDP mode
    if _throttle_state["initial_dy"] is None:
        _throttle_state["initial_dy"] = dy
        #print(f"[UDP Input] Captured initial dy: {dy}")
    
    # Gradually transition target_dy from initial position to final target as pitch ramps up
    # This prevents the PID from fighting the changing drone position during pitch ramp
    initial_dy = _throttle_state["initial_dy"]
    target_dy = initial_dy + (final_target_dy - initial_dy) * pitch_ratio
    
    #print(f"Soft target: initial={initial_dy:.1f}, current_target={target_dy:.1f}, final={final_target_dy:.1f}, ratio={pitch_ratio:.3f}")

    print(f"dy: {dy:4d}  target: {target_dy:6.1f}  err: {target_dy - dy:6.1f}")

    # PID gains
    Kp = 50.0   # Proportional - on raw dy, stays snappy near target
    Ki = 20.0   # Integral - steady-state correction
    Kd = 80.0   # Derivative - on EMA-filtered dy only, kills noise spikes

    # Error for P and I uses raw dy so response is immediate when near target
    error = target_dy - dy

    # EMA filter on dy for D term only (alpha=0.5: fast enough to track, smooth enough for D)
    # This stops 1px noise bounces from causing 4000-unit throttle spikes via D
    EMA_ALPHA = 0.5
    if _throttle_state["filtered_dy"] is None:
        _throttle_state["filtered_dy"] = float(dy)
    _throttle_state["filtered_dy"] = EMA_ALPHA * dy + (1.0 - EMA_ALPHA) * _throttle_state["filtered_dy"]
    filtered_error = target_dy - _throttle_state["filtered_dy"]

    # Time delta for integral/derivative
    current_time = time.time()
    dt = current_time - _throttle_state["last_time"]
    if _throttle_state["last_time"] == 0.0 or dt > 1.0:
        dt = 0.02  # Default to 50Hz if first call or too long
    _throttle_state["last_time"] = current_time

    # Proportional term (raw - fast response)
    P = Kp * error

    # Integral term (raw - accumulated error over time)
    _throttle_state["integral"] += error * dt
    # Anti-windup: clamp integral to prevent runaway
    _throttle_state["integral"] = max(-200, min(200, _throttle_state["integral"]))
    I = Ki * _throttle_state["integral"]

    # Derivative term (filtered - rate of change without noise amplification)
    D = Kd * (filtered_error - _throttle_state["last_error"]) / dt if dt > 0 else 0.0
    _throttle_state["last_error"] = filtered_error
    
    # Calculate throttle: baseline + PID adjustment
    throttle_adjustment = P + I + D
    throttle = hover_throttle + throttle_adjustment
    
    # Clamp to safe limits
    throttle = max(-32000, min(32000, throttle))
    
    # Debug output (uncomment to tune)
    #print(f"dy={dy:4d} err={error:6.1f} P={P:6.1f} I={I:6.1f} D={D:6.1f} thr={throttle:6.0f}")
    #print(f"Pitch: {pitch:6.0f}, Throttle: {throttle:6.0f}")


    return roll, pitch, throttle, yaw


def process_udp_input(data: dict, shared_state: dict) -> None:
    """Process incoming UDP data and update shared state."""
    # bx : x position   by : y position   bw : box width   bh : box height
    dx = data.get("dx", 0)
    dy = data.get("dy", 0)
    bw = data.get("bw", 0)
    bh = data.get("bh", 0)

    #print(f"[UDP Input] Received dx={dx}, dy={dy}, bw={bw}, bh={bh}")
    
    # Apply correction logic
    roll, pitch, throttle, yaw = apply_correction_logic(dx, dy, bw, bh, shared_state)
    
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