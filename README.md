# Adaptive Media Streaming System (DASH Video Server)

> **Simulating Real Streaming Systems over a Custom Networking Stack**

## 📖 Overview

This project is a complete, end-to-end adaptive media streaming system built entirely in Python. It simulates a realistic internet environment from the ground up, including custom implementations of core infrastructure services (DHCP, DNS) and an advanced Application Server utilizing a custom Reliable UDP (RUDP) protocol.

The system is designed to handle real-world network challenges such as packet loss, latency, and network congestion by dynamically adapting video quality to the client's available throughput (DASH - Dynamic Adaptive Streaming over HTTP).

## ✨ Key Features

### 1. Infrastructure Services

- **Custom DHCP Server (UDP):** Implements the complete 4-way DORA handshake (DISCOVER, OFFER, REQUEST, ACK). Features IP pool management, lease expiration handling, and client tracking.
- **Custom DNS Server (UDP):** Acts as the network's address book. Features a local cache with TTL management, static local records, and an external fallback using DNS over HTTPS (DoH) via Cloudflare to resolve real-world domains.

### 2. Application Server (TCP + Reliable UDP)

The core server handles a dual-channel communication architecture:

- **Control Channel (TCP):** Uses a custom, stateful handshake (`LIST` -> `SELECT`) to present the video catalog and negotiate the required media securely.
- **Data Channel (Reliable UDP):** Streams video segments using a custom RUDP implementation. It ensures data integrity over an unreliable protocol by utilizing:
  - **Stop-and-Wait ARQ:** Sequence numbers, ACKs, and a maximum of 3 retries per chunk.
  - **Congestion Control:** A dynamic sliding window implementing **Slow Start** (exponential growth) and **Congestion Avoidance** (linear growth). It dynamically reacts to packet loss by cutting the window threshold in half.
  - **Network Simulation:** Deliberately introduces an 8% packet loss rate and variable latency to test the system's resilience.

### 3. Adaptive Streaming Client (DASH)

- Executes the full network flow: Acquires an IP via DHCP, resolves the server's domain via DNS, and connects to the App Server.
- **Adaptive Bitrate Algorithm:** Measures the download throughput of each segment. If the network is fast, it requests the next segment in `HIGH` or `ULTRA` quality. If packet loss or delays occur, it gracefully downgrades to `MEDIUM` or `LOW` to prevent video buffering.
- **Gap Detection:** Detects missing chunks and handles incomplete segments gracefully.

### 4. Media Pre-processing

- Automated script utilizing `FFmpeg` and `FFprobe` to slice raw `.mp4` files into 2-second segments across 3 distinct bitrates (500k, 1500k, 3000k).
- Generates a structured `catalog.json` used by the Application Server.

---

## System Architecture

```
Client              App Server          DHCP Server    DNS Server
  |                    |                    |              |
  |--DHCP REQUEST----->|                    |              |
  |<-----DHCP OFFER----|                    |              |
  |                                         |              |
  |--DNS QUERY------------------------------------------->|
  |<--DNS RESPONSE (app.local -> 127.0.0.1)--|           |
  |                    |                                    |
  |--TCP: LIST------->|                                    |
  |<--Movie Catalog---|                                    |
  |                    |                                    |
  |--TCP: SELECT----->|                                    |
  |<--SELECT_OK-------|                                    |
  |                    |                                    |
  |--UDP: REQ seg 0-->| (Reliable UDP)                     |
  |<--Chunks (ACK)----| (Sliding Window + Congestion Ctrl) |
  |                    |                                    |
```

**Flow:**
1. Client broadcasts DHCP DISCOVER to get an IP address
2. Client queries DNS to resolve `app.local` 
3. Client establishes TCP connection to fetch video catalog
4. Client selects a movie and initiates UDP streaming
5. Server streams chunks with Reliable UDP and Congestion Control
6. Client measures throughput and adapts quality dynamically

---

## 🛠️ Technology Stack

- **Language:** Python 3.8+
- **Networking:** Built-in `socket` library (IPv4, TCP, UDP)
- **Media Processing:** `subprocess`, `FFmpeg`, `FFprobe`
- **Data Serialization:** JSON
- **Concurrency:** Python `threading`

---

## 📁 Project Structure

```
project/
├── app_server.py              # Application server (TCP + UDP)
│                              # Implements Reliable UDP, Congestion Control
├── client.py                  # DASH client with adaptive bitrate selection
│                              # Performs DHCP, DNS, and throughput measurement
├── dhcp_server.py             # DHCP protocol server
│                              # IP allocation, lease management
├── dns_server.py              # DNS server with caching and DoH
│                              # Local records, TTL-based cache, Cloudflare fallback
├── prepare_media.py           # FFmpeg-based media preparation
│                              # Slices videos into segments, generates catalog
├── catalog.json               # Generated video catalog (created by prepare_media.py)
├── media/                     # Video segments directory (created automatically)
│                              # Contains seg_XXX_HIGH.mp4, seg_XXX_MEDIUM.mp4, etc.
└── README.md                  # This file
```

---

## Network Configuration

| Component | Protocol | Address | Port | Purpose |
|-----------|----------|---------|------|---------|
| DHCP | UDP | 0.0.0.0 | 6767 | IP allocation for clients |
| DNS | UDP | 127.0.0.1 | 9999 | Domain name resolution |
| App TCP | TCP | 127.0.0.1 | 9000 | Control channel (LIST/SELECT) |
| App UDP | UDP | 127.0.0.1 | 9001 | Data channel (Reliable UDP streaming) |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **FFmpeg** installed and added to system PATH
  - Download: https://ffmpeg.org/download.html
  - Verify: `ffmpeg -version` in terminal
- Place `.mp4` video files in a `movies/` directory before running

