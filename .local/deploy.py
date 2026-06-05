import paramiko
import sys
import secrets
import string
import os
import re

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
        if item in ['.git', '.venv', 'venv', '__pycache__', '.local', 'instance', '.agents', '.gemini', 'logs', 'scratch', 'buchungssystem_local.json']:
            continue
            
        remote_path = remote_dir + "/" + item
        if os.path.isdir(local_path):
            upload_directory_sftp(sftp, local_path, remote_path)
        else:
            sftp.put(local_path, remote_path)

def get_multisystem_services(client):
    # Find all systemd service files starting with 'multisystem'
    stdin, stdout, stderr = client.exec_command("ls /etc/systemd/system/multisystem*.service")
    files = stdout.read().decode('utf-8').strip().split('\n')
    services = []
    for f in files:
        f = f.strip()
        if not f:
            continue
        service_name = os.path.basename(f).replace('.service', '')
        
        # Read the file to get WorkingDirectory
        _, s_out, _ = client.exec_command(f"grep 'WorkingDirectory=' {f}")
        wd_line = s_out.read().decode('utf-8').strip()
        wd_match = re.search(r'WorkingDirectory=(.+)', wd_line)
        if wd_match:
            wd = wd_match.group(1).strip()
            services.append((service_name, wd))
    return services

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
        
        # 1. Discover all active multisystem service deployments on the VPS
        print("Discovering active deployments on the VPS...")
        services = get_multisystem_services(client)
        if not services:
            print("No multisystem services found! Falling back to default /var/www/multisystem.")
            services = [("multisystem", "/var/www/multisystem")]
            
        print(f"Found {len(services)} instances to deploy to:")
        for s_name, wd in services:
            print(f"  - Service: {s_name} (Directory: {wd})")
        print("="*60)
        
        # 2. Deploy to each discovered instance
        for service_name, remote_dir in services:
            print(f"\n>>> Deploying to: {service_name} at {remote_dir} <<<")
            run_command(client, f"mkdir -p {remote_dir}", f"Ensuring directory {remote_dir} exists")
            
            # Upload files via SFTP
            print(f"Uploading files to {remote_dir}...")
            sftp = client.open_sftp()
            upload_directory_sftp(sftp, local_project_dir, remote_dir)
            sftp.close()
            print("File upload complete!")
            
            # Fix permissions
            run_command(client, f"chown -R www-data:www-data {remote_dir}", "Setting owner permissions")
            run_command(client, f"chmod -R 755 {remote_dir}", "Setting folder permissions")
            
            # Reload systemd and restart service
            run_command(client, "systemctl daemon-reload", "Reloading systemd daemon")
            run_command(client, f"systemctl restart {service_name} && systemctl enable {service_name}", f"Restarting {service_name}")
            
            # Wait a brief moment and check status
            import time
            time.sleep(1.5)
            run_command(client, f"systemctl status {service_name} --no-pager", f"Checking status of {service_name}")
            
        print("\n" + "="*60)
        print("DEPLOYMENT TO ALL INSTANCES COMPLETE.")
        print("="*60)
        client.close()
    except Exception as e:
        print("Deployment failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    deploy()
