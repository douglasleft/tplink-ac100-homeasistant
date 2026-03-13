# TP-Link TL-AC100 for Home Assistant

A Home Assistant custom integration for TP-Link TL-AC100 wireless controller (new firmware with nonce-based MD5 authentication).

## Features

- **Device Tracker**: Track all WiFi clients connected to APs managed by AC100
- **AP Sensors**: Monitor each AP's status (online/offline), client count, uptime, channel info
- **Controller Overview**: Total online clients and online APs count
- **Device Hierarchy**: AC100 controller → APs → WiFi clients, all visible in HA device registry

### Terminal (WiFi Client) Attributes

| Attribute | Description |
|-----------|-------------|
| ip | IP address |
| mac | MAC address |
| ap_name | Connected AP name |
| ssid | Connected SSID |
| frequency | Band (2.4GHz / 5GHz) |
| online_time | Connection duration |
| signal | Signal strength |
| rx_rate / tx_rate | Link speed |
| auth_type | Authentication type |
| blocked | Whether blocked |

### AP Sensor Attributes

| Attribute | Description |
|-----------|-------------|
| Status | online / offline |
| Clients | Number of connected clients |
| Uptime | AP uptime |
| Channel / Load | Per-band channel and channel load |

## Installation

### HACS (Manual Repository)

1. Open HACS → Integrations → 3-dot menu → Custom repositories
2. Add this repository URL, category: Integration
3. Search for "TP-Link TL-AC100" and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/tplink_ac100` to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services → Add Integration
2. Search for "TP-Link TL-AC100"
3. Enter your AC100's IP address, username and password
4. Optionally adjust scan interval and consider-home time

## Compatibility

This integration uses the **new firmware** authentication method:

1. Fetch nonce via `get_encrypt_info`
2. Compute `md5(password:nonce)`
3. Login with `encrypt_type: "3"`

If your AC100 uses the old firmware (direct password login), this integration will not work.

## Notes

- The AC100 only supports **one active management session**. Avoid running multiple HA instances against the same AC100.
- Communication is over HTTP (the AC100 hardware does not support HTTPS). Deploy on a trusted network.
