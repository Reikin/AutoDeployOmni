import tarfile
import os

class FileManager:
    def __init__(self):
        pass

    def compress_files(self, base_path, file_list, output_path, root_dir="", log_callback=None, progress_callback=None):
        """
        Compress a list of files (relative to base_path) into a tar.gz file.
        If root_dir is provided, files will be placed inside this folder in the archive.
        """
        try:
            with tarfile.open(output_path, "w:gz") as tar:
                total = len(file_list)
                for index, file_rel_path in enumerate(file_list):
                    full_path = os.path.join(base_path, file_rel_path)
                    
                    # Determine archive name (path inside tar)
                    if root_dir:
                        arc_name = os.path.join(root_dir, file_rel_path)
                    else:
                        arc_name = file_rel_path

                    if os.path.exists(full_path):
                        tar.add(full_path, arcname=arc_name)
                        if log_callback:
                            log_callback(f"Adding {file_rel_path} ({index+1}/{total})")
                    else:
                        if log_callback:
                            log_callback(f"Warning: File not found {file_rel_path}")
                    
                    if progress_callback and total > 0:
                        percent = int((index + 1) / total * 100)
                        progress_callback(percent)
                        
            return True, f"Compressed to {output_path}"
        except Exception as e:
            return False, str(e)


    def get_all_files(self, directory, ignore_patterns=None):
        """
        Walk through directory and return list of relative paths.
        """
        file_paths = []
        # Basic ignore patterns if none provided
        if ignore_patterns is None:
            ignore_patterns = ['.git']
            
        for root, dirs, files in os.walk(directory):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_patterns]
            
            for file in files:
                if file not in ignore_patterns and not file.endswith('.pyc'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, directory)
                    file_paths.append(rel_path)
        return file_paths
