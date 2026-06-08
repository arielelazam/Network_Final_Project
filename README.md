
# Adaptive Media Streaming System (DASH Video Server) 

> **Simulating Real Streaming Systems over a Custom Networking Stack**

## 📖 Overview
This project is a complete, end-to-end adaptive media streaming system built entirely in Python. It simulates a realistic internet environment from the ground up, including custom implementations of core infrastructure services (DHCP, DNS) and an advanced Application Server utilizing a custom Reliable UDP (RUDP) protocol. 

The system is designed to handle real-world network challenges such as packet loss, latency, and network congestion by dynamically adapting video quality to the client's available throughput (DASH - Dynamic Adaptive Streaming over HTTP).

## ✨ Key Features

### 1. Infrastructure Services
*   **Custom DHCP Server (UDP):** Implements the complete 4-way DORA handshake (DISCOVER, OFFER, REQUEST, ACK). Features IP pool management, lease expiration handling, and client tracking.
*   **Custom DNS Server (UDP):** Acts as the network's address book. Features a local cache with TTL management, static local records, and an external fallback using DNS over HTTPS (DoH) via Cloudflare to resolve real-world domains.

### 2. Application Server (TCP + Reliable UDP)
The core server handles a dual-channel communication architecture:
*   **Control Channel (TCP):** Uses a custom, stateful handshake (`LIST` -> `SELECT`) to present the video catalog and negotiate the required media securely.
*   **Data Channel (Reliable UDP):** Streams video segments using a custom RUDP implementation. It ensures data integrity over an unreliable protocol by utilizing:
    *   **Stop-and-Wait ARQ:** Sequence numbers, ACKs, and a maximum of 3 retries per chunk.
    *   **Congestion Control:** A dynamic sliding window implementing **Slow Start** (exponential growth) and **Congestion Avoidance** (linear growth). It dynamically reacts to packet loss by cutting the window threshold in half.
    *   **Network Simulation:** Deliberately introduces an 8% packet loss rate and variable latency to test the system's resilience.

### 3. Adaptive Streaming Client (DASH)
*   Executes the full network flow: Acquires an IP via DHCP, resolves the server's domain via DNS, and connects to the App Server.
*   **Adaptive Bitrate Algorithm:** Measures the download throughput of each segment. If the network is fast, it requests the next segment in `HIGH` or `ULTRA` quality. If packet loss or delays occur, it gracefully downgrades to `MEDIUM` or `LOW` to prevent video buffering.

### 4. Media Pre-processing
*   Automated script utilizing `FFmpeg` and `FFprobe` to slice raw `.mp4` files into 2-second segments across 3 distinct bitrates (500k, 1500k, 3000k).
*   Generates a structured `catalog.json` used by the Application Server.

---

## System Architecture

1. **Client -> DHCP:** Broadcasts to get an IP address and lease time.
2. **Client -> DNS:** Requests IP resolution for `app.local` (or external sites).
3. **Client -> App Server (TCP):** Establishes a control connection to fetch the video catalog and select a movie.
4. **App Server -> Client (UDP):** Streams the movie chunks over Reliable UDP, adjusting window sizes based on ACKs.
5. **Client Adaptive Logic:** Calculates `Throughput = Segment Size / Download Time`. Adjusts the requested quality of the next segment accordingly.

---

## 🛠️ Technology Stack
*   **Language:** Python 3.x
*   **Networking:** Built-in `socket` library (IPv4, TCP, UDP)
*   **Media Processing:** `subprocess`, `FFmpeg`, `FFprobe`
*   **Data Serialization:** JSON

---

## 🚀 Getting Started

### Prerequisites
*   Python 3.8+
*   [FFmpeg](https://ffmpeg.org/download.html) installed and added to your system's PATH.
*   Place some `.mp4` video files in the `movies` directory before running the system.

### Installation & Execution

Run the following commands in separate terminal windows in the exact order below:

##How to Run the System


---

### 1. Prepare the Media  
*Run once to slice the videos and create the catalog*

```bash
python prepare_media.py
```

---

### 2. Start the DHCP Server

```bash
python dhcp_server.py
```

---

### 3. Start the DNS Server

```bash
python dns_server.py
```

---

### 4. Start the Application Server

```bash
python app_server.py
```

---

### 5. Run the Client  
*Follow the on-screen prompts to interact with the system*

```bash
python client.py
```

## Authors

Ariel Elazam, Amir Keinan and Pinhas Zanzuri
