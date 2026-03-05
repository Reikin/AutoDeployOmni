import paramiko
import os
import threading

class SSHManager:
    def __init__(self):
        self.client = None
        self.sftp = None
        self.host = ""
        self.port = 22
        self.username = ""
    
    def connect(self, host, port, username, password=None, key_path=None):
        """
        Connect to the SSH server using password or private key.
        """
        try:
            self.host = host
            self.port = int(port)
            self.username = username
            
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": 10
            }
            
            if key_path and os.path.exists(key_path):
                # Only support RSA/Ed25519 keys efficiently via paramiko's auto discovery or explicit loading
                # For simplicity, we try loading as generic key
                pkey = paramiko.PKey.from_private_key_file(key_path)
                connect_kwargs["pkey"] = pkey
            elif password:
                connect_kwargs["password"] = password
            else:
                 raise ValueError("Neither password nor key_path provided.")

            self.client.connect(**connect_kwargs)
            self.sftp = self.client.open_sftp()
            return True, "Connected successfully"
        except Exception as e:
            return False, str(e)

    def execute_command(self, command, output_callback=None, sudo_password=None):
        """
        Execute a command and stream output to callback. 
        Supports sudo if sudo_password is provided (assumes command uses 'sudo -S').
        """
        if not self.client:
            return False, "Not connected"

        try:
            stdin, stdout, stderr = self.client.exec_command(command, get_pty=True)
            
            if sudo_password:
                stdin.write(sudo_password + "\n")
                stdin.flush()
            
            if output_callback:
                # Read stdout line by line
                for line in iter(stdout.readline, ""):
                    output_callback(line.strip())
            
            exit_status = stdout.channel.recv_exit_status()
            return exit_status == 0, f"Command finished with status {exit_status}"
        except Exception as e:
            return False, str(e)

    def upload_file(self, local_path, remote_path, progress_callback=None):
        """
        Upload a file via SFTP.
        """
        if not self.sftp:
            return False, "SFTP not initialized"
        
        try:
            self.sftp.put(local_path, remote_path, callback=progress_callback)
            return True, "Upload successful"
        except Exception as e:
            return False, str(e)
            
    def check_file_exists(self, remote_path):
        """
        Check if a file exists on the remote server.
        """
        if not self.sftp:
            return False
        try:
            self.sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def detect_running_service(self, project_name, search_path=None):
        """
        Detect the working directory and compose file by project name.
        1. Search Docker containers (running or stopped).
        2. Fallback: Search directories in search_path (default: ~).
        Returns (True, [(working_dir, compose_filename), ...]) if found, (False, error_msg) otherwise.
        """
        if not self.client:
            return False, "Not connected"

        try:
            results = []
            # 1. Find container ID by name filter (Include stopped containers with -a)
            cmd_ps = f"docker ps -a --filter \"name={project_name}\" --format \"{{{{.ID}}}}\""
            stdin, stdout, stderr = self.client.exec_command(cmd_ps)
            ids = stdout.read().decode().strip().split('\n')
            ids = [x for x in ids if x] 
            
            if ids:
                for container_id in ids:
                    cmd_inspect = f"docker inspect --format \"{{{{ index .Config.Labels \\\"com.docker.compose.project.working_dir\\\" }}}}|{{{{ index .Config.Labels \\\"com.docker.compose.project.config_files\\\" }}}}\" {container_id}"
                    
                    stdin, stdout, stderr = self.client.exec_command(cmd_inspect)
                    output = stdout.read().decode().strip()
                    
                    if output and "|" in output:
                        working_dir, config_files = output.split("|", 1)
                        
                        if working_dir == '<no value>': working_dir = ""
                        if config_files == '<no value>': config_files = ""
                        
                        if working_dir:
                            # Parse config file
                            compose_filename = "docker-compose.yml" # Default
                            if config_files:
                                first_file = config_files.split(",")[0].strip()
                                if first_file:
                                    compose_filename = os.path.basename(first_file)
                            
                            entry = (working_dir, compose_filename)
                            if entry not in results:
                                results.append(entry)

            # 3. Fallback: Search File System if Docker yielded no results or inspection failed
            if not results:
                if not search_path:
                    search_path = "~"
                    
                # Search in target dir for directories matching the keyword
                cmd_find = f"find {search_path} -maxdepth 3 -type d -name \"*{project_name}*\" 2>/dev/null"
                stdin, stdout, stderr = self.client.exec_command(cmd_find)
                found_paths = stdout.read().decode().strip().split('\n')
                
                for fpath in found_paths:
                    fpath = fpath.strip()
                    if fpath:
                        entry = (fpath, "docker-compose.yml")
                        if entry not in results:
                            results.append(entry)
            
            if results:
                return True, results

            return False, f"No container or directory found for '{project_name}'"

        except Exception as e:
            return False, f"Detection failed: {str(e)}"

    def list_working_dir_files(self, remote_dir):
        """
        List .yml and .yaml files in the remote directory.
        """
        if not self.client:
            return False, "Not connected"

        try:
            # List both .yml and .yaml
            # 2>/dev/null to suppress error if no matches for one pattern
            cmd = f"cd {remote_dir} && ls -1 *.yml *.yaml 2>/dev/null"
            stdin, stdout, stderr = self.client.exec_command(cmd)
            
            output = stdout.read().decode().strip()
            if not output:
                # check if dir exists at least
                cmd_check = f"[ -d {remote_dir} ] && echo 'yes' || echo 'no'"
                stdin, stdout, stderr = self.client.exec_command(cmd_check)
                if stdout.read().decode().strip() != 'yes':
                    return False, f"Directory {remote_dir} does not exist"
                return True, [] # Dir exists but no yml files

            files = output.split('\n')
            files = [f.strip() for f in files if f.strip().endswith(('.yml', '.yaml'))]
            return True, files
            
        except Exception as e:
            return False, f"List files failed: {str(e)}"

    def list_scripts(self, remote_dir):
        """
        List .sh files in the remote directory.
        """
        if not self.client:
            return False, "Not connected"

        try:
            cmd = f"cd {remote_dir} && ls -1 *.sh 2>/dev/null"
            stdin, stdout, stderr = self.client.exec_command(cmd)
            
            output = stdout.read().decode().strip()
            if not output:
                return True, []

            files = output.split('\n')
            files = [f.strip() for f in files if f.strip().endswith('.sh')]
            return True, files
            
        except Exception as e:
            return False, str(e)

    def close(self):
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()
