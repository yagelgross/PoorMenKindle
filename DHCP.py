import socket
from scapy.layers.dhcp import BOOTP, DHCP
from scapy.all import srp1
from scapy.layers.l2 import Ether, ARP
import netifaces

import DHCPIPPool



def is_available(ip):
    """A method to check if an IP address is already in use by sending an ARP request"""
    arp_request = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip) # build the ARP request
    print("Checking if IP is available: ", ip, "")
    reply = srp1(arp_request, timeout=0.1, verbose=0) # send and wait for a reply
    return reply is None # ensure no reply, which means the IP is available

def get_my_ip():
    """A method to get the local IP address of the server."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # open a UDP socket
    # noinspection PyBroadException
    try:
        # try to connect to Google's DNS server and fetch the local IP address from the response packet
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        #if an error occurs, return the loopback address (127.0.0.1)
        ip = '127.0.0.1'
    finally:
        # close the socket
        s.close()
    return ip

# Initialize DHCP server socket (UDP port 67)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # enable address reuse to allow multiple servers on the same machine (for testing)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) # enable broadcast to send responses to all clients in the network
sock.bind(("", 67)) # bind the socket to the default DHCP port
print("DHCP Server is running and listening on port 67...") # debug print line

SERVER_IP = get_my_ip() # Initialize IP pool and server configuration

# The following lines (40 to 47) were given to us by AI, we did not know about the netifaces library and were not familiar with it.
gws = netifaces.gateways() # Retrieve default gateway and network interface information
GATEWAY = gws['default'][netifaces.AF_INET][0] # Extract the gateway IP address

# Get network interface details to extract netmask
iface = gws['default'][netifaces.AF_INET][1] # Extract the network interface name
addrs = netifaces.ifaddresses(iface) # Retrieve IP addresses associated with the interface
NETMASK = addrs[netifaces.AF_INET][0]['netmask'] # Extract the network mask

# initiate a DHCPPIPPool object with the server's IP address as the base address'
base_prefix = '.'.join(SERVER_IP.split('.')[:-1]) + '.'
IPPool = DHCPIPPool.DHCPIPPool(base_ip=base_prefix, start=150, end=230)

DNS_SERVER = SERVER_IP # Set DNS server to the server's IP address'

# Main DHCP server loop
while True:
    IPPool.clear_leases() # at every iteration, clear expired leases from the pool to free up IPs for new clients
    data, address = sock.recvfrom(1024) # receive a packet from the client

    try:
        packet = BOOTP(data) # parse the packet using scapy's BOOTP layer
        if DHCP in packet:
            # Extract client MAC address and transaction ID, as well as all the other DHCP options
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
                print(f"[+] DHCP Discover received from MAC: {client_mac}") # debug print line
                client_ip = IPPool.get_ip(client_mac)

                # Ensure the assigned IP is not already in use on the network
                while client_ip is not None and not is_available(client_ip):
                    if client_mac in IPPool.leases:
                        del IPPool.leases[client_mac]
                    client_ip = IPPool.get_ip(client_mac) # try again with a new IP

                if client_ip is None:
                    print("[-] IP Pool is empty, cannot offer an IP.")
                    continue

                # Send DHCP Offer response with network configuration
                resp = BOOTP(
                    op=2, # DHCP Offer
                    xid=xid, # Transaction ID from the client
                    yiaddr=client_ip, # Client's IP address
                    siaddr=SERVER_IP, # Server's IP address
                    chaddr=raw_mac # Client's MAC address
                ) / DHCP( # DHCP options
                    options=[
                        ('message-type', 'offer'), # DHCP Offer message type
                        ('server_id', SERVER_IP), # Server's IP address'
                        ('lease_time', 3600), # Lease time for the IP address, 1 hour
                        ('subnet_mask', NETMASK), # Network mask
                        ('router', GATEWAY), # Default gateway
                        ('name_server', DNS_SERVER), # the DNS server's IP address
                        'end'
                    ]
                )
                print(f"[+] Sent DHCP Offer with IP {client_ip} to MAC: {client_mac}")
                sock.sendto(bytes(resp), ("255.255.255.255", 68)) # broadcast the response


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
