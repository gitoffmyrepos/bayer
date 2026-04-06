"""
GitOps Auto-Remediator — fixes cluster issues by editing GitOps manifests.

Workflow:
  1. Detect issue (crash-loop, OOM, image pull error, resource exhaustion)
  2. Identify which manifest in sb-gitops controls the affected resource
  3. Generate fix using LLM (Qwen3.5-27B via Ollama)
  4. Apply fix to local sb-gitops clone
  5. Commit + push → ArgoCD auto-syncs
  6. Verify fix applied (pod becomes healthy)
  7. Notify Discord with fix summary

Author: Nova ⚡ | Nightwatch Platform
"""

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
import yaml

log = structlog.get_logger("nightwatch.remediation.gitops")


@dataclass(frozen=True)
class RemediationResult:
    """Immutable result of a remediation attempt."""
    success: bool
    issue_type: str
    resource_name: str
    fix_description: str
    manifest_path: Optional[str] = None
    commit_sha: Optional[str] = None
    verified: bool = False
    error: Optional[str] = None
    steps_taken: list = field(default_factory=list)
    duration_seconds: float = 0.0


class GitOpsRemediator:
    """Auto-fixes cluster issues by editing GitOps manifests and pushing."""

    # Issue types safe for auto-remediation (no human approval needed)
    SAFE_AUTO_FIX = {
        "oom_kill",
        "crash_loop_backoff",
        "image_pull_error",
        "liveness_probe_failure",
        "readiness_probe_failure",
        "startup_probe_failure",
        "resource_quota_exceeded",
        "pending_pod_scheduling",
    }

    def __init__(self, repos_config: dict, llm_client, alert_manager=None):
        self.repos = {
            "fx": Path(repos_config.get("fx", {}).get("path", "/repos/fx")),
            "gitops": Path(repos_config.get("gitops", {}).get("path", "/repos/sb-gitops")),
            "infra": Path(repos_config.get("infra", {}).get("path", "/repos/sb-dev-infra")),
        }
        self.llm = llm_client
        self.alert_manager = alert_manager
        self._manifest_cache: dict[str, str] = {}

        # Validate repos exist
        for name, path in self.repos.items():
            if path.exists():
                log.info(f"repo_available: {name} at {path}")
            else:
                log.warning(f"repo_missing: {name} at {path}")

    def find_manifest_for_resource(
        self, namespace: str, resource_type: str, resource_name: str
    ) -> Optional[tuple[str, str]]:
        """Find the GitOps manifest YAML file for a K8s resource.

        Returns (file_path, yaml_content) or None.
        """
        gitops = self.repos["gitops"]
        search_dirs = [
            gitops / "prod" / "application" / "manifests" / "forextrader-platform",
            gitops / "prod" / "application" / "manifests" / "forextrader-platform" / "microservices",
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for yaml_file in search_dir.glob("*.yaml"):
                try:
                    content = yaml_file.read_text()
                    if resource_name in content:
                        self._manifest_cache[resource_name] = str(yaml_file)
                        return str(yaml_file), content
                except Exception as e:
                    log.debug(f"error_reading_manifest: {yaml_file}: {e}")

        log.warning(f"manifest_not_found: {resource_name} in {namespace}")
        return None

    def generate_fix(
        self, issue_type: str, resource_name: str, error_context: str, current_manifest: str
    ) -> Optional[dict]:
        """Use LLM to generate a YAML fix for the issue.

        Returns {fixed_yaml, description, changes_made} or None.
        """
        prompt = f"""You are a Kubernetes operations expert. Fix the following issue in this YAML manifest.

ISSUE TYPE: {issue_type}
RESOURCE: {resource_name}
ERROR CONTEXT:
{error_context[:2000]}

CURRENT MANIFEST (relevant section):
```yaml
{current_manifest[:3000]}
```

RULES:
- For oom_kill: increase memory limit by 50% (e.g., 256Mi → 384Mi, 1Gi → 1536Mi)
- For crash_loop_backoff: add or increase startupProbe (failureThreshold: 30, periodSeconds: 10)
- For liveness/readiness probe failure: increase timeoutSeconds and periodSeconds
- For image_pull_error: verify the image tag format is correct
- For resource_quota_exceeded: reduce resource requests by 20%
- For pending_pod_scheduling: check nodeSelector and tolerations

Return ONLY the corrected YAML section (the container spec or the full deployment spec that changed).
Also include a one-line description of what you changed.

Format:
DESCRIPTION: <one-line description>
```yaml
<corrected yaml>
```"""

        try:
            response = self.llm._call(prompt)
            # Parse description
            desc_match = re.search(r"DESCRIPTION:\s*(.+)", response)
            description = desc_match.group(1).strip() if desc_match else f"Auto-fix for {issue_type}"

            # Parse YAML
            yaml_match = re.search(r"```yaml\s*\n(.*?)```", response, re.DOTALL)
            if not yaml_match:
                yaml_match = re.search(r"```\s*\n(.*?)```", response, re.DOTALL)
            if not yaml_match:
                log.error("llm_no_yaml_in_response", resource=resource_name)
                return None

            fixed_yaml = yaml_match.group(1).strip()

            # Validate YAML is parseable
            yaml.safe_load(fixed_yaml)

            return {
                "fixed_yaml": fixed_yaml,
                "description": description,
                "issue_type": issue_type,
            }
        except Exception as e:
            log.error(f"llm_fix_generation_failed: {e}", resource=resource_name)
            return None

    def apply_fix(self, manifest_path: str, fix: dict) -> bool:
        """Apply the LLM-generated fix to the manifest file.

        Uses a targeted replacement strategy based on issue type.
        """
        try:
            original = Path(manifest_path).read_text()
            fixed_yaml = fix["fixed_yaml"]
            issue_type = fix["issue_type"]

            # Parse the fix to find the container name or resource section
            fix_parsed = yaml.safe_load(fixed_yaml)

            if issue_type in ("oom_kill", "resource_quota_exceeded"):
                # Replace the resources section
                new_content = self._replace_resources_section(original, fix_parsed)
            elif issue_type in ("crash_loop_backoff", "liveness_probe_failure",
                                "readiness_probe_failure", "startup_probe_failure"):
                # Replace or add probe sections
                new_content = self._replace_probe_section(original, fix_parsed)
            else:
                # Generic: replace the entire container spec
                new_content = self._generic_replace(original, fixed_yaml)

            if new_content and new_content != original:
                # Validate the new YAML
                for doc in yaml.safe_load_all(new_content):
                    pass  # Just validate it parses

                Path(manifest_path).write_text(new_content)
                log.info(f"fix_applied: {manifest_path}", description=fix["description"])
                return True
            else:
                log.warning("fix_no_change: generated fix identical to original")
                return False

        except Exception as e:
            log.error(f"fix_apply_failed: {e}", manifest=manifest_path)
            return False

    def _replace_resources_section(self, original: str, fix_parsed: dict) -> Optional[str]:
        """Replace memory/cpu limits in the manifest."""
        # Find resources block and replace limits/requests
        if isinstance(fix_parsed, dict):
            resources = fix_parsed.get("resources", fix_parsed)
            limits = resources.get("limits", {})
            if limits.get("memory"):
                # Simple regex replacement for memory limit
                new_memory = limits["memory"]
                result = re.sub(
                    r'(limits:\s*\n\s*(?:cpu:[^\n]*\n\s*)?memory:\s*)"[^"]*"',
                    f'\\1"{new_memory}"',
                    original,
                )
                if result == original:
                    result = re.sub(
                        r"(limits:\s*\n\s*(?:cpu:[^\n]*\n\s*)?memory:\s*)\S+",
                        f"\\g<1>{new_memory}",
                        original,
                    )
                return result
        return None

    def _replace_probe_section(self, original: str, fix_parsed: dict) -> Optional[str]:
        """Add or replace probe configuration."""
        # If startupProbe doesn't exist, add it
        if "startupProbe" in str(fix_parsed):
            if "startupProbe:" not in original:
                # Insert before readinessProbe or livenessProbe
                indent = "          "
                probe_yaml = yaml.dump({"startupProbe": fix_parsed.get("startupProbe", fix_parsed)},
                                        default_flow_style=False)
                probe_lines = "\n".join(f"{indent}{line}" for line in probe_yaml.strip().split("\n"))
                # Insert before readinessProbe
                return original.replace(
                    f"{indent}readinessProbe:",
                    f"{probe_lines}\n{indent}readinessProbe:",
                )
            else:
                # Replace existing startupProbe
                probe_yaml = yaml.dump(fix_parsed, default_flow_style=False)
                return re.sub(
                    r"startupProbe:.*?(?=\n\s*\w+Probe:|\n\s*volumeMounts:|\n\s*env:)",
                    probe_yaml.strip(),
                    original,
                    flags=re.DOTALL,
                )
        return original

    def _generic_replace(self, original: str, fixed_yaml: str) -> Optional[str]:
        """Generic replacement — try to match and replace the section."""
        # Fallback: just return original with a comment about the suggested fix
        log.warning("generic_replace: could not auto-apply, manual review needed")
        return None

    def commit_and_push(self, manifest_path: str, description: str) -> Optional[str]:
        """Git add, commit, and push the fix."""
        repo_dir = None
        for name, path in self.repos.items():
            if manifest_path.startswith(str(path)):
                repo_dir = str(path)
                break

        if not repo_dir:
            log.error(f"commit_failed: manifest {manifest_path} not in any known repo")
            return None

        try:
            # Pull latest first
            subprocess.run(["git", "pull", "--rebase"], cwd=repo_dir,
                          capture_output=True, timeout=30)

            # Add and commit
            rel_path = os.path.relpath(manifest_path, repo_dir)
            subprocess.run(["git", "add", rel_path], cwd=repo_dir,
                          capture_output=True, check=True, timeout=10)

            commit_msg = f"fix(nightwatch): {description}"
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=repo_dir, capture_output=True, text=True, timeout=10,
            )

            if result.returncode != 0:
                if "nothing to commit" in result.stdout:
                    log.info("commit_skipped: no changes to commit")
                    return None
                log.error(f"commit_failed: {result.stderr}")
                return None

            # Push
            push_result = subprocess.run(
                ["git", "push"], cwd=repo_dir,
                capture_output=True, text=True, timeout=30,
            )
            if push_result.returncode != 0:
                log.error(f"push_failed: {push_result.stderr}")
                return None

            # Get commit SHA
            sha_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_dir, capture_output=True, text=True, timeout=5,
            )
            sha = sha_result.stdout.strip()
            log.info(f"fix_pushed: {sha}", manifest=rel_path, description=description)
            return sha

        except Exception as e:
            log.error(f"git_operation_failed: {e}")
            return None

    def verify_fix(self, namespace: str, resource_name: str, timeout: int = 300) -> bool:
        """Poll the resource status to check if the fix worked."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = subprocess.run(
                    ["kubectl", "get", "pod", "-n", namespace, "-l",
                     f"app={resource_name}", "--no-headers"],
                    capture_output=True, text=True, timeout=10,
                )
                lines = [l for l in result.stdout.strip().split("\n") if l]
                if lines:
                    # Check if all pods are Running with 0 recent restarts
                    all_healthy = all(
                        "Running" in line and line.split()[3] == "0"
                        for line in lines
                        if len(line.split()) >= 4
                    )
                    if all_healthy:
                        log.info(f"fix_verified: {resource_name} is healthy")
                        return True
            except Exception:
                pass
            time.sleep(15)

        log.warning(f"fix_verification_timeout: {resource_name} not healthy after {timeout}s")
        return False

    def rollback_if_failed(self, manifest_path: str, original_content: str) -> bool:
        """Revert the manifest to original and push."""
        try:
            Path(manifest_path).write_text(original_content)
            sha = self.commit_and_push(manifest_path, "rollback: revert failed auto-fix")
            if sha:
                log.info(f"rollback_pushed: {sha}", manifest=manifest_path)
                return True
        except Exception as e:
            log.error(f"rollback_failed: {e}")
        return False

    async def remediate(
        self, issue_type: str, namespace: str, resource_name: str, error_context: str
    ) -> RemediationResult:
        """Full remediation pipeline: find → fix → apply → push → verify."""
        start = time.time()
        steps = []

        # Safety check
        if issue_type not in self.SAFE_AUTO_FIX:
            return RemediationResult(
                success=False, issue_type=issue_type, resource_name=resource_name,
                fix_description="Issue type not in safe auto-fix list",
                error=f"Unsupported issue type for auto-fix: {issue_type}",
                steps_taken=["safety_check_failed"],
            )

        # Step 1: Find manifest
        steps.append("finding_manifest")
        manifest = self.find_manifest_for_resource(namespace, "deployment", resource_name)
        if not manifest:
            return RemediationResult(
                success=False, issue_type=issue_type, resource_name=resource_name,
                fix_description="Could not find GitOps manifest",
                error="Manifest not found in sb-gitops",
                steps_taken=steps,
                duration_seconds=time.time() - start,
            )

        manifest_path, manifest_content = manifest
        original_content = manifest_content  # Save for rollback

        # Step 2: Generate fix via LLM
        steps.append("generating_fix")
        fix = self.generate_fix(issue_type, resource_name, error_context, manifest_content)
        if not fix:
            return RemediationResult(
                success=False, issue_type=issue_type, resource_name=resource_name,
                fix_description="LLM could not generate a fix",
                manifest_path=manifest_path,
                error="Fix generation failed",
                steps_taken=steps,
                duration_seconds=time.time() - start,
            )

        # Step 3: Apply fix
        steps.append("applying_fix")
        applied = self.apply_fix(manifest_path, fix)
        if not applied:
            return RemediationResult(
                success=False, issue_type=issue_type, resource_name=resource_name,
                fix_description=fix["description"],
                manifest_path=manifest_path,
                error="Could not apply fix to manifest",
                steps_taken=steps,
                duration_seconds=time.time() - start,
            )

        # Step 4: Commit and push
        steps.append("committing_and_pushing")
        sha = self.commit_and_push(manifest_path, fix["description"])
        if not sha:
            self.rollback_if_failed(manifest_path, original_content)
            return RemediationResult(
                success=False, issue_type=issue_type, resource_name=resource_name,
                fix_description=fix["description"],
                manifest_path=manifest_path,
                error="Git push failed — rolled back",
                steps_taken=steps,
                duration_seconds=time.time() - start,
            )

        # Step 5: Verify
        steps.append("verifying_fix")
        verified = self.verify_fix(namespace, resource_name, timeout=300)
        if not verified:
            steps.append("rollback_after_failed_verification")
            self.rollback_if_failed(manifest_path, original_content)

        return RemediationResult(
            success=verified,
            issue_type=issue_type,
            resource_name=resource_name,
            fix_description=fix["description"],
            manifest_path=manifest_path,
            commit_sha=sha,
            verified=verified,
            steps_taken=steps,
            duration_seconds=time.time() - start,
        )

    def pull_repos(self):
        """Pull latest from all repos."""
        for name, path in self.repos.items():
            if path.exists() and (path / ".git").exists():
                try:
                    subprocess.run(
                        ["git", "pull", "--rebase"],
                        cwd=str(path), capture_output=True, timeout=30,
                    )
                    log.info(f"repo_pulled: {name}")
                except Exception as e:
                    log.warning(f"repo_pull_failed: {name}: {e}")
