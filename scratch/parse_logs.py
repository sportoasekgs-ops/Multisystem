import paramiko
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        
        # Get last 150 lines of journalctl for multisystem
        stdin, stdout, stderr = client.exec_command("journalctl -u multisystem -n 150 --no-pager")
        logs = stdout.read().decode('utf-8', errors='replace').splitlines()
        
        print(f"=== VPS LOGS ({len(logs)} lines) ===")
        for line in logs:
            print(line)
            
        client.close()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
