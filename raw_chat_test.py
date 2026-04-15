import socket, json

def raw_post(host, port, path, body_dict, timeout=30):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        body = json.dumps(body_dict).encode()
        req = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        s.sendall(req.encode() + body)
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
        return data.decode('utf-8', errors='replace')
    except Exception as e:
        s.close()
        return f"ERROR: {e}"

body = {
    "query": "vendor payment terms for company code 1000",
    "user_role": "AP_CLERK",
    "domain": "auto",
    "use_swarm": False
}

print("=== POST /api/v1/chat/master-data ===")
result = raw_post('127.0.0.1', 8000, '/api/v1/chat/master-data', body, timeout=60)
# Print first 800 chars
print(result[:800])