### Installation & Execution

Run the following commands in **separate terminal windows** in the exact order:

#### 1. Prepare the Media

*Run once to slice videos and create the catalog*

```bash
python prepare_media.py
```

This script will:
- Scan the `movies/` directory for `.mp4` files
- Slice each video into 2-second segments
- Encode each segment at 3 bitrates (500k, 1500k, 3000k)
- Generate `catalog.json`

#### 2. Start the DHCP Server

*Terminal Window 1*

```bash
python dhcp_server.py
```

Expected output:
```
DHCP Server running on 0.0.0.0:6767
Waiting for DISCOVER messages...
```

#### 3. Start the DNS Server

*Terminal Window 2*

```bash
python dns_server.py
```

Expected output:
```
DNS Server listening on 127.0.0.1:9999
Ready to resolve domains...
```

#### 4. Start the Application Server

*Terminal Window 3*

```bash
python app_server.py
```

Expected output:
```
App Server started on 127.0.0.1:9000 (TCP) and 127.0.0.1:9001 (UDP)
Simulating network: 8% packet loss, variable latency
```

#### 5. Run the Client

*Terminal Window 4*

```bash
python client.py
```

Follow the on-screen prompts:
- Select a movie from the catalog
- Watch as segments are downloaded with quality adaptation
- Downloaded segments saved to `network_project_downloads/`

---

## How It Works

### DHCP Process
1. Client sends `DHCP DISCOVER` broadcast
2. Server responds with `DHCP OFFER` (IP + lease time)
3. Client sends `DHCP REQUEST` to accept the offer
4. Server confirms with `DHCP ACK`
5. Client renews lease every 540 seconds

### DNS Resolution
1. Client queries DNS server for `app.local`
2. DNS checks local records first (fast path)
3. If not found, checks cache with TTL
4. If still not found, queries Cloudflare DoH for external domains
5. Result cached with TTL for future queries

### TCP Handshake (Control Channel)
1. Client connects to server via TCP port 9000
2. Sends `LIST` request
3. Server responds with movie catalog (JSON)
4. Client sends `SELECT` with movie choice
5. Server responds with `SELECT_OK`

### UDP Streaming (Data Channel)
1. Client sends segment request via UDP
2. Server sends chunks with sequence numbers
3. Client acknowledges receipt (ACK)
4. Server implements Reliable UDP:
   - If ACK not received within 1 second, retransmit (max 3 attempts)
   - If chunk fails, reduce congestion window threshold
5. Window size adapts: Slow Start phase → Congestion Avoidance phase

### DASH Adaptive Bitrate
1. Client measures segment download time
2. Calculates throughput: `Throughput = Segment Size / Download Time`
3. Selects quality for next segment:
   - `HIGH` (3000k) if throughput > 200 KB/s
   - `MEDIUM` (1500k) if throughput > 50 KB/s
   - `LOW` (500k) otherwise
4. Quality changes dynamically without interruption

---

## Key Concepts Demonstrated

- **Reliable UDP (RUDP):** Custom protocol built on top of unreliable UDP to provide reliability
- **Stop-and-Wait ARQ:** Simple retransmission mechanism with sequence numbers
- **Congestion Control:** TCP Reno-style algorithm with Slow Start and Congestion Avoidance
- **Flow Control:** Sliding window mechanism to manage data transmission rate
- **Adaptive Streaming (DASH):** Dynamic quality selection based on network conditions
- **DHCP Protocol:** IP address allocation with lease management
- **DNS Protocol:** Domain name resolution with caching and upstream queries
- **Multi-threading:** Concurrent server handling multiple clients
- **Network Simulation:** Deliberate introduction of packet loss and latency

---

## Debugging & Monitoring

### Enable Verbose Logging

Edit the respective `.py` files and uncomment `print()` statements:

```python
# In app_server.py
print(f"ACK received for chunk {chunk_num}")

# In client.py
print(f"Throughput: {throughput:.2f} KB/s, Quality: {quality}")
```

### Monitor with Wireshark

Capture UDP traffic on port 9001 to observe:
- Reliable UDP retransmissions
- Sequence number progression
- ACK patterns
- Window size changes

### Common Issues

| Issue | Solution |
|-------|----------|
| "Address already in use" | Wait 30 seconds or change port numbers |
| "FFmpeg not found" | Install FFmpeg and add to PATH |
| "No such file or directory: catalog.json" | Run `prepare_media.py` first |
| "Connection refused" | Ensure all servers are running |
| "Segment not found" | Check `media/` directory exists and has segments |

---

## Performance Metrics

With 8% simulated packet loss:
- **Throughput:** ~100-200 KB/s (depends on network conditions)
- **Quality Adaptation:** Changes within 2-3 segments
- **Recovery Time:** ~2-4 seconds after congestion event
- **Multi-client:** Handles 3-5 concurrent clients smoothly

---

## Future Enhancements

- [ ] Implement QUIC protocol for comparison
- [ ] Add video player UI (PyGame or web frontend)
- [ ] Support for different segment durations (1s, 5s, 10s)
- [ ] Advanced congestion control (BBR, Vegas)
- [ ] Bandwidth prediction algorithms (EWMA, PANDA)
- [ ] Support for multiple quality levels (4K, 8K)

---

## Learning Outcomes

This project demonstrates:
- ✅ Custom protocol implementation from scratch
- ✅ Congestion control algorithms in action
- ✅ DHCP and DNS protocol details
- ✅ Adaptive streaming decision-making
- ✅ Multi-threaded server architecture
- ✅ Network simulation and testing
- ✅ Reliable communication over unreliable channels

---

## Authors

- **Ariel Elazam**
- **Amir Keinan**
- **Pinhas Zanzuri**
