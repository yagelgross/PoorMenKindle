import socket


class DHCP:
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', 67))
        print("DHCP Server listening on port 67...")


if __name__ == "__main__":
    nat = DHCP()
    while True:
        nat.socket.recvfrom(1024)
