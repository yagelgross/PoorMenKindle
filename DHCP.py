import socket
from scapy.layers.dhcp import BOOTP, DHCP
from scapy.all import srp1
from scapy.layers.l2 import Ether, ARP
import netifaces

import DHCPIPPool

# Check if an IP address is already in use by sending an ARP request
def is_available(ip):
    arp_request = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip)
    reply = srp1(arp_request, timeout=0.1, verbose=0)
    return reply is None

# Detect the local machine's IP address by connecting to a public DNS server
def get_my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Initialize DHCP server socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(("", 67))
print("DHCP Server is running and listening on port 67...")

# Initialize IP pool and server configuration
SERVER_IP = get_my_ip()

# Retrieve default gateway and network interface information
gws = netifaces.gateways()
GATEWAY = gws['default'][netifaces.AF_INET][0]

# Get network interface details to extract netmask
iface = gws['default'][netifaces.AF_INET][1]
addrs = netifaces.ifaddresses(iface)
NETMASK = addrs[netifaces.AF_INET][0]['netmask']

# Create an IP pool based on the server's network subnet (IPs 150-230)
base_prefix = '.'.join(SERVER_IP.split('.')[:-1]) + '.'
IPPool = DHCPIPPool.DHCPIPPool(base_ip=base_prefix, start=150, end=230)

DNS_SERVER = SERVER_IP

# Main DHCP server loop
while True:
    IPPool.clear_leases()
    data, address = sock.recvfrom(1024)

    try:
        packet = BOOTP(data)
        if DHCP in packet:
            # Extract client MAC address and transaction ID
            raw_mac = packet[BOOTP].chaddr
            mac_raw_address = raw_mac[:6]
            client_mac = ':'.join(f'{b:02x}' for b in mac_raw_address)
            xid = packet[BOOTP].xid
            msg_type = None

            # Find DHCP message type from packet options
            for option in packet[DHCP].options:
                if isinstance(option, tuple) and option[0] == 'message-type':
                    msg_type = option[1]
                    break

            # Handle DHCP Discover (message type 1)
            if msg_type == 1:
                print(f"[+] DHCP Discover received from MAC: {client_mac}")
                client_ip = IPPool.get_ip(client_mac)

                # Ensure the assigned IP is not already in use on the network
                while client_ip is not None and not is_available(client_ip):
                    if client_mac in IPPool.leases:
                        del IPPool.leases[client_mac]
                    client_ip = IPPool.get_ip(client_mac)

                if client_ip is None:
                    print("[-] IP Pool is empty, cannot offer an IP.")
                    continue

                # Send DHCP Offer response with network configuration
                resp = BOOTP(
                    op=2,
                    xid=xid,
                    yiaddr=client_ip,
                    siaddr=SERVER_IP,
                    chaddr=raw_mac
                ) / DHCP(
                    options=[
                        ('message-type', 'offer'),
                        ('server_id', SERVER_IP),
                        ('lease_time', 3600),
                        ('subnet_mask', NETMASK),
                        ('router', GATEWAY),
                        ('name_server', DNS_SERVER),
                        'end'
                    ]
                )
                print(f"[+] Sent DHCP Offer with IP {client_ip} to MAC: {client_mac}")
                sock.sendto(bytes(resp), ("255.255.255.255", 68))


            # Handle DHCP Request (message type 3)
            elif msg_type == 3:
                print(f"[+] DHCP Request received from MAC: {client_mac}")
                req_server_id = None
                req_ip = None

                # Extract server ID and requested IP from client options
                for option in packet[DHCP].options:
                    if isinstance(option, tuple):
                        if option[0] == 'server_id':
                            req_server_id = option[1]
                        elif option[0] == 'requested_addr':
                            req_ip = option[1]
                client_ip = IPPool.get_ip(client_mac)

                print(f"[*] Client {client_mac} is requesting IP: {req_ip} from Server: {req_server_id}")

                # Send DHCP ACK only if the client selected this server and requested the correct IP
                if req_server_id == SERVER_IP and req_ip == client_ip:
                    print(f"[+] SUCCESS! Client chose OUR server. Sending ACK for IP: {client_ip}")
                    resp = BOOTP(
                        op=2,
                        xid=xid,
                        yiaddr=client_ip,
                        siaddr=SERVER_IP,
                        chaddr=raw_mac
                    ) / DHCP(
                        options=[
                            ('message-type', 'ack'),
                            ('server_id', SERVER_IP),
                            ('lease_time', 3600),
                            ('subnet_mask', NETMASK),
                            ('router', GATEWAY),
                            ('name_server', DNS_SERVER),
                            'end'
                        ]
                    )
                    sock.sendto(bytes(resp), ("255.255.255.255", 68))
                else:
                    print(f"[-] Client chose another DHCP server ({req_server_id}). Ignoring request.")

            else:
                # Log unexpected message types
                print(f"[-] Other DHCP message type ({msg_type}) from: {client_mac}")

    except Exception as e:
        # Log any errors during packet processing
        print(f"[-] Error processing packet: {e}")
