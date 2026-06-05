import paramiko
import sys

# Set standard output encoding to UTF-8
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
        
        # 1. Read config
        print("\n--- buchungssystem_local.json ---")
        out, _ = run_cmd(client, "cat /var/www/multisystem/buchungssystem_local.json")
        print(out)
        
        # 2. Check service status
        print("\n--- systemctl status multisystem ---")
        out, _ = run_cmd(client, "systemctl status multisystem")
        print(out)
        
        # 3. Check environment variables of the service
        print("\n--- systemctl cat multisystem ---")
        out, _ = run_cmd(client, "systemctl cat multisystem")
        print(out)
        
        # 4. Check journal logs
        print("\n--- journalctl -u multisystem -n 50 ---")
        out, _ = run_cmd(client, "journalctl -u multisystem -n 50 --no-pager")
        print(out)

        client.close()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
