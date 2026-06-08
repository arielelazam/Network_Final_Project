# DASH Video Streaming with Reliable UDP

Advanced video streaming system featuring adaptive bitrate selection, 
congestion control, DHCP & DNS servers.

## Features

- **Reliable UDP**: ACK-based retransmission (3 attempts, 1s timeout)
- **Congestion Control**: Sliding Window with Slow Start & Congestion Avoidance
- **DASH Adaptive Streaming**: Quality selection (HIGH/MEDIUM/LOW) based on throughput
- **DHCP Server**: IP allocation with lease renewal
- **DNS Server**: Caching with Cloudflare DoH integration
- **Network Simulation**: Packet loss & latency simulation
- **Multi-client Support**: Concurrent client handling

## Files

- `app_server.py` - Application server (TCP + UDP)
- `client.py` - Video streaming client
- `dhcp_server.py` - DHCP protocol implementation
- `dns_server.py` - DNS server with caching
- `prepare_media.py` - Media preparation script

## How to Run

### 1. Start Prepare Media Engine
```bash
python prepare_media.py
```

### 2. Start DHCP Server
```bash
python dhcp_server.py
```

### 3. Start DNS Server (in another terminal)
```bash
python dns_server.py
```

### 4. Start Application Server (in another terminal)
```bash
python app_server.py
```

### 5. Run Client (in another terminal)
```bash
python client.py
```

## Network Configuration

- DHCP: 0.0.0.0:6767 (UDP)
- DNS: 127.0.0.1:9999 (UDP)
- App TCP: 127.0.0.1:9000 (TCP)
- App UDP: 127.0.0.1:9001 (UDP)

## Technologies

- Python 3
- Socket Programming (TCP/UDP)
- JSON for data serialization
- Threading for multi-client support

## Authors

Ariel Elazam, Amir Keinan and Pinhas Zanzuri
