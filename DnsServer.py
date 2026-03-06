import socket
from dnslib import DNSRecord
import certifi
import time
import urllib3

DnsPort = 53

DOH_IP = "1.1.1.1"
DOH_HOST = "cloudflare-dns.com"
DOH_PATH = "/dns-query"

pIndex = 0

http = urllib3.HTTPSConnectionPool(
    host=DOH_IP,
    port=443,
    cert_reqs="CERT_REQUIRED",
    ca_certs=certifi.where(),
    assert_hostname=DOH_HOST,
    server_hostname=DOH_HOST,
    headers={
        "Host": DOH_HOST,
        "Content-Type": "application/dns-message",
        "Accept": "application/dns-message",
    },
    timeout=urllib3.util.Timeout(connect=2.0, read=2.0),
)

def doh_forward(query_bytes: bytes, timeout=2.0) -> bytes:
    r = http.urlopen(
        "POST",
        DOH_PATH,
        body=query_bytes,
    )
    if r.status != 200:
        raise Exception(f"Error: {r.status} {r.reason}")
    return r.data

def get_min_ttl(resp_bytes: bytes) -> int:
    # Use minimum TTL in an answer section (rr). If no answers, don't cache.
    reply = DNSRecord.parse(resp_bytes)
    if not reply.rr:
        return 0
    return min(rr.ttl for rr in reply.rr)

def startdns():
    global pIndex
    cache= {}
    print(f"{pIndex}: DNS over HTTPS Server started")
    pIndex+=1
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", DnsPort))
        print(f"{pIndex}: DNS active on port {DnsPort}")
        pIndex += 1
    except PermissionError:
        print(f"{pIndex}: Error: You need root/admin privileges to bind to port 53.")
        pIndex += 1
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
                print(f"{pIndex}: Cache hit for {qname}")
                pIndex += 1
                cached.header.id = req.header.id
                cached.questions = list(req.questions)
                print(f"{pIndex}: Forward response")
                pIndex += 1
                sock.sendto(cached.pack(), addr)
                continue
            else:
                del cache[key]
        try:
            response = doh_forward(data,timeout=2.0)

            ttl = get_min_ttl(response)
            if ttl > 0:
                cache[key] = {"resp": response, "added_at": time.time()}
            print(f"{pIndex}: Forward response")
            pIndex += 1
            sock.sendto(response, addr)
        except socket.timeout:
            print(f"{pIndex}: Timeout error")
            pIndex += 1
        except Exception as e:
            print(f"{pIndex}: Error: {e}")
            pIndex += 1

if __name__ == "__main__":
    startdns()