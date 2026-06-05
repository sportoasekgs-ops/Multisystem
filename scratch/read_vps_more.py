import paramiko
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def run_cmd(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def main():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    print(f"Connecting to {host}...")
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        
        # 1. Print last 100 lines of journalctl
        print("\n--- journalctl -u multisystem -n 100 ---")
        out, _ = run_cmd(client, "journalctl -u multisystem -n 100 --no-pager")
        print(out)
        
        # 2. Print Nginx error logs
        print("\n--- Nginx Error Log ---")
        out, _ = run_cmd(client, "tail -n 30 /var/log/nginx/error.log")
        print(out)

        # 3. Print Nginx access logs
        print("\n--- Nginx Access Log ---")
        out, _ = run_cmd(client, "tail -n 30 /var/log/nginx/access.log")
        print(out)

        client.close()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
