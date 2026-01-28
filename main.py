#!/usr/bin/env python3
"""
FPV Drone Command Switch - Main Orchestration

This is the entry point that orchestrates all modules using multiprocessing.
It creates shared state, spawns input receivers, and runs the router.

Architecture:
- Process 1: Joystick UDP receiver
- Process 2: Secondary UDP input receiver  
- Main Process: Command router + output sender

Usage:
    python main.py

To test, run test_sender.py in separate terminals to simulate inputs.
"""

import signal
import sys
from multiprocessing import Manager

import config
from joystick_receiver import start_joystick_receiver
from udp_input_receiver import start_udp_input_receiver
from router import create_router
from udp_output import UDPOutput


def create_shared_state(manager: Manager) -> dict:
    """
    Create and initialize shared state dictionary.
    
    Args:
        manager: Multiprocessing Manager instance
    
    Returns:
        Manager dict with initialized state
    """
    state = manager.dict()
    
    # Initialize joystick channels (4 axes: roll, pitch, yaw, throttle)
    state["joystick_channels"] = config.get_default_channels()
    state["joystick_last_update"] = 0.0
    
    # Initialize UDP input channels
    state["udp_channels"] = config.get_default_channels()
    state["udp_last_update"] = 0.0
    
    # Initialize switch state (default to joystick control)
    state["switch_state"] = config.MODE_JOYSTICK
    
    # Initialize pitch ramp reset flag
    state["reset_pitch_ramp"] = False
    
    # Initialize button and unmapped axis storage for passthrough
    state["joystick_buttons"] = manager.dict()  # Button states: {button_num: value}
    state["joystick_other_axes"] = manager.dict()  # Unmapped axes: {axis_num: value}
    
    return state


def main():
    """
    Main entry point for the command switch system.
    
    Sets up multiprocessing, starts receivers, and runs router.
    """
    print("=" * 60)
    print("FPV Drone Command Switch")
    print("=" * 60)
    print(f"Joystick Device:   /dev/input/js0 (direct read)")
    print(f"Control UDP Port:  {config.CONTROL_UDP_PORT}")
    print(f"Output UDP Port:   {config.OUTPUT_UDP_PORT}")
    print(f"Output Host:       {config.OUTPUT_UDP_HOST}")
    print(f"Router Rate:       {config.ROUTER_LOOP_HZ} Hz")
    print(f"Switch Button:     {config.SWITCH_BUTTON_NUMBER}")
    print("=" * 60)
    
    # Create multiprocessing manager for shared state
    manager = Manager()
    shared_state = create_shared_state(manager)
    
    # Create output sender
    output = UDPOutput()
    
    # Track processes for cleanup
    processes = []
    
    def cleanup(signum=None, frame=None):
        """Clean up processes on shutdown."""
        print("\n[Main] Shutting down...")
        for proc in processes:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1.0)
        output.close()
        print("[Main] Cleanup complete")
        sys.exit(0)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    try:
        # Start input receiver processes
        print("\n[Main] Starting input receivers...")
        
        joystick_proc = start_joystick_receiver(shared_state)
        processes.append(joystick_proc)
        
        udp_input_proc = start_udp_input_receiver(shared_state)
        processes.append(udp_input_proc)
        
        # Give receivers time to initialize
        import time
        time.sleep(0.1)
        
        # Create and run router in main process
        print("\n[Main] Starting command router...")
        router = create_router(shared_state, output.send_channels)
        
        # This blocks until interrupted
        router.run()
        
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
