"""
Command Router Module

Routes control commands between joystick and UDP inputs based on switch state.
Selects the active input source and forwards to output.

Design Decisions:
- Evaluates switch state on every loop iteration
- Immediately switches source when switch state changes
- Never mixes or blends inputs
- Always forwards exactly one source
- Provides debug logging for mode changes
"""

import time
import config


class CommandRouter:
    """
    Routes commands from multiple input sources to output based on switch state.
    
    The router reads from shared state populated by input receivers
    and forwards the selected source to the output function.
    """
    
    def __init__(self, shared_state: dict, output_func):
        """
        Initialize the command router.
        
        Args:
            shared_state: Multiprocessing Manager dict containing:
                - joystick_channels: list of 4 floats
                - udp_channels: list of 4 floats  
                - switch_state: MODE_JOYSTICK or MODE_UDP
            output_func: Callable that accepts channels list
        """
        self.shared_state = shared_state
        self.output_func = output_func
        self.last_mode = None
        self.loop_interval = 1.0 / config.ROUTER_LOOP_HZ
        self.skip_frames_after_switch = 0  # Counter to skip frames after mode switch
        self.last_throttle_print_time = 0.0  # Time of last throttle print
        self.throttle_print_interval = 0.5  # Print throttle every 0.5 seconds
        
    def get_active_channels(self) -> list:
        """
        Get channels from the currently active input source.
        
        Returns:
            List of channel values from selected source
        """
        mode = self.shared_state.get("switch_state", config.MODE_JOYSTICK)
        
        # Log mode changes
        if mode != self.last_mode:
            print(f"[Router] Mode changed: {self.last_mode} -> {mode}")
            # Reset pitch ramp when switching to UDP mode
            if mode == config.MODE_UDP:
                self.shared_state["reset_pitch_ramp"] = True
                print("[Router] Pitch ramp reset requested")
                
                # Initialize UDP channels to current joystick values to prevent jerking
                joystick_channels = list(self.shared_state.get("joystick_channels", config.get_default_channels()))
                self.shared_state["udp_channels"] = joystick_channels
                print(f"[Router] UDP channels initialized to joystick values: {joystick_channels}")
                
                # Skip first 3 frames after switching to allow UDP receiver to stabilize
                self.skip_frames_after_switch = 3
                print("[Router] Will skip first 3 frames after mode switch")
            self.last_mode = mode
        
        if mode == config.MODE_JOYSTICK:
            channels = self.shared_state.get("joystick_channels", config.get_default_channels())
        else:
            channels = self.shared_state.get("udp_channels", config.get_default_channels())
        
        # Ensure we return a proper list (Manager proxies need conversion)
        return list(channels)
    
    def route_once(self) -> None:
        """
        Perform a single routing iteration.
        
        Gets active channels and forwards to output.
        Always sends button events and unmapped axes from physical controller.
        """
        channels = self.get_active_channels()
        
        # Print throttle value periodically in joystick mode
        mode = self.shared_state.get("switch_state", config.MODE_JOYSTICK)
        if mode == config.MODE_JOYSTICK:
            current_time = time.time()
            if current_time - self.last_throttle_print_time >= self.throttle_print_interval:
                throttle = channels[config.CHANNEL_THROTTLE]
                print(f"[Joystick] Throttle: {throttle:+8.1f}")
                self.last_throttle_print_time = current_time
        
        # Skip sending data for first few frames after mode switch
        if self.skip_frames_after_switch > 0:
            self.skip_frames_after_switch -= 1
            print(f"[Router] Skipping frame (remaining skips: {self.skip_frames_after_switch})")
            return
        
        # Send main channels (axes 0-3)
        self.output_func(channels)
        
        # Always pass through physical controller buttons and unmapped axes (4-7)
        # This works in BOTH modes:
        # - JOYSTICK mode: axes 0-3 from joystick + axes 4-7 + buttons
        # - UDP mode: axes 0-3 from UDP + axes 4-7 + buttons
        
        # Pass through button events
        buttons = dict(self.shared_state.get("joystick_buttons", {}))
        for button_num, button_value in buttons.items():
            if hasattr(self.output_func, '__self__'):  # Check if it's a method
                self.output_func.__self__.send_button_event(button_num, button_value)
        
        # Pass through unmapped axes (4-7)
        other_axes = dict(self.shared_state.get("joystick_other_axes", {}))
        for axis_num, axis_value in other_axes.items():
            if hasattr(self.output_func, '__self__'):
                self.output_func.__self__.send_axis_event(axis_num, axis_value)
    
    def run(self) -> None:
        """
        Run the router loop continuously.
        
        Routes commands at configured rate until interrupted.
        """
        print(f"[Router] Starting at {config.ROUTER_LOOP_HZ} Hz")
        print(f"[Router] Initial mode: {self.shared_state.get('switch_state', config.MODE_JOYSTICK)}")
        
        try:
            while True:
                loop_start = time.time()
                
                # Route commands
                self.route_once()
                
                # Maintain loop rate
                elapsed = time.time() - loop_start
                sleep_time = self.loop_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            print("[Router] Shutting down...")


def create_router(shared_state: dict, output_func) -> CommandRouter:
    """
    Factory function to create a configured router.
    
    Args:
        shared_state: Multiprocessing Manager dict
        output_func: Output function accepting channels list
    
    Returns:
        Configured CommandRouter instance
    """
    return CommandRouter(shared_state, output_func)
