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
        
        script_content = """
from app import app
from models import User, db, create_user

with app.app_context():
    u = User.query.filter_by(username='admin').first()
    if u:
        u.set_password('Admin1234!')
        db.session.commit()
        print('Admin password updated successfully to Admin1234!')
    else:
        uid = create_user('admin', 'Admin1234!', 'admin')
        if uid:
            print('Admin user did not exist, created new admin with password Admin1234!')
        else:
            print('Failed to create admin user.')
"""
        
        # Write script to VPS via SFTP
        sftp = client.open_sftp()
        with sftp.file("/var/www/multisystem/reset_admin.py", "w") as f:
            f.write(script_content)
        sftp.close()
        
        # Run it with SESSION_SECRET environment variable set
        cmd = "export SESSION_SECRET=temp_secret_for_reset_123 && cd /var/www/multisystem && venv/bin/python3 reset_admin.py && rm reset_admin.py"
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        
        print("=== VPS COMMAND OUTPUT ===")
        print(out)
        if err:
            print("=== VPS COMMAND ERROR ===")
            print(err)
            
        client.close()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
