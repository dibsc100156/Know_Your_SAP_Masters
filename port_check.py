import socket
for port in [8000, 8001]:
    s = socket.socket()
    s.settimeout(2)
    r = s.connect_ex(('127.0.0.1', port))
    print(f'Port {port}: {"OPEN" if r==0 else f"CLOSED({r})"}')
    s.close()