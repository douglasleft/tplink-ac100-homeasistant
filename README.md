# TP-Link TL-AC100 for Home Assistant

A Home Assistant custom integration for **TP-Link TL-AC100 wireless controller (firmware v6.0+)**, using nonce-based MD5 authentication.

> **Note**: This integration is designed for AC100 firmware **v6.0 and above**. Older firmware versions that use plaintext password login are not supported.

## Features

- **Device Tracker**: Track all WiFi clients connected to APs managed by AC100
- **Per-Client Sensors**: IP address, connected AP, SSID, signal strength (dBm), connection time
- **Client Controls**: Block/Unblock switch, Disconnect button for each client
- **AP Monitoring**: Online/offline status (binary sensor), client count, uptime
- **Controller Overview**: Total online clients and online APs on the AC100
- **Device Hierarchy**: AC100 controller → APs → WiFi clients, all visible in HA device registry
- **Options Flow**: Adjust scan interval and consider-home time without re-adding

### Per-Client Sensors (Diagnostic)

| Sensor | Example | Description |
|--------|---------|-------------|
| Signal | -57 dBm | WiFi signal strength |
| IP Address | 192.168.1.100 | Client IP |
| Connected AP | TL-AP-3-书房 | Which AP the client is connected to |
| SSID | MyWiFi | Connected network name |
| Connected At | 2026/03/11 23:25:56 | When the client connected |

### Per-Client Controls

| Control | Type | Description |
|---------|------|-------------|
| Blocked | Switch | Block/unblock client from network |
| Disconnect | Button | Kick client off the network |

### Per-AP Sensors

| Sensor | Description |
|--------|-------------|
| Status | Online / Offline (binary sensor) |
| Clients | Number of connected clients |
| Uptime | AP uptime |

### AC100 Controller Sensors

| Sensor | Description |
|--------|-------------|
| Online Clients | Total connected clients |
| Online APs | Total online APs |

## Installation

### HACS (Recommended)

1. Open HACS → Integrations → ⋮ menu → Custom repositories
2. Add `https://github.com/douglasleft/tplink-ac100-homeasistant`, category: Integration
3. Search for "TP-Link TL-AC100" and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/tplink_ac100` to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"TP-Link TL-AC100"**
3. Enter your AC100's IP address, username and password
4. Optionally adjust scan interval (default: 30s) and consider-home time (default: 180s)

These options can also be changed later via **Options** without re-adding the integration.

## Compatibility

| Firmware | Supported | Auth Method |
|----------|-----------|-------------|
| v6.0+ | ✅ Yes | Nonce + MD5 (`encrypt_type: "3"`) |
| < v6.0 | ❌ No | Plaintext password (not supported) |

### Authentication Flow (v6.0+)

1. `POST /` → `get_encrypt_info` → receive `nonce`
2. Compute `md5(password:nonce)`
3. `POST /` → `login` with `encrypt_type: "3"` → receive `stok`
4. All API calls via `POST /stok={stok}/ds`

## Notes

- **建议为 Home Assistant 单独创建一个 AC100 管理账号**，避免与日常使用的 admin 账号互相踢 session。AC100 同一账号只支持一个活跃会话，如果你在浏览器登录 AC100 管理页面，会导致 HA 的 token 失效（集成会自动重新登录，但会产生短暂中断）。
- **Tip: Create a dedicated AC100 account for Home Assistant** to avoid session conflicts with your daily admin account. The AC100 only supports one active session per account — logging into the web UI will invalidate HA's token (the integration auto-recovers, but there will be a brief interruption).
- Communication is over **HTTP** (the AC100 hardware does not support HTTPS). Deploy on a trusted local network.
- MAC addresses from the AC100 API use dash-uppercase format (e.g., `10-B7-13-93-5E-C5`). The integration normalizes them to colon-lowercase format (e.g., `10:b7:13:93:5e:c5`) for HA compatibility.

## License

MIT
