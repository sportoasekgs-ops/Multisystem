import paramiko
import sys

def run_command(client, command, desc=""):
    print(f"--- Running: {desc or command} ---")
    stdin, stdout, stderr = client.exec_command(command)
    
    while True:
        line = stdout.readline()
        if not line:
            break
        print("  OUT:", line.strip())
        
    err = stderr.read().decode('utf-8', errors='replace')
    if err:
        print("  ERR:", err.strip())
        
    exit_status = stdout.channel.recv_exit_status()
    print(f"Finished with exit status: {exit_status}\n")
    return exit_status == 0

def setup_ssl():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"
    domain = "igsbadenstedt.learngrid.app"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        print("SSH Connection established successfully!")
        
        # Execute certbot
        # We pass --nginx, -d, --non-interactive, --agree-tos, and an admin email.
        certbot_cmd = f"certbot --nginx -d {domain} --non-interactive --agree-tos -m admin@learngrid.app --redirect"
        run_command(client, certbot_cmd, f"Requesting SSL Certificate for {domain}")
        
        # Reload Nginx just in case
        run_command(client, "systemctl reload nginx", "Reloading Nginx web server")
        
        client.close()
    except Exception as e:
        print("SSL setup failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    setup_ssl()
