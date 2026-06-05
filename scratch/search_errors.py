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
        
        # Get last 500 lines of journalctl for multisystem
        stdin, stdout, stderr = client.exec_command("journalctl -u multisystem -n 500 --no-pager")
        logs = stdout.read().decode('utf-8', errors='replace').splitlines()
        
        print("=== FILTERED LOGS (Tracebacks, Errors, Login, Redirects) ===")
        capture_traceback = False
        traceback_lines = []
        
        for line in logs:
            lower_line = line.lower()
            # If we detect a traceback starting
            if "traceback" in lower_line or "stack trace" in lower_line:
                capture_traceback = True
                traceback_lines.append(line)
                continue
                
            if capture_traceback:
                if line.startswith("Jun") and not ("gunicorn[" in line and (line.find("gunicorn[") > 20 or "  " in line)):
                    # A new syslog line starting (not indented traceback)
                    capture_traceback = False
                    if traceback_lines:
                        print("\n--- TRACEBACK ---")
                        for tb_line in traceback_lines:
                            print(tb_line)
                        print("-----------------\n")
                    traceback_lines = []
                else:
                    traceback_lines.append(line)
                    continue
            
            # Print other relevant events
            if any(k in lower_line for k in ["error", "exception", "failed", "login", "dashboard", "setup", "admin"]):
                # Skip the warnings about IServ
                if "iserv oauth ist nicht vollständig konfiguriert" in lower_line or "bitte domain, client-id" in lower_line:
                    continue
                print(line)
                
        if traceback_lines:
            print("\n--- TRACEBACK ---")
            for tb_line in traceback_lines:
                print(tb_line)
            print("-----------------\n")

        client.close()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
