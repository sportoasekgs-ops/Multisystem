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
        
        # 1. Run psql command to list tables
        print("\n--- Tables in learngrid ---")
        cmd = "PGPASSWORD=CjRwDdCyb0kvVtDRdZuceo6W psql -h localhost -U learngrid_user -d learngrid -c \"\\dt\""
        out, err = run_cmd(client, cmd)
        print(out)
        if err:
            print("Err:", err)
            
        # 2. Run psql command to select users
        print("\n--- Users in learngrid ---")
        cmd = "PGPASSWORD=CjRwDdCyb0kvVtDRdZuceo6W psql -h localhost -U learngrid_user -d learngrid -c \"SELECT id, username, role, email FROM users;\""
        out, err = run_cmd(client, cmd)
        print(out)
        if err:
            print("Err:", err)

        client.close()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
