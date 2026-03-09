"""
UDP Output Module

Sends selected control commands to the drone control system via UDP.
Provides a pluggable, replaceable output interface.

Output Format (JSON):
{
    "channels": [roll, pitch, yaw, throttle],
    "timestamp": <float>
}

Design Decisions:
- Isolated socket management
- Simple, replaceable implementation
- JSON format for easy debugging (can be changed to binary later)
- Reuses socket for efficiency
- send_channels() is the public interface
"""

import socket
import json
import time

import config


class UDPOutput:
    """
    Sends control channels over UDP to a destination.
    
    This class manages the UDP socket and provides the send_channels
    interface required by the router.
    """
    
    def __init__(self, host: str = None, port: int = None):
        """
        Initialize UDP output sender.
        
        Args:
            host: Destination host (default from config)
            port: Destination port (default from config)
        """
        self.host = host or config.OUTPUT_UDP_HOST
        self.port = port or config.OUTPUT_UDP_PORT
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.verbose = False  # Set False to disable logging
        
        # Set up secondary output if defined
        self.secondary_host = getattr(config, 'SECONDARY_UDP_HOST', None)
        self.secondary_port = getattr(config, 'SECONDARY_UDP_PORT', None) if self.secondary_host else None
        
        print(f"[UDPOutput] Primary: {self.host}:{self.port}")
        if self.secondary_host and self.secondary_port:
            print(f"[UDPOutput] Secondary: {self.secondary_host}:{self.secondary_port}")
    
    def send_channels(self, channels: list) -> None:
        """
        Send channel values to the destination as individual axis events.
        
        Sends each channel as a separate axis event matching the format:
        {
            "type": 2,  // axis event
            "time": timestamp_ms,
            "number": axis_number,
            "value": axis_value
        }
        
        Args:
            channels: List of channel values [roll, pitch, yaw, throttle]
        """
        timestamp_ms = int(time.time() * 1000)
        
        # Send each channel as a separate axis event
        # Axis mapping: 0=roll, 1=pitch, 2=yaw, 3=throttle
        for axis_number, value in enumerate(channels):
            event = {
                "type": 2,  # Axis event
                "time": timestamp_ms,
                "number": axis_number,
                "value": int(value)  # Ensure integer value
            }
            
            #print(f"[UDPOutput] Sending axis event: {event}")
            data = json.dumps(event).encode("utf-8")
            self.sock.sendto(data, (self.host, self.port))
            
            # Send to secondary if defined
            if self.secondary_host and self.secondary_port:
                self.sock.sendto(data, (self.secondary_host, self.secondary_port))
        
        # Debug logging (can be disabled for production)
        if self.verbose:
            print(f"[UDPOutput] Sent: {channels}")
    
    def send_button_event(self, button_number: int, value: int) -> None:
        """
        Send a button event from physical controller.
        
        Args:
            button_number: Button number
            value: Button value (1=pressed, 0=released)
        """
        timestamp_ms = int(time.time() * 1000)
        event = {
            "type": 1,  # Button event
            "time": timestamp_ms,
            "number": button_number,
            "value": value
        }
        data = json.dumps(event).encode("utf-8")
        self.sock.sendto(data, (self.host, self.port))
        
        # Send to secondary if defined
        if self.secondary_host and self.secondary_port:
            self.sock.sendto(data, (self.secondary_host, self.secondary_port))
        
        if self.verbose:
            print(f"[UDPOutput] Button {button_number}: {value}")
    
    def send_axis_event(self, axis_number: int, value: int) -> None:
        """
        Send an individual axis event (for unmapped axes passthrough).
        
        Args:
            axis_number: Axis number
            value: Axis value
        """
        timestamp_ms = int(time.time() * 1000)
        event = {
            "type": 2,  # Axis event
            "time": timestamp_ms,
            "number": axis_number,
            "value": int(value)
        }
        data = json.dumps(event).encode("utf-8")
        self.sock.sendto(data, (self.host, self.port))
        
        # Send to secondary if defined
        if self.secondary_host and self.secondary_port:
            self.sock.sendto(data, (self.secondary_host, self.secondary_port))
        
        if self.verbose:
            print(f"[UDPOutput] Axis {axis_number}: {value}")
    
    def close(self) -> None:
        """Close the UDP socket."""
        self.sock.close()
        print("[UDPOutput] Socket closed")


# Module-level convenience function
_output_instance = None


def get_output_sender(host: str = None, port: int = None) -> UDPOutput:
    """
    Get or create the UDP output sender instance.
    
    Args:
        host: Optional destination host override
        port: Optional destination port override
    
    Returns:
        UDPOutput instance
    """
    global _output_instance
    if _output_instance is None:
        _output_instance = UDPOutput(host, port)
    return _output_instance


def send_channels(channels: list) -> None:
    """
    Convenience function to send channels using shared instance.
    
    This matches the interface specification:
        send_channels(channels: list[int | float])
    
    Args:
        channels: List of channel values
    """
    sender = get_output_sender()
    sender.send_channels(channels)
