import socket
from dnslib import DNSRecord
import requests
import time

DnsPort = 53
DOH_URL = "https://cloudflare-dns.com/dns-query"
DOH_HEADERS = {
    "Content-Type": "application/dns-message",
    "Accept": "application/dns-message",
}

def doh_forward(query_bytes: bytes, timeout=2.0) -> bytes:
    r = requests.post(DOH_URL, data=query_bytes, headers=DOH_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content

def get_min_ttl(resp_bytes: bytes) -> int:
    # Use minimum TTL in an answer section (rr). If no answers, don't cache.
    reply = DNSRecord.parse(resp_bytes)
    if not reply.rr:
        return 0
    return min(rr.ttl for rr in reply.rr)

def startdns():
    cache= {}
    print("DNS over HTTP Server started")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", DnsPort))
        print(f"DNS active on port {DnsPort}")
    except PermissionError:
        print("Error: You need root/admin privileges to bind to port 53.")
        return

    while True:
        data, addr = sock.recvfrom(4096)
        req = DNSRecord.parse(data)

        qname = str(req.q.qname).rstrip(".")
        qtype = req.q.qtype
        qclass = req.q.qclass
        key = (qname, qtype, qclass)
        if(key in cache):
            cached_bytes = cache[key]["resp"]
            age = time.time() - cache[key]["added_at"]
            cached = DNSRecord.parse(cached_bytes)
            try:
                ttl = get_min_ttl(cached_bytes)
            except Exception:
                ttl = 0
            if ttl > 0 and age <= ttl:
                print(f"Cache hit for {qname}")
                cached.header.id = req.header.id
                cached.questions = list(req.questions)
                sock.sendto(cached.pack(), addr)
                continue
            else:
                del cache[key]
        try:
            response = doh_forward(data,timeout=2.0)

            ttl = get_min_ttl(response)
            if ttl > 0:
                cache[key] = {"resp": response, "added_at": time.time()}
            sock.sendto(response, addr)
        except socket.timeout:
            print("Timeout error")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    startdns()