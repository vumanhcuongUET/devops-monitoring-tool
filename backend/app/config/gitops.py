"""
GitOps Management Module

Provides Git-based configuration management with branch strategies,
PR workflows, and synchronization capabilities.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import subprocess
import logging
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)


class GitBranch(Enum):
    """Git branch types."""
    MAIN = "main"
    DEVELOP = "develop"
    FEATURE = "feature"
    HOTFIX = "hotfix"
    RELEASE = "release"


class GitOpsManager:
    """Manage GitOps workflow for configurations."""

    def __init__(self, repo_path: str, auto_push: bool = False):
        """Initialize GitOps manager.

        Args:
            repo_path: Path to Git repository
            auto_push: Whether to automatically push changes
        """
        self.repo_path = Path(repo_path)
        self.auto_push = auto_push
        self.current_branch = self._get_current_branch()

        # Validate repository
        if not self._is_git_repo():
            raise ValueError(f"Not a Git repository: {repo_path}")

    def _is_git_repo(self) -> bool:
        """Check if path is a Git repository."""
        git_dir = self.repo_path / ".git"
        return git_dir.exists()

    def _get_current_branch(self) -> str:
        """Get current Git branch."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to get current branch: {e}")
            return "unknown"

    def _run_git_command(
        self,
        args: List[str],
        check: bool = True,
        capture: bool = True
    ) -> subprocess.CompletedProcess:
        """Run Git command with error handling."""
        cmd = ["git"] + args
        try:
            return subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=capture,
                text=True,
                check=check
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}")
            logger.error(f"stdout: {e.stdout}")
            logger.error(f"stderr: {e.stderr}")
            raise

    async def get_repo_status(self) -> Dict[str, Any]:
        """Get repository status."""
        # Get branch status
        status_result = self._run_git_command(["status", "--porcelain"])
        has_changes = bool(status_result.stdout.strip())

        # Get current branch
        branch = self._get_current_branch()

        # Get remote tracking
        remote_result = self._run_git_command(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            check=False
        )
        remote = remote_result.stdout.strip() if remote_result.returncode == 0 else None

        # Get last commit
        log_result = self._run_git_command(["log", "-1", "--format=%H %s"])
        last_commit = log_result.stdout.strip().split(" ", 1)

        return {
            "branch": branch,
            "remote": remote,
            "has_uncommitted_changes": has_changes,
            "last_commit_hash": last_commit[0] if last_commit else None,
            "last_commit_message": last_commit[1] if len(last_commit) > 1 else None,
            "repo_path": str(self.repo_path)
        }

    async def create_feature_branch(
        self,
        project: str,
        author: str,
        base_branch: str = "develop"
    ) -> str:
        """Create a feature branch for config change.

        Args:
            project: Project name
            author: Author name
            base_branch: Base branch to branch from

        Returns:
            New branch name
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"config/{project}/{timestamp}"

        # Ensure we're on base branch and up to date
        await self.checkout_branch(base_branch)
        await self.pull_changes(base_branch)

        # Create and checkout new branch
        self._run_git_command(["checkout", "-b", branch_name])

        logger.info(f"Created feature branch {branch_name} for {project} by {author}")
        return branch_name

    async def checkout_branch(self, branch: str) -> bool:
        """Checkout a branch."""
        try:
            self._run_git_command(["checkout", branch])
            self.current_branch = branch
            logger.info(f"Checked out branch {branch}")
            return True
        except subprocess.CalledProcessError:
            logger.error(f"Failed to checkout branch {branch}")
            return False

    async def commit_change(
        self,
        project: str,
        author: str,
        message: str,
        files: Optional[List[str]] = None
    ) -> str:
        """Commit configuration change to Git.

        Args:
            project: Project name
            author: Author information
            message: Commit message
            files: Specific files to stage (None = all project files)

        Returns:
            Commit hash
        """
        # Stage files
        if files:
            for file_path in files:
                self._run_git_command(["add", file_path])
        else:
            # Stage all project files
            project_path = f"projects/{project}"
            self._run_git_command(["add", project_path])

        # Check if there are changes to commit
        status_result = self._run_git_command(["diff", "--cached", "--name-only"])
        if not status_result.stdout.strip():
            logger.warning(f"No changes to commit for {project}")
            return ""

        # Commit with author info
        commit_msg = f"[{project}] {message}\n\nAuthor: {author}"
        result = self._run_git_command(["commit", "-m", commit_msg])

        # Extract commit hash
        commit_hash = ""
        if result.returncode == 0:
            hash_result = self._run_git_command(["rev-parse", "HEAD"])
            commit_hash = hash_result.stdout.strip()

        logger.info(f"Committed changes for {project}: {commit_hash[:8]}")

        # Auto push if enabled
        if self.auto_push:
            await self.push_changes()

        return commit_hash

    async def create_pull_request(
        self,
        project: str,
        branch_name: str,
        title: str,
        description: str,
        base_branch: str = "develop"
    ) -> Dict[str, Any]:
        """Create pull request for review.

        Args:
            project: Project name
            branch_name: Source branch
            title: PR title
            description: PR description
            base_branch: Target branch

        Returns:
            PR information
        """
        # Try using GitHub CLI
        try:
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", title,
                    "--body", description,
                    "--base", base_branch,
                    "--head", branch_name
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )

            # Extract PR URL/number from output
            pr_url = result.stdout.strip()

            # Get PR number
            if "github.com" in pr_url:
                pr_number = pr_url.split("/")[-1]
            else:
                pr_number = "unknown"

            logger.info(f"Created PR #{pr_number} for {project}")
            return {
                "success": True,
                "url": pr_url,
                "number": pr_number,
                "branch": branch_name,
                "base": base_branch
            }

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"GitHub CLI not available or failed: {e}")

            # Fallback: manual PR creation instructions
            return {
                "success": False,
                "manual": True,
                "instructions": f"""
                Manual PR Required:
                - Source branch: {branch_name}
                - Target branch: {base_branch}
                - Title: {title}
                - Description: {description}

                Create PR at: {self._get_repo_url()}/compare/{base_branch}...{branch_name}
                """,
                "branch": branch_name,
                "base": base_branch
            }

    async def merge_pull_request(
        self,
        pr_number: int,
        method: str = "squash"
    ) -> bool:
        """Merge pull request after approval.

        Args:
            pr_number: PR number
            method: Merge method (merge, squash, rebase)

        Returns:
            True if merged successfully
        """
        try:
            if method == "squash":
                args = ["pr", "merge", str(pr_number), "--squash"]
            elif method == "rebase":
                args = ["pr", "merge", str(pr_number), "--rebase"]
            else:
                args = ["pr", "merge", str(pr_number)]

            subprocess.run(
                ["gh"] + args,
                cwd=self.repo_path,
                check=True,
                timeout=30
            )

            logger.info(f"Merged PR #{pr_number} using {method}")
            return True

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"Failed to merge PR #{pr_number}: {e}")
            return False

    async def pull_changes(
        self,
        branch: Optional[str] = None
    ) -> bool:
        """Pull latest changes from remote.

        Args:
            branch: Branch to pull (None = current branch)

        Returns:
            True if successful
        """
        target_branch = branch or self.current_branch

        try:
            # Checkout branch if specified
            if branch and branch != self.current_branch:
                await self.checkout_branch(branch)

            # Pull changes
            self._run_git_command(["pull", "origin", target_branch])

            logger.info(f"Pulled latest changes for {target_branch}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to pull changes: {e}")
            return False

    async def push_changes(
        self,
        branch: Optional[str] = None,
        force: bool = False
    ) -> bool:
        """Push changes to remote.

        Args:
            branch: Branch to push (None = current branch)
            force: Whether to force push

        Returns:
            True if successful
        """
        target_branch = branch or self.current_branch

        try:
            args = ["push", "origin", target_branch]
            if force:
                args.append("--force")

            self._run_git_command(args)

            logger.info(f"Pushed changes to {target_branch}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to push changes: {e}")
            return False

    async def sync_from_git(
        self,
        branch: str = "develop"
    ) -> List[str]:
        """Sync configurations from Git.

        Args:
            branch: Branch to sync from

        Returns:
            List of changed projects
        """
        # Pull latest changes
        success = await self.pull_changes(branch)

        if not success:
            logger.error(f"Failed to sync from Git (branch: {branch})")
            return []

        # Identify changed projects
        changed = self._get_changed_projects(branch)

        logger.info(f"Synced from Git, changed projects: {changed}")
        return changed

    def _get_changed_projects(self, branch: str = "develop") -> List[str]:
        """Get list of changed projects."""
        try:
            # Get changed files since last merge
            result = self._run_git_command([
                "diff", "--name-only", f"origin/{branch}..HEAD"
            ], check=False)

            changed_files = result.stdout.strip().split('\n')
            projects = set()

            for file_path in changed_files:
                if file_path.startswith("projects/"):
                    parts = file_path.split('/')
                    if len(parts) > 1:
                        projects.add(parts[1])

            return list(projects)

        except subprocess.CalledProcessError:
            return []

    async def get_commit_history(
        self,
        project: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get commit history for a project.

        Args:
            project: Project name
            limit: Maximum number of commits

        Returns:
            List of commits
        """
        try:
            path = f"projects/{project}"
            result = self._run_git_command([
                "log",
                f"--max-count={limit}",
                "--pretty=format:%H|%ai|%an|%s",
                "--", path
            ])

            commits = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('|', 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "timestamp": parts[1],
                        "author": parts[2],
                        "message": parts[3]
                    })

            return commits

        except subprocess.CalledProcessError:
            return []

    async def tag_version(
        self,
        version: str,
        message: str,
        project: Optional[str] = None
    ) -> bool:
        """Create a version tag.

        Args:
            version: Tag version
            message: Tag message
            project: Optional project name

        Returns:
            True if successful
        """
        try:
            tag_name = f"{project}/{version}" if project else version

            # Create annotated tag
            self._run_git_command([
                "tag", "-a", tag_name, "-m", message
            ])

            # Push tag
            self._run_git_command([
                "push", "origin", tag_name
            ])

            logger.info(f"Created and pushed tag {tag_name}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create tag: {e}")
            return False

    async def get_file_diff(
        self,
        file_path: str,
        version_a: Optional[str] = None,
        version_b: Optional[str] = None
    ) -> str:
        """Get diff for a file between two versions.

        Args:
            file_path: Path to file
            version_a: First version (None = working tree)
            version_b: Second version (None = HEAD)

        Returns:
            Diff output
        """
        try:
            v_a = version_a if version_a else "HEAD"
            v_b = version_b if version_b else ""

            result = self._run_git_command([
                "diff", v_a, v_b, "--", file_path
            ], check=False)

            return result.stdout

        except subprocess.CalledProcessError:
            return ""

    def _get_repo_url(self) -> str:
        """Get repository URL."""
        try:
            result = self._run_git_command([
                "config", "--get", "remote.origin.url"
            ], check=False)

            url = result.stdout.strip()
            # Convert to web URL if possible
            if url.startswith("git@"):
                url = url.replace(":", "/").replace("git@", "https://")
            if url.endswith(".git"):
                url = url[:-4]
            return url

        except subprocess.CalledProcessError:
            return "unknown"

    async def validate_repo(self) -> Dict[str, Any]:
        """Validate repository health."""
        status = await self.get_repo_status()

        issues = []

        # Check for uncommitted changes
        if status["has_uncommitted_changes"]:
            issues.append("Uncommitted changes exist")

        # Check if behind remote
        if status["remote"]:
            try:
                result = self._run_git_command([
                    "rev-list", "--count", "--left-right",
                    f"{status['remote']}...HEAD"
                ], check=False)

                if result.returncode == 0:
                    behind, ahead = result.stdout.strip().split('\t')
                    if int(behind) > 0:
                        issues.append(f"Behind remote by {behind} commits")
                    if int(ahead) > 0:
                        issues.append(f"Ahead of remote by {ahead} commits")
            except (subprocess.CalledProcessError, ValueError):
                pass

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "status": status
        }
