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

def enable_external():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        print("SSH Connection established successfully!")
        
        # 1. Update postgresql.conf to listen on all interfaces
        # On Ubuntu 24.04, the path is /etc/postgresql/16/main/postgresql.conf
        listen_cmd = "sed -i \"s/#listen_addresses = 'localhost'/listen_addresses = '*'/g\" /etc/postgresql/16/main/postgresql.conf"
        # In case it was already uncommented or different:
        listen_cmd_alt = "sed -i \"s/listen_addresses = 'localhost'/listen_addresses = '*'/g\" /etc/postgresql/16/main/postgresql.conf"
        
        run_command(client, listen_cmd, "Setting listen_addresses to '*'")
        run_command(client, listen_cmd_alt, "Setting listen_addresses to '*' (fallback)")
        
        # 2. Append access rule to pg_hba.conf
        # We append a rule allowing md5 password connections from any IPv4 address
        rule = "host    all             all             0.0.0.0/0               md5"
        append_cmd = f"echo '{rule}' >> /etc/postgresql/16/main/pg_hba.conf"
        run_command(client, append_cmd, "Adding MD5 access rule to pg_hba.conf")
        
        # 3. Restart PostgreSQL service
        run_command(client, "systemctl restart postgresql", "Restarting PostgreSQL to apply changes")
        
        client.close()
        print("="*60)
        print("VPS DATABASE EXTERNAL ACCESS ENABLED.")
        print("="*60)
    except Exception as e:
        print("Failed to enable external access:", e)
        sys.exit(1)

if __name__ == "__main__":
    enable_external()
