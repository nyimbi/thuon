# long_running_processes/reactor_control.py

"""
Reactor Control Module for Thuon Platform Long-Running Processes

This module provides the ReactorControl class to manage and monitor
long-running processes within the Thuon Platform. It's designed to
handle tasks that might require extended execution time, such as
complex AI analyses, data processing, or background operations.

Currently, it provides basic process management capabilities, including
starting, monitoring, and stopping external processes (e.g., via
subprocess calls to thuon.sh). Future enhancements could include
process queue management, resource allocation, and more sophisticated
monitoring and error handling.
"""

import subprocess
import time
import logging
import signal
import os
import threading
from typing import List, Dict, Optional

# Configure logging for this module
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__)


class ProcessReactor:
    """
    Manages and monitors long-running processes within the Thuon Platform.

    This class provides methods to start, stop, and monitor external processes,
    typically Thuon Platform capability modules executed via subprocess calls.

    Attributes:
        process_list (List[subprocess.Popen]): A list to keep track of running subprocesses.
        process_status (Dict[int, str]): A dictionary to store the status of each process,
                                        keyed by process PID (Process ID). Status can be 'running',
                                        'completed', 'error', 'stopped', 'unknown'.
        process_metadata (Dict[int, dict]):  Stores metadata for each process, like capability module,
                                            command, start time, etc. Keyed by process PID.
        polling_interval (float): Time interval (in seconds) for monitoring process status.
        running (bool): Flag to control the main reactor loop.
    """

    def __init__(self, polling_interval: float = 5.0):
        """
        Initializes the ProcessReactor.

        Args:
            polling_interval (float): The time interval (in seconds) to check process status.
                                      Defaults to 5.0 seconds.
        """
        self.process_list: List[subprocess.Popen] = []
        self.process_status: Dict[int, str] = {}
        self.process_metadata: Dict[int, dict] = {}
        self.polling_interval: float = polling_interval
        self.running: bool = False
        self._process_lock = threading.Lock()  # Lock for thread-safe process list operations

    def start_process(self, capability_module: str, command: str, options: Optional[List[str]] = None, metadata: Optional[dict] = None) -> Optional[int]:
        """
        Starts a new long-running process by calling the thuon.sh script.

        Args:
            capability_module (str): The name of the capability module to execute.
            command (str): The command to run within the capability module.
            options (Optional[List[str]]): A list of command-line options for the thuon.sh script.
                                           Defaults to None (no options).
            metadata (Optional[dict]):  Optional metadata to associate with the process.
                                        This can be used to store information about the task, user, etc.

        Returns:
            Optional[int]: The Process ID (PID) of the newly started process if successful,
                           or None if process start fails.
        """
        command_list = ["bash", "./thuon.sh", capability_module, command]
        if options:
            command_list.extend(options)

        try:
            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,  # Capture standard output (can be modified as needed)
                stderr=subprocess.PIPE,  # Capture standard error (can be modified as needed)
                cwd="."  # Assuming thuon.sh is in the project root, adjust if necessary
                # Add env=os.environ.copy() if you need to pass environment variables
            )
            with self._process_lock:
                self.process_list.append(process)
                self.process_status[process.pid] = 'running'
                process_meta = {
                    'capability_module': capability_module,
                    'command': command,
                    'options': options if options else [],
                    'start_time': time.time()
                }
                if metadata:
                    process_meta.update(metadata) # Merge user-provided metadata
                self.process_metadata[process.pid] = process_meta
            logger.info(f"Process started: PID={process.pid}, Command='{' '.join(command_list)}'")
            return process.pid
        except Exception as e:
            logger.error(f"Error starting process for command: {' '.join(command_list)} - {e}")
            return None

    def monitor_processes(self) -> None:
        """
        Monitors the status of all running processes and updates process_status.

        This method iterates through the list of running processes and checks their
        current status using process.poll(). It updates the process_status dictionary
        accordingly ('completed', 'running', 'error', 'unknown').
        """
        processes_to_remove = []
        with self._process_lock:
            for process in self.process_list:
                pid = process.pid
                if pid not in self.process_status:  # Process not tracked, should not happen normally
                    logger.warning(f"Untracked process found, PID={pid}. Adding to monitoring.")
                    self.process_status[pid] = 'unknown'
                    self.process_metadata[pid] = {'status': 'unknown', 'message': 'Untracked process found'}

                return_code = process.poll() # Check if process has finished

                if return_code is None:
                    # Process is still running
                    if self.process_status[pid] != 'running':
                        self.process_status[pid] = 'running' # Ensure status is correct
                    continue # Move to next process

                # Process has exited (return_code is not None)
                if return_code == 0:
                    status = 'completed'
                    logger.info(f"Process completed successfully: PID={pid}, Command='{self.process_metadata[pid].get('command', 'unknown command')}'")
                else:
                    status = 'error'
                    stderr_output = process.stderr.read().decode() if process.stderr else "No stderr output" # Read error output
                    logger.error(f"Process exited with error: PID={pid}, Return Code={return_code}, Command='{self.process_metadata[pid].get('command', 'unknown command')}', Error Output: {stderr_output}")

                self.process_status[pid] = status
                processes_to_remove.append(process) # Mark for removal after loop

            # Remove completed/errored processes from process_list
            for process in processes_to_remove:
                self.process_list.remove(process)

    def stop_process(self, pid: int) -> bool:
        """
        Stops a running process based on its Process ID (PID).

        Args:
            pid (int): The Process ID of the process to stop.

        Returns:
            bool: True if the process was successfully stopped, False otherwise.
        """
        with self._process_lock:
            process_to_stop = None
            for proc in self.process_list:
                if proc.pid == pid:
                    process_to_stop = proc
                    break

            if process_to_stop:
                try:
                    process_to_stop.terminate()  # Send SIGTERM signal
                    time.sleep(1) # Give process a moment to terminate gracefully
                    if process_to_stop.poll() is None: # Still running? Forcefully kill
                        process_to_stop.kill() # Send SIGKILL signal
                    self.process_status[pid] = 'stopped'
                    self.process_list.remove(process_to_stop)
                    logger.info(f"Process stopped: PID={pid}")
                    return True
                except Exception as e:
                    logger.error(f"Error stopping process PID={pid}: {e}")
                    return False
            else:
                logger.warning(f"Process with PID={pid} not found in running process list.")
                return False

    def get_process_status(self, pid: Optional[int] = None) -> Dict[int, str]:
        """
        Retrieves the status of a specific process or all running processes.

        Args:
            pid (Optional[int]): The Process ID to query. If None, returns status of all processes.
                                 Defaults to None.

        Returns:
            Dict[int, str]: A dictionary mapping Process IDs to their status ('running', 'completed', 'error', 'stopped', 'unknown').
                             If pid is specified and not found, returns an empty dictionary. If pid is None, returns status of all tracked processes.
        """
        status_to_return = {}
        with self._process_lock:
            if pid is not None:
                if pid in self.process_status:
                    status_to_return[pid] = self.process_status[pid]
            else:
                status_to_return = self.process_status.copy() # Return a copy to avoid external modification
        return status_to_return

    def run(self) -> None:
        """
        Main reactor loop to continuously monitor and manage processes.

        This loop runs as long as self.running is True. It periodically calls
        monitor_processes to update process statuses and handles any reactor-level
        operations (currently just monitoring).
        """
        self.running = True
        logger.info("Process Reactor started.")
        try:
            while self.running:
                self.monitor_processes()
                time.sleep(self.polling_interval)
        except KeyboardInterrupt:
            logger.info("Process Reactor received KeyboardInterrupt. Shutting down...")
        except Exception as e:
            logger.critical(f"Process Reactor encountered a critical error: {e}")
        finally:
            self.running = False
            self.stop_all_processes() # Ensure all processes are stopped on reactor exit
            logger.info("Process Reactor stopped.")

    def stop_all_processes(self) -> None:
        """
        Stops all currently running processes managed by the reactor.
        """
        logger.info("Stopping all running processes...")
        with self._process_lock:
            for process in list(self.process_list): # Iterate over a copy to allow removal
                self.stop_process(process.pid)
        logger.info("All processes stopped.")


