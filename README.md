# BookWorm: Custom Network Infrastructure & Digital Library

BookWorm is a vertically integrated network system built entirely in Python. Unlike standard applications that rely on the operating system's network stack, this project implements its own core customized services—including DHCP, DNS, and a Reliable UDP (RUDP) protocol—to power a fully functional digital e-book library.

## 📖 Table of Contents
- [Project Overview](#project-overview)
- [Key Functionality](#key-functionality)
  - [Application Layer](#application-layer)
  - [Transport Layer (RUDP)](#transport-layer-rudp)
  - [Infrastructure Layer](#infrastructure-layer)
- [Technical Stack](#technical-stack)
- [Running the Project](#running-the-project)
- [Future Roadmap](#future-roadmap)

---

## 🏗 Project Overview

The system operates on a client-server architecture consisting of:
1.  **The Server:** Hosts `.epub` files, manages user authentication, stores reading progress, and handles raw network requests.
2.  **The Client:** A GUI application (`BookWormApp.py`) that discovers the server, downloads book chapters, and renders them for the user.
3.  **The Network Stack:** Custom implementations of DHCP and DNS to manage the local network environment, plus a Proxy for simulating packet loss.

---

## 🚀 Key Functionality

### 📱 Application Layer (The Library)
*   **E-Book Parsing:** The server parses standard `.epub` files on the fly using `EbookLib` and `BeautifulSoup`, serving them chapter-by-chapter to reduce bandwidth.
*   **Progress Tracking:** Users can stop reading at any time; the server persistently tracks the exact chapter and book for every user.
*   **User Authentication:** A custom login system using Caesar Cipher encryption for credential transmission.
*   **Media Handling:** Server-side processing of book cover art using `Pillow`, converted to lightweight Base64 thumbnails for the client.

### 📦 Transport Layer (Reliable UDP)
This project implements **RUDP** (Reliable User Datagram Protocol) to achieve TCP-like reliability over UDP.
*   **Reliability Logic:** Implements Sequence Numbers, Acknowledgments (ACKs), and Retries.
*   **Packet Recovery:** A dedicated background thread (`udp_retransmission_loop`) monitors unacknowledged packets and retransmits them if a timeout occurs.
*   **Chaos Testing:** Includes a `udp_proxy.py` module to simulate network jitter and packet drops, allowing verification of the RUDP recovery logic via Wireshark.

### 🌐 Infrastructure Layer
*   **Custom DHCP Server (`DHCP.py`):** Uses raw sockets (`scapy`) to listen for BOOTP discovery packets and assign IP addresses to clients, managing a custom IP pool.
*   **DNS Handling (`DnsServer.py`):** Acts as a local DNS resolver, utilizing **DNS-over-HTTPS (DoH)** to resolve external domains securely while handling local hostname resolution.

---

## 🛠 Technical Stack

*   **Language:** Python 3.13
*   **Networking:** `socket`, `scapy`, `netifaces`, `dnslib`, `dnspython`
*   **Data Processing:** `base64`, `json`, `io`
*   **Media & Parsing:** `EbookLib`, `beautifulsoup4`, `Pillow`
*   **GUI:** `tkinter`

---

## ⚙️ Running the Project

### Prerequisites
Install dependencies using the provided requirements file:
```bash
pip install -r requirements.txt
```

### 1. Start the Network Infrastructure
*Note: These scripts require `sudo` or Administrator privileges to access raw sockets.*

```bash
# Start the DHCP server to manage IPs
sudo python3 DHCP.py

# Start the DNS server
sudo python3 DnsServer.py
```

### 2. Start the Book Server
The server creates both TCP and RUDP listeners.
```bash
python3 Server.py
```

### 3. Start the Client
Launch the GUI application.
```bash
python3 BookWormApp.py
```

---

## 🔮 Future Roadmap

While the current system is fully functional for educational and demonstration purposes, the following features are planned for future releases to transition BookWorm into production-grade software:

1.  **Database Integration:**
    *   *Current:* Users and reading progress are stored in volatile memory lists (`AllClients`, `currClients`).
    *   *Future:* Migration to **SQLite** or **PostgreSQL** for persistent user data and library management.

2.  **Advanced Security:**
    *   *Current:* Credentials use a simple Caesar Cipher.
    *   *Future:* Implementation of **TLS/SSL** wrappers for all sockets and industry-standard hashing (e.g., bcrypt) for passwords.

3.  **Modern UI/UX:**
    *   *Current:* `tkinter` based interface.
    *   *Future:* Porting the client to a modern web frontend (React/Vue) or a desktop framework like **PyQt/PySide** for a smoother reading experience.

