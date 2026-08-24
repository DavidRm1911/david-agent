"""DockerSandbox: runs a shell command inside an ephemeral, network-isolated
container with only `workspace` bind-mounted (at /workspace) — the agent
can't see or touch anything else on the host filesystem, matching CLAUDE.md
§15 ("trabajar en workspace/ sin acceso irrestricto al host").

No image is pulled and no container is started until run() is actually
called — same lazy-by-default principle as OllamaProvider.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from david_agent.sandbox.base import Sandbox
from david_agent.tools.base import ToolResult

DEFAULT_IMAGE = "python:3.12-slim"


class DockerSandbox(Sandbox):
    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        memory: str = "512m",
        cpus: str = "1",
        timeout: int = 60,
        network: bool = False,
    ) -> None:
        self._image = image
        self._memory = memory
        self._cpus = cpus
        self._timeout = timeout
        self._network = network

    def run(self, command: str, *, workspace: Path) -> ToolResult:
        workspace = workspace.resolve()
        # Named explicitly so a timeout can kill it by name — relying on
        # Docker to notice the client process died and clean up on its own
        # is not immediate: verified empirically, a killed `docker run`
        # process left its container `Up` and running for several seconds
        # afterward before Docker's own disconnect detection caught up.
        container_name = f"david-agent-sandbox-{uuid.uuid4().hex[:12]}"
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
            "-v",
            f"{workspace}:/workspace",
            "-w",
            "/workspace",
            "--memory",
            self._memory,
            "--cpus",
            self._cpus,
        ]
        if not self._network:
            cmd += ["--network", "none"]
        cmd += [self._image, "sh", "-c", command]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=10)
            return ToolResult(output="", error=f"sandboxed command timed out after {self._timeout}s")
        except FileNotFoundError:
            return ToolResult(output="", error="docker is not installed or not on PATH")

        if proc.returncode != 0:
            return ToolResult(output=proc.stdout, error=f"exit {proc.returncode}: {proc.stderr.strip()}")
        return ToolResult(output=proc.stdout or "(no output)")