def signal_handler(sig, frame):
    """
    Signal handler for graceful shutdown on SIGINT and SIGTERM.
    """
    logger.info(f"Signal {sig} received. Initiating graceful shutdown...")
    global reactor
    if reactor:
        reactor.running = False # Signal reactor loop to stop
    # Reactor loop will call stop_all_processes in its finally block


if __name__ == "__main__":
    # Example usage and command-line interface (basic example)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # `kill <pid>`

    reactor = ProcessReactor(polling_interval=2.0) # Initialize reactor

    logger.info("Reactor Control script started. Use Ctrl+C to stop.")

    # Example: Start a few long-running processes (for testing)
    process_ids = []
    process_ids.append(reactor.start_process("research_assistant", "conduct_research", ["--topic", "Long-running process test 1", "--output", "process1_output.txt"], metadata={'task_id': 'task1'}))
    process_ids.append(reactor.start_process("ai_report_writer", "generate_report", ["--template", "basic_report", "--data_source", "dummy_data", "--output", "process2_output.txt"], metadata={'task_id': 'task2'}))
    process_ids.append(reactor.start_process("ethical_ai_governance_engine", "assess_prompt_ethics", ["--prompt", "Example prompt for ethical assessment", "--output", "process3_output.txt"], metadata={'task_id': 'task3'}))

    if any(pid is None for pid in process_ids):
        logger.error("One or more processes failed to start.")
    else:
        logger.info(f"Started processes with PIDs: {process_ids}")

    reactor.run() # Start the main reactor loop

    logger.info("Reactor Control script finished.")
