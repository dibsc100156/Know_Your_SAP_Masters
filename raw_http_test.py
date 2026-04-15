import socket

def raw_http_request(host, port, path, timeout=5):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        s.sendall(req.encode())
        data = b''
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
        s.close()
        return data.decode('utf-8', errors='replace')[:600]
    except Exception as e:
        s.close()
        return f"ERROR: {e}"

print("=== Testing port 8000 ===")
result = raw_http_request('127.0.0.1', 8000, '/health')
print(result)
print()
print("=== Testing port 8000 /api/v1/chat/master-data ===")
result2 = raw_http_request('127.0.0.1', 8000, '/api/v1/chat/master-data')
print(result2)