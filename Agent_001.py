"""
Agent_001 - Main Orchestration Agent

Responsible for:
- Monitoring other agents' status and current jobs
- Assigning tasks based on research and user input
- Installing dependencies as needed
- Controlling workflow and resource allocation
"""

import importlib
import json
import logging
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

# Allowlist pattern for installable package names (PEP 508 name component).
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Agent_001] %(levelname)s: %(message)s",
)
logger = logging.getLogger("Agent_001")


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class Task:
    task_id: str
    agent_id: str
    description: str
    payload: dict = field(default_factory=dict)
    priority: int = 1
    status: str = "pending"


@dataclass
class AgentInfo:
    agent_id: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[Task] = None
    handler: Optional[Callable] = None


class Agent001:
    """Main orchestration agent that manages all other agents."""

    def __init__(self):
        self._agents: dict[str, AgentInfo] = {}
        self._task_queue: list[Task] = []
        self._lock = threading.Lock()
        self._running = False
        self._task_counter = 0

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, handler: Callable) -> None:
        """Register a sub-agent with its task handler callable."""
        with self._lock:
            self._agents[agent_id] = AgentInfo(agent_id=agent_id, handler=handler)
        logger.info("Registered agent: %s", agent_id)

    def get_agent_status(self, agent_id: str) -> Optional[AgentStatus]:
        """Return the current status of a registered agent."""
        info = self._agents.get(agent_id)
        return info.status if info else None

    def list_agents(self) -> dict[str, str]:
        """Return a mapping of agent IDs to their current statuses."""
        return {aid: info.status.value for aid, info in self._agents.items()}

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def submit_task(
        self,
        agent_id: str,
        description: str,
        payload: Optional[dict] = None,
        priority: int = 1,
    ) -> str:
        """Queue a task for a specific agent and return the task ID."""
        with self._lock:
            self._task_counter += 1
            task = Task(
                task_id=f"task-{self._task_counter:04d}",
                agent_id=agent_id,
                description=description,
                payload=payload or {},
                priority=priority,
            )
            self._task_queue.append(task)
            self._task_queue.sort(key=lambda t: t.priority, reverse=True)
        logger.info("Task %s queued for agent %s: %s", task.task_id, agent_id, description)
        return task.task_id

    def _dispatch_tasks(self) -> None:
        """Dispatch pending tasks to idle agents."""
        with self._lock:
            pending = [t for t in self._task_queue if t.status == "pending"]
            for task in pending:
                agent = self._agents.get(task.agent_id)
                if agent and agent.status == AgentStatus.IDLE and agent.handler:
                    task.status = "running"
                    agent.status = AgentStatus.BUSY
                    agent.current_task = task
                    threading.Thread(
                        target=self._run_task,
                        args=(agent, task),
                        daemon=True,
                    ).start()

    def _run_task(self, agent: AgentInfo, task: Task) -> None:
        """Execute a task in its agent's handler and update status."""
        logger.info("Agent %s starting task %s", agent.agent_id, task.task_id)
        try:
            agent.handler(task.payload)
            task.status = "completed"
            logger.info("Agent %s completed task %s", agent.agent_id, task.task_id)
        except Exception as exc:  # noqa: BLE001
            task.status = "error"
            logger.error(
                "Agent %s failed task %s: %s", agent.agent_id, task.task_id, exc
            )
            with self._lock:
                agent.status = AgentStatus.ERROR
            return
        with self._lock:
            agent.status = AgentStatus.IDLE
            agent.current_task = None

    # ------------------------------------------------------------------
    # Dependency installation
    # ------------------------------------------------------------------

    def install_dependency(self, package: str) -> bool:
        """Install a Python package via pip if it is not already available.

        The package name is validated against PEP 508 naming rules before
        being passed to pip to prevent command-injection via untrusted input.
        """
        # Validate package name before invoking pip
        name_part = package.split("==")[0].split(">=")[0].split("<=")[0].strip()
        if not _PACKAGE_NAME_RE.match(name_part):
            logger.error("Refusing to install package with invalid name: %r", package)
            return False
        try:
            importlib.import_module(name_part.replace("-", "_"))
            logger.info("Dependency already satisfied: %s", package)
            return True
        except ImportError:
            pass
        logger.info("Installing dependency: %s", package)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Successfully installed: %s", package)
            return True
        logger.error("Failed to install %s: %s", package, result.stderr)
        return False

    # ------------------------------------------------------------------
    # Workflow control
    # ------------------------------------------------------------------

    def start(self, poll_interval: float = 1.0) -> None:
        """Start the orchestration loop."""
        self._running = True
        logger.info("Agent_001 orchestration loop started.")
        try:
            while self._running:
                self._dispatch_tasks()
                self._log_status()
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("Shutdown requested.")
        finally:
            self._running = False
            logger.info("Agent_001 stopped.")

    def stop(self) -> None:
        """Signal the orchestration loop to stop."""
        self._running = False

    def _log_status(self) -> None:
        """Periodically log the status of all registered agents."""
        status_map = self.list_agents()
        logger.debug("Agent statuses: %s", json.dumps(status_map))


# ---------------------------------------------------------------------------
# Example usage / entry-point
# ---------------------------------------------------------------------------

def _example_agent_002_handler(payload: dict) -> None:
    """Placeholder handler that delegates to Agent_002."""
    # Import lazily so Agent_001 can run without Agent_002 present.
    from Agent_002 import Agent002  # type: ignore[import]

    agent = Agent002()
    action = payload.get("action", "status")
    if action == "serve":
        agent.serve(host=payload.get("host", "0.0.0.0"), port=payload.get("port", 8080))
    else:
        logger.info("Agent_002 status: %s", agent.status())


def _example_husler_handler(payload: dict) -> None:
    """Placeholder handler that delegates to Husler_bot2."""
    from Husler_bot2 import HuslerBot2  # type: ignore[import]

    bot = HuslerBot2()
    bot.run_campaign(payload)


if __name__ == "__main__":
    orchestrator = Agent001()

    # Register sub-agents
    orchestrator.register_agent("Agent_002", _example_agent_002_handler)
    orchestrator.register_agent("Husler_bot2", _example_husler_handler)

    # Install known dependencies
    for dep in ["requests", "jinja2"]:
        orchestrator.install_dependency(dep)

    # Queue sample tasks (remove or replace with real tasks)
    orchestrator.submit_task(
        "Agent_002",
        "Start web server",
        {"action": "serve", "host": "0.0.0.0", "port": 8080},
    )
    orchestrator.submit_task(
        "Husler_bot2",
        "Run ad campaign",
        {"campaign_id": "camp-001", "product": "example_product"},
    )

    orchestrator.start()
