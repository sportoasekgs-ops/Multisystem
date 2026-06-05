import paramiko
import sys

# Reconfigure stdout to use UTF-8 to prevent charmap codec errors on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def check_logs():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        print("SSH Connection established successfully!")
        
        stdin, stdout, stderr = client.exec_command("journalctl -u multisystem --no-pager -n 100")
        output = stdout.read().decode('utf-8', errors='replace')
        print("--- GUNICORN SYSTEMD LOGS ---")
        # Ensure we encode/decode safely
        safe_output = output.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        print(safe_output)
        
        client.close()
    except Exception as e:
        print("Failed to read logs:", e)
        sys.exit(1)

if __name__ == "__main__":
    check_logs()
