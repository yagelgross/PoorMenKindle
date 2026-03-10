import time


class DHCPIPPool:
    """A class to manage a pool of IP addresses for a private DHCP implementation that will not clash with the network."""
    def __init__(self, base_ip, start, end):
        """Initialize the pool with a base IP address, starting and ending IP addresses."""
        self.available_ips = [f"{base_ip}{i}" for i in range(start, end + 1)]
        self.leases = {}
        self.lease_time = 3600

    def get_ip(self, mac_address):
        """A method to get an IP address from the pool and confirming its availability. If no IP is available, return None."""
        if mac_address in self.leases: # first, check if the mac address is already leased
            self.leases[mac_address]['expire'] = time.time() + self.lease_time # if it is, renew the lease
            return self.leases[mac_address]['ip'] #return the leased ip

        if len(self.available_ips) > 0: # if there are available ips, return one
            new_ip = self.available_ips.pop(0) # get the first available ip
            self.leases[mac_address] = {
                'ip': new_ip,
                'expire': time.time() + self.lease_time
            } # add it to the leased dictionary
            return new_ip

        return None # if no ip is available, return None

    def clear_leases(self):
        """ A method to ensure that all leases are renewed and any expired leases are removed from the pool."""
        expired_macs = [] # list to store expired mac addresses
        for mac, data in self.leases.items(): # for each mac address in the leases, check if the lease has expired
            if time.time() > data['expire']:
                self.available_ips.append(data['ip']) # if it has expired, add the ip back to the available pool
                expired_macs.append(mac) # add the mac address to the list of expired Macs

        for mac in expired_macs: # for each expired mac address, remove it from the leases
            del self.leases[mac]

