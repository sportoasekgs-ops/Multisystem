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
        
        # 1. Clean the PostgreSQL database (drop and recreate public schema)
        print("\n--- Resetting PostgreSQL Database ---")
        cmd = 'PGPASSWORD=CjRwDdCyb0kvVtDRdZuceo6W psql -h localhost -U learngrid_user -d learngrid -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
        out, err = run_cmd(client, cmd)
        print("Out:", out)
        if err:
            print("Err:", err)
            
        # 2. Delete buchungssystem_local.json
        print("\n--- Deleting local database configuration file ---")
        cmd = 'rm -f /var/www/multisystem/buchungssystem_local.json'
        out, err = run_cmd(client, cmd)
        print("Out:", out)
        if err:
            print("Err:", err)
            
        # 3. Restart the multisystem service
        print("\n--- Restarting Gunicorn (multisystem.service) ---")
        cmd = 'systemctl restart multisystem'
        out, err = run_cmd(client, cmd)
        print("Out:", out)
        if err:
            print("Err:", err)
            
        print("\n--- Verifying service status ---")
        cmd = 'systemctl status multisystem --no-pager'
        out, err = run_cmd(client, cmd)
        print(out)

        client.close()
        print("\n=============================================")
        print("RESET SUCCESSFUL. Web app is now in bootstrap mode.")
        print("=============================================")
    except Exception as e:
        print("Failed to perform reset:", e)

if __name__ == "__main__":
    main()
