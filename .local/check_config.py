import paramiko
import sys

def check_config():
    host = "87.106.155.5"
    user = "root"
    secret = "VaXp4ngpdJwTQ"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(host, username=user, password=secret, timeout=10)
        print("SSH Connection established successfully!")
        
        stdin, stdout, stderr = client.exec_command("cat /var/www/multisystem/buchungssystem_local.json")
        output = stdout.read().decode('utf-8')
        print("--- buchungssystem_local.json ---")
        print(output)
        
        client.close()
    except Exception as e:
        print("Failed to read config:", e)
        sys.exit(1)

if __name__ == "__main__":
    check_config()
