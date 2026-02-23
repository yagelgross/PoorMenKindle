import socket

from scapy.layers.dns import DNS, DNSQR, DNSRR

# Map of domain names to spoofed IP addresses for local DNS hijacking
LOCAL_RECORDS = {
    "yagel.home.": "10.0.0.101",
    "google.co.il.": "1.2.3.4",
}

DNS_PORT = 53
FORWARD_DNS = "8.8.8.8"

# Main DNS server that handles DNS queries and spoofing
def run_dns():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", DNS_PORT))
        print(f"[*] DNS Server is up on port {DNS_PORT}...")
    except PermissionError:
        print("[-] Error: You must run this with sudo!")
        return
    except Exception as e:
        print(f"[-] Could not bind to port 53: {e}")
        return

    print(f"DNS Server is running and listening on port {DNS_PORT}...")

    # Main DNS query processing loop
    while True:
        data, addr = sock.recvfrom(1024)
        try:
            dns_packet = DNS(data)
            # Check if this is a DNS query (qr=0)
            if dns_packet.qr == 0 and DNSQR in dns_packet:
                qname = dns_packet[DNSQR].qname.decode('utf-8')

                # Return spoofed IP if the domain is in LOCAL_RECORDS
                if qname in LOCAL_RECORDS:
                    print(f"[!] Spoofing {qname} -> {LOCAL_RECORDS[qname]}")
                    resp = DNS(id=dns_packet.id, qr=1, aa=1, qd=dns_packet.qd,
                               an=DNSRR(rrname=qname, type='A', rclass='IN', ttl=60, rdata=LOCAL_RECORDS[qname]))
                    sock.sendto(bytes(resp), addr)
                else:
                    # Forward unknown queries to a real DNS server
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as forward_sock:
                        forward_sock.settimeout(2)
                        forward_sock.sendto(data, (FORWARD_DNS, 53))
                        try:
                            forward_data, _ = forward_sock.recvfrom(1024)
                            sock.sendto(forward_data, addr)
                        except socket.timeout:
                            # Ignore timeout errors
                            pass
        except Exception as e:
            # Log packet parsing errors
            print(f"[-] DNS Packet Error: {e}")



# Run the DNS server when executed directly
if __name__ == "__main__":
    run_dns()