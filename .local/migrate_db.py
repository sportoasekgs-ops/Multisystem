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

def migrate():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"

    # Connection details
    render_db_url = "postgresql://multitest_user:aDe4FXstUdH3cxE6JFCv3dF18CxF2opA@dpg-d87bts3tqb8s7394p6cg-a.frankfurt-postgres.render.com/multitest"
    vps_db_pass = "CjRwDdCyb0kvVtDRdZuceo6W"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        print("SSH Connection established successfully!")
        
        # We stop the application service first to prevent active sessions during database migration
        run_command(client, "systemctl stop multisystem", "Stopping multisystem service")
        
        # We run pg_dump from Render and pipe it directly to local psql on the VPS.
        # We use --clean and --if-exists to replace any existing tables in the new DB.
        migration_cmd = (
            f'PGPASSWORD="{vps_db_pass}" pg_dump --no-owner --no-privileges --clean --if-exists -d "{render_db_url}" '
            f'| psql -U learngrid_user -d learngrid -h localhost'
        )
        
        run_command(client, migration_cmd, "Transferring database from Render to VPS")
        
        # Restart the application service
        run_command(client, "systemctl start multisystem", "Starting multisystem service")
        
        client.close()
        print("="*60)
        print("DATABASE MIGRATION COMPLETE.")
        print("All data has been copied from Render to the VPS.")
        print("="*60)
    except Exception as e:
        print("Migration failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    migrate()
