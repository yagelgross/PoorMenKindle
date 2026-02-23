import time


class DHCPIPPool:
    def __init__(self, base_ip, start, end):
        self.available_ips = [f"{base_ip}{i}" for i in range(start, end + 1)]
        self.leases = {}
        self.lease_time = 3600

    def get_ip(self, mac_address):
        if mac_address in self.leases:
            self.leases[mac_address]['expire'] = time.time() + self.lease_time
            return self.leases[mac_address]['ip']

        if len(self.available_ips) > 0:
            new_ip = self.available_ips.pop(0)
            self.leases[mac_address] = {
                'ip': new_ip,
                'expire': time.time() + self.lease_time
            }
            return new_ip

        return None

    def clear_leases(self):
        expired_macs = []
        for mac, data in self.leases.items():
            if time.time() > data['expire']:
                self.available_ips.append(data['ip'])
                expired_macs.append(mac)

        for mac in expired_macs:
            del self.leases[mac]

