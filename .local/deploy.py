import paramiko
import sys
import secrets
import string
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def run_command(client, command, desc=""):
    print(f"--- Running: {desc or command} ---")
    stdin, stdout, stderr = client.exec_command(command)
    
    while True:
        line = stdout.readline()
        if not line:
            break
        safe_line = line.strip().encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        print("  OUT:", safe_line)
        
    err = stderr.read().decode('utf-8', errors='replace')
    if err:
        print("  ERR:", err.strip())
        
    exit_status = stdout.channel.recv_exit_status()
    print(f"Finished with exit status: {exit_status}\n")
    return exit_status == 0

def upload_directory_sftp(sftp, local_dir, remote_dir):
    try:
        sftp.mkdir(remote_dir)
    except IOError:
        pass # Already exists
        
    for item in os.listdir(local_dir):
        local_path = os.path.join(local_dir, item)
        if item in ['.git', '.venv', 'venv', '__pycache__', '.local', 'instance', '.agents', '.gemini', 'logs']:
            continue
            
        remote_path = remote_dir + "/" + item
        if os.path.isdir(local_path):
            upload_directory_sftp(sftp, local_path, remote_path)
        else:
            sftp.put(local_path, remote_path)

def deploy():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"
    local_project_dir = r"c:\Users\Mauro\Desktop\MULTI REPLIT SYSTEM\Multisystem"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        print("SSH Connection established successfully!")
        
        # 1. Ensure target directories exist
        run_command(client, "mkdir -p /var/www/multisystem", "Creating web directory")
        
        # 2. Upload files via SFTP
        print("Uploading files via SFTP...")
        sftp = client.open_sftp()
        upload_directory_sftp(sftp, local_project_dir, "/var/www/multisystem")
        sftp.close()
        print("File upload complete!")

        # 3. Use the DB password
        db_password = "CjRwDdCyb0kvVtDRdZuceo6W"
        db_url = f"postgresql://learngrid_user:{db_password}@localhost:5432/learngrid"
        local_config_content = f'{{\n  "database_url": "{db_url}"\n}}'
        
        sftp = client.open_sftp()
        with sftp.file("/var/www/multisystem/buchungssystem_local.json", "w") as f:
            f.write(local_config_content)
        sftp.close()
        print("local_config JSON created/verified.")

        # 4. Create virtual env if not present
        run_command(client, "python3 -m venv /var/www/multisystem/venv", "Creating Python virtual environment")
        run_command(client, "/var/www/multisystem/venv/bin/pip install --upgrade pip", "Upgrading pip")
        run_command(client, "/var/www/multisystem/venv/bin/pip install -r /var/www/multisystem/requirements.txt", "Installing project python requirements")
        
        # 5. Fix permissions
        run_command(client, "chown -R www-data:www-data /var/www/multisystem", "Setting owner permissions")
        run_command(client, "chmod -R 755 /var/www/multisystem", "Setting folder permissions")

        # 6. Create Gunicorn systemd service with SESSION_SECRET
        print("Writing systemd service file...")
        session_secret_val = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        service_content = f"""[Unit]
Description=LernGrid Multisystem Booking Application
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/var/www/multisystem
Environment="SESSION_SECRET={session_secret_val}"
ExecStart=/var/www/multisystem/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 --threads 4 app:app
Restart=always

[Install]
WantedBy=multi-user.target
"""
        sftp = client.open_sftp()
        with sftp.file("/etc/systemd/system/multisystem.service", "w") as f:
            f.write(service_content)
        sftp.close()

        # Reload systemd and start service
        run_command(client, "systemctl daemon-reload", "Reloading systemd daemon")
        run_command(client, "systemctl restart multisystem && systemctl enable multisystem", "Starting/Restarting & enabling multisystem app service")
        
        # Wait a brief moment for service to spin up, then check status
        import time
        time.sleep(2)
        run_command(client, "systemctl status multisystem --no-pager", "Checking multisystem service status")

        # 7. Configure Nginx Server Block
        print("Writing Nginx server block...")
        nginx_block = """server {
    listen 80;
    server_name igsbadenstedt.learngrid.app;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""
        sftp = client.open_sftp()
        with sftp.file("/etc/nginx/sites-available/multisystem", "w") as f:
            f.write(nginx_block)
        sftp.close()

        run_command(client, "ln -sf /etc/nginx/sites-available/multisystem /etc/nginx/sites-enabled/default", "Linking Nginx site configuration")
        run_command(client, "nginx -t", "Testing Nginx configuration")
        run_command(client, "systemctl restart nginx", "Restarting Nginx")

        client.close()
        print("="*60)
        print("DEPLOYMENT STEP 1 COMPLETE.")
        print("Nginx reverse proxy is running at http://igsbadenstedt.learngrid.app")
        print("="*60)
    except Exception as e:
        print("Deployment failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    deploy()
