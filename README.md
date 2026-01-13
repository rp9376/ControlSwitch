# FPV Drone Command Switch

A modular Python program that routes control commands for an FPV drone between two concurrent input sources.

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│  JoystickUDP        │     │  Secondary UDP      │
│  (Port 5000)        │     │  Input (Port 5001)  │
│                     │     │                     │
│  type, number,      │     │  dx, dy             │
│  value              │     │                     │
└─────────┬───────────┘     └──────────┬──────────┘
          │                            │
          ▼                            ▼
    ┌───────────┐                ┌───────────┐
    │ Process 1 │                │ Process 2 │
    │ Joystick  │                │   UDP     │
    │ Receiver  │                │ Receiver  │
    └─────┬─────┘                └─────┬─────┘
          │                            │
          └──────────┬─────────────────┘
                     │
              ┌──────▼──────┐
              │   Shared    │
              │   State     │
              │  (Manager)  │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │   Router    │
              │ (Main Proc) │
              │             │
              │ Switch ───► │ Selects active source
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │ UDP Output  │
              │ (Port 5002) │
              └─────────────┘
```

## Modules

| Module | Purpose |
|--------|---------|
| `config.py` | Configuration constants, port definitions, channel mappings |
| `joystick_receiver.py` | Receives joystick events, normalizes values, detects switch |
| `udp_input_receiver.py` | Receives dx/dy control input, mocks missing axes |
| `router.py` | Selects active source based on switch, forwards to output |
| `udp_output.py` | Sends channels to drone control system |
| `main.py` | Orchestrates all modules with multiprocessing |
| `test_sender.py` | Test utility for simulating inputs |

## Quick Start

```bash
# Terminal 1: Run the command switch
python main.py

# Terminal 2: Simulate inputs and toggle switch
python test_sender.py --mode all

# Terminal 3: Receive and display output
python test_sender.py --mode receive
```

## Configuration

Edit `config.py` to change:

- **UDP Ports**: `JOYSTICK_UDP_PORT`, `CONTROL_UDP_PORT`, `OUTPUT_UDP_PORT`
- **Channel Mapping**: `JOYSTICK_AXIS_MAP` - maps joystick axis numbers to channels
- **Switch Channel**: `SWITCH_CHANNEL_NUMBER` - which joystick channel controls routing
- **Router Rate**: `ROUTER_LOOP_HZ` - output update rate

## Input Formats

### Joystick Events (Port 5000)
```json
{"type": 2, "time": 3656941, "number": 1, "value": -171}
```

### Secondary UDP Input (Port 5001)
```json
{"dx": 50, "dy": -30}
```

## Output Format (Port 5002)
```json
{"channels": [0.5, -0.3, 0.0, 0.0], "timestamp": 1234567890.123}
```

## Switch Behavior

The switch is a regular controller channel (configured as channel 4 by default):
- **Value > 0**: JOYSTICK mode active
- **Value ≤ 0**: UDP mode active

Switching is instantaneous with no blending.

## Testing

```bash
# Simulate joystick movements
python test_sender.py --mode joystick

# Simulate UDP control input
python test_sender.py --mode udp

# Toggle switch between modes
python test_sender.py --mode switch

# Run all simulations
python test_sender.py --mode all

# Receive output for verification
python test_sender.py --mode receive
```
