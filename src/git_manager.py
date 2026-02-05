import git
import os

class GitManager:
    def __init__(self):
        pass

    def validate_repo(self, path):
        try:
            _ = git.Repo(path)
            return True, "Valid Git repository"
        except git.InvalidGitRepositoryError:
            return False, "Not a valid Git repository"
        except Exception as e:
            return False, str(e)

    def pull(self, repo_path, output_callback=None):
        try:
            repo = git.Repo(repo_path)
            origin = repo.remotes.origin
            
            if output_callback:
                output_callback(f"Starting git pull in {repo_path}...")
                
            info_list = origin.pull()
            
            summary = []
            for info in info_list:
                if info.flags & info.ERROR:
                    msg = f"Error: {info.ref} - {info.note}"
                    summary.append(msg)
                    if output_callback: output_callback(msg)
                elif info.flags & info.HEAD_UPTODATE:
                    msg = f"Up to date: {info.ref}"
                    summary.append(msg)
                    if output_callback: output_callback(msg)
                else:
                    msg = f"Updated: {info.ref} from {info.old_commit} to {info.commit}"
                    summary.append(msg)
                    if output_callback: output_callback(msg)
            
            return True, "\n".join(summary)
        except git.exc.GitCommandError as e:
            error_hint = ""
            if "Authentication failed" in e.stderr or "403" in e.stderr:
                error_hint = "\n[Hint] Authentication failed. Check your credentials on using a Personal Access Token (PAT) if you are using HTTPS."
            elif "Merge attempt failed" in e.stderr:
                error_hint = "\n[Hint] Merge conflict detected. Please resolve conflicts manually."
            
            error_msg = f"{e.stderr}{error_hint}"
            if output_callback: output_callback(error_msg)
            return False, error_msg
        except Exception as e:
            if output_callback: output_callback(str(e))
            return False, str(e)

    def get_tags(self, repo_path):
        try:
            repo = git.Repo(repo_path)
            tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime, reverse=True)
            return [str(tag) for tag in tags]
        except Exception:
            return []

    def archive_repo(self, repo_path, tag, output_path, prefix="", output_callback=None):
        try:
            repo = git.Repo(repo_path)
            if output_callback: output_callback(f"Archiving tag '{tag}' to {output_path} with prefix '{prefix}'...")
            
            with open(output_path, 'wb') as f:
                # Ensure prefix ends with / if not empty, required/typical for git archive prefix
                if prefix and not prefix.endswith('/'):
                    prefix += '/'
                elif not prefix:
                    prefix = "" # ensure empty string if None
                    
                repo.archive(f, treeish=tag, format='tar.gz', prefix=prefix)
                
            return True, f"Successfully archived {tag}"
        except Exception as e:
            return False, str(e)
