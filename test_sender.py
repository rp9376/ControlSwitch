#!/usr/bin/env python3
"""
Test Sender Utility

Simulates input sources for testing the command switch system.
Can send simulated joystick events, UDP control input, and switch toggles.

Usage:
    python test_sender.py --mode joystick     # Simulate joystick axis movements
    python test_sender.py --mode udp          # Simulate UDP control input (dx, dy)
    python test_sender.py --mode switch       # Toggle the input switch
    python test_sender.py --mode all          # Run all simulations concurrently
"""

import socket
import json
import time
import argparse
import math
import threading

import config


def send_joystick_event(sock, event_type: int, number: int, value: int, addr: tuple):
    """Send a single joystick event."""
    event = {
        "type": event_type,
        "time": int(time.time() * 1000),
        "number": number,
        "value": value
    }
    data = json.dumps(event).encode("utf-8")
    sock.sendto(data, addr)


def simulate_joystick(duration: float = 30.0):
    """
    Simulate joystick axis movements.
    
    Sends sinusoidal movements on all 4 axes.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = ("127.0.0.1", config.JOYSTICK_UDP_PORT)
    
    print(f"[TestSender] Simulating joystick on port {config.JOYSTICK_UDP_PORT}")
    print("[TestSender] Press Ctrl+C to stop")
    
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            t = time.time() - start_time
            
            # Generate sine wave values for each axis (different frequencies)
            roll_val = int(math.sin(t * 1.0) * 20000)
            pitch_val = int(math.sin(t * 0.7) * 20000)
            yaw_val = int(math.sin(t * 0.5) * 15000)
            throttle_val = int(math.sin(t * 0.3) * 10000)
            
            # Send axis events
            send_joystick_event(sock, config.EVENT_TYPE_AXIS, 0, roll_val, addr)
            send_joystick_event(sock, config.EVENT_TYPE_AXIS, 1, pitch_val, addr)
            send_joystick_event(sock, config.EVENT_TYPE_AXIS, 2, yaw_val, addr)
            send_joystick_event(sock, config.EVENT_TYPE_AXIS, 3, throttle_val, addr)
            
            time.sleep(0.02)  # 50 Hz update rate
            
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("[TestSender] Joystick simulation stopped")


def simulate_udp_input(duration: float = 30.0):
    """
    Simulate secondary UDP control input.
    
    Sends dx, dy values simulating some external control source.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = ("127.0.0.1", config.CONTROL_UDP_PORT)
    
    print(f"[TestSender] Simulating UDP input on port {config.CONTROL_UDP_PORT}")
    print("[TestSender] Press Ctrl+C to stop")
    
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            t = time.time() - start_time
            
            # Generate smooth movements
            dx = int(math.sin(t * 2.0) * 50)
            dy = int(math.cos(t * 1.5) * 50)
            
            message = {"dx": dx, "dy": dy}
            data = json.dumps(message).encode("utf-8")
            sock.sendto(data, addr)
            
            time.sleep(0.05)  # 20 Hz update rate
            
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("[TestSender] UDP input simulation stopped")


def simulate_switch_toggle(interval: float = 3.0, count: int = 10):
    """
    Simulate switch toggles between JOYSTICK and UDP modes.
    
    Args:
        interval: Seconds between toggles
        count: Number of toggles
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = ("127.0.0.1", config.JOYSTICK_UDP_PORT)
    
    print(f"[TestSender] Simulating switch toggles every {interval}s")
    print("[TestSender] Press Ctrl+C to stop")
    
    switch_state = True  # True = JOYSTICK mode
    
    try:
        for i in range(count):
            # Toggle switch
            switch_state = not switch_state
            value = 32000 if switch_state else -32000
            
            mode = "JOYSTICK" if switch_state else "UDP"
            print(f"[TestSender] Switch -> {mode}")
            
            send_joystick_event(
                sock, 
                config.EVENT_TYPE_AXIS,  # Switch is a channel like any other
                config.SWITCH_BUTTON_NUMBER,
                value,
                addr
            )
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("[TestSender] Switch simulation stopped")


def simulate_all():
    """Run all simulations concurrently in separate threads."""
    print("[TestSender] Running all simulations concurrently")
    
    threads = [
        threading.Thread(target=simulate_joystick, args=(60.0,), daemon=True),
        threading.Thread(target=simulate_udp_input, args=(60.0,), daemon=True),
        threading.Thread(target=simulate_switch_toggle, args=(5.0, 12), daemon=True),
    ]
    
    for t in threads:
        t.start()
    
    try:
        # Wait for switch simulation to complete
        threads[2].join()
    except KeyboardInterrupt:
        print("\n[TestSender] Stopping all simulations...")


def receive_output():
    """Listen for and display output from the command switch system."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", config.OUTPUT_UDP_PORT))
    sock.settimeout(0.5)
    
    print(f"[TestSender] Receiving output on port {config.OUTPUT_UDP_PORT}")
    print("[TestSender] Press Ctrl+C to stop")
    
    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = json.loads(data.decode("utf-8"))
                channels = message.get("channels", [])
                print(f"[Output] channels={channels}")
            except socket.timeout:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("[TestSender] Output receiver stopped")


def main():
    parser = argparse.ArgumentParser(description="Test sender for command switch system")
    parser.add_argument(
        "--mode",
        choices=["joystick", "udp", "switch", "all", "receive"],
        default="all",
        help="Simulation mode: joystick, udp, switch, all, or receive"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Duration in seconds for continuous simulations"
    )
    
    args = parser.parse_args()
    
    if args.mode == "joystick":
        simulate_joystick(args.duration)
    elif args.mode == "udp":
        simulate_udp_input(args.duration)
    elif args.mode == "switch":
        simulate_switch_toggle()
    elif args.mode == "all":
        simulate_all()
    elif args.mode == "receive":
        receive_output()


if __name__ == "__main__":
    main()
