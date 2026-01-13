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
        """
        channels = self.get_active_channels()
        self.output_func(channels)
    
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
