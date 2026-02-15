import socket
import os

image_path = 'YagelWhiteHouse.png'

if not os.path.exists(image_path):
    print(f"Error: File {image_path} not found!")
    exit()

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('localhost', 12345))
s.listen(1)
while True:
    print('Waiting for a connection...')

    conn, addr = s.accept()
    print(f'Connected by {addr}')

    with open(image_path, 'rb') as f:
        image = f.read()

    x = len(image)
    print(f"Sending image size: {x}")

    conn.send(x.to_bytes(4, 'big'))

    data = conn.recv(1024)
    print(f"Received confirmation: {data}")

    if data.decode('utf-8').lower() == 'ok':
        print("Sending image data...")
        conn.sendall(image)
        print('Image sent successfully')
    else:
        print(f"Did not receive OK, received: {data}")

    conn.close()
s.close()