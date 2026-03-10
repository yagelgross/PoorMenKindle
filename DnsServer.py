import socket
from dnslib import DNSRecord, RR, QTYPE, A # DNS parsing and building library
import certifi # provides Mozilla's CA bundle for SSL certificate verification
import time # used for cache expiration tracking
import urllib3 # HTTP client used to send DNS-over-HTTPS requests


# Default DNS server configuration
DnsPort = 53 # standard DNS port

# Cloudflare DNS-over-HTTPS (DoH) server configuration
DOH_IP = "1.1.1.1" # Cloudflare's public DNS IP address
DOH_HOST = "cloudflare-dns.com" # hostname for TLS certificate verification
DOH_PATH = "/dns-query" # API endpoint for DoH queries

pIndex = 0 # global print index for ordered debug logging

# Build a persistent HTTPS connection pool to Cloudflare's DoH server
http = urllib3.HTTPSConnectionPool(
    host=DOH_IP, # connect to Cloudflare's IP directly
    port=443, # standard HTTPS port
    cert_reqs="CERT_REQUIRED", # enforce SSL certificate validation
    ca_certs=certifi.where(), # use Mozilla's trusted CA bundle for verification
    assert_hostname=DOH_HOST, # verify the server's certificate matches the expected hostname
    server_hostname=DOH_HOST, # SNI hostname for TLS handshake
    headers={ # default headers sent with every request
        "Host": DOH_HOST, # required Host header for the DoH server
        "Content-Type": "application/dns-message", # indicates a raw DNS wire-format in the request body
        "Accept": "application/dns-message", # expects a raw DNS wire-format in the response
    },
    timeout=urllib3.util.Timeout(connect=2.0, read=2.0), # 2-second timeout for both connection and read
)

def doh_forward(query_bytes: bytes) -> bytes:
    """A method to forward a raw DNS query to Cloudflare's DoH server and return the response."""
    r = http.urlopen(
        "POST", # send the query as a POST request
        DOH_PATH, # the DoH API endpoint
        body=query_bytes, # raw DNS wire-format query as the request body
    )
    if r.status != 200: # check if the server returned a successful response
        raise Exception(f"Error: {r.status} {r.reason}")
    return r.data # return the raw DNS wire-format response

def get_min_ttl(resp_bytes: bytes) -> int:
    """A method to extract the minimum TTL from the answer section of a DNS response. Used for cache expiration."""
    reply = DNSRecord.parse(resp_bytes) # parse the raw DNS response bytes
    if not reply.rr: # if there are no answer records, don't cache
        return 0
    return min(rr.ttl for rr in reply.rr) # return the smallest TTL among all answer records

def get_my_ip():
    """A method to get the local IP address of the server."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # open a UDP socket
    # noinspection PyBroadException
    try:
        # try to connect to Google's DNS server and fetch the local IP address from the response packet
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        # if an error occurs, return the loopback address (127.0.0.1)
        ip = '127.0.0.1'
    finally:
        # close the socket
        s.close()
    return ip
def start_dns():
    """Main function to start the DNS-over-HTTPS proxy server."""
    global pIndex
    cache= {} # local cache for DNS responses, keyed by (qname, qtype, q_class)
    print(f"{pIndex}: DNS over HTTPS Server started") # debug print line
    pIndex+=1

    # Initialize DNS server socket (UDP port 53)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # open a UDP socket
    try:
        sock.bind(("0.0.0.0", DnsPort)) # bind to all interfaces on the DNS port
        print(f"{pIndex}: DNS active on port {DnsPort}") # debug print line
        pIndex += 1
    except PermissionError:
        # port 53 requires root/admin privileges
        print(f"{pIndex}: Error: You need root/admin privileges to bind to port 53.") # debug print line
        pIndex += 1
        return

    # Main DNS server loop
    while True:
        data, addr = sock.recvfrom(4096) # receive a DNS query packet from a client
        req = DNSRecord.parse(data) # parse the raw packet using dnslib

        # Extract query details from the DNS request
        qname = str(req.q.qname).rstrip(".") # the domain name being queried (strip trailing dot)
        qtype = req.q.qtype # the query type (e.g., A, AAAA, CNAME)
        q_class = req.q.qclass # the query class (usually IN for Internet)

        # Handle local resolution for "books.server" -> server's own IP
        if qname == "books.server" and qtype == QTYPE.A:
            local_ip = get_my_ip() # get the server's local IP address
            print(f"{pIndex}: Local resolve for {qname} -> {local_ip}") # debug print line
            pIndex += 1
            reply = req.reply() # create a reply based on the original request
            reply.add_answer(RR(qname, QTYPE.A, rdata=A(local_ip), ttl=60)) # add an A record pointing to the server's IP with a 60-second TTL
            sock.sendto(reply.pack(), addr) # send the response back to the client
            continue
        else:
            # For all other queries, check cache or forward to Cloudflare DoH
            key = (qname, qtype, q_class) # unique cache key for this query

            # Check if we have a cached response for this query
            if key in cache:
                cached_bytes = cache[key]["resp"] # the raw cached DNS response
                age = time.time() - cache[key]["added_at"] # how long ago we cached it
                cached = DNSRecord.parse(cached_bytes) # parse the cached response
                # noinspection PyBroadException
                try:
                    ttl = get_min_ttl(cached_bytes) # get the minimum TTL from the cached response
                except Exception:
                    ttl = 0
                # Serve from cache if the TTL hasn't expired
                if ttl > 0 and age <= ttl:
                    print(f"{pIndex}: Cache hit for {qname}") # debug print line
                    pIndex += 1
                    cached.header.id = req.header.id # match the transaction ID from the client's request
                    cached.questions = list(req.questions) # match the question section from the client's request
                    print(f"{pIndex}: Forward response") # debug print line
                    pIndex += 1
                    sock.sendto(cached.pack(), addr) # send the cached response back to the client
                    continue
                else:
                    # Cache entry has expired, remove it
                    del cache[key]

            # No valid cache entry found, forward the query to Cloudflare's DoH server
            try:
                response = doh_forward(data) # forward the raw DNS query and receive the response

                # Cache the response if it has a valid TTL
                ttl = get_min_ttl(response)
                if ttl > 0:
                    cache[key] = {"resp": response, "added_at": time.time()} # store the response with a timestamp
                print(f"{pIndex}: Forward response") # debug print line
                pIndex += 1
                sock.sendto(response, addr) # send the DoH response back to the client
            except socket.timeout:
                print(f"{pIndex}: Timeout error") # debug print line
                pIndex += 1
            except Exception as e:
                # Log any errors during packet processing
                print(f"{pIndex}: Error: {e}") # debug print line
                pIndex += 1

if __name__ == "__main__":
    start_dns()