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
        
        # 1. Check postgres service
        print("\n--- pg_isready ---")
        out, _ = run_cmd(client, "pg_isready")
        print(out)
        
        # 2. List database users
        print("\n--- PostgreSQL Users ---")
        out, _ = run_cmd(client, "sudo -u postgres psql -c \"\\du\"")
        print(out)
        
        # 3. List databases
        print("\n--- PostgreSQL Databases ---")
        out, _ = run_cmd(client, "sudo -u postgres psql -c \"\\l\"")
        print(out)

        # 4. Test connection using psycopg2 on the server for both URLs
        print("\n--- Testing connections from python on VPS ---")
        test_script = """
import psycopg2
import sys

urls = {
    "User URL": "postgresql://learngrid_user:CjRwDdCyb0kvVtDRdZuceo6W@localhost:5432/learngrid",
    "Our URL": "postgresql://learngrid:learngrid_password@localhost:5432/learngrid"
}

for name, url in urls.items():
    print(f"Testing {name}...")
    try:
        conn = psycopg2.connect(url)
        print("  Connection SUCCESS!")
        cur = conn.cursor()
        cur.execute("SELECT version();")
        print("  Version:", cur.fetchone()[0])
        # Check tables in database
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        tables = [t[0] for t in cur.fetchall()]
        print("  Tables:", tables)
        # Check if there is an admin user
        if 'users' in tables:
            cur.execute("SELECT id, username, role, email FROM users;")
            users = cur.fetchall()
            print("  Users:", users)
        conn.close()
    except Exception as e:
        print("  Connection FAILED:", e)
"""
        # Run test script on VPS
        s_stdin, s_stdout, s_stderr = client.exec_command("python3")
        s_stdin.write(test_script)
        s_stdin.close()
        print(s_stdout.read().decode('utf-8', errors='replace'))
        print(s_stderr.read().decode('utf-8', errors='replace'))

        client.close()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
