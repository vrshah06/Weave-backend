const { spawn, execSync } = require("child_process");
const path = require("path");
const automationState = require("./automationState");

class PythonRunner {
  constructor() {
    this.pythonProcess = null;
  }

  isAutomationRunning() {
    return this.pythonProcess !== null;
  }

  startAutomation({ isSendMode = false, csvFilePath = null }) {
    if (this.pythonProcess) {
      throw new Error("Automation process is already running.");
    }

    automationState.resetForRun();

    const rootDir = path.resolve(__dirname, "../../");
    const targetCsv = csvFilePath
      ? path.resolve(csvFilePath)
      : path.join(rootDir, "data", "appointments.csv");

    const modeFlag = isSendMode ? "--send" : "--dry-run";
    const args = ["main.py", modeFlag, "--file", targetCsv];

    automationState.updateState({
      status: "starting",
      mode: isSendMode ? "send" : "dry_run",
      startedAt: new Date().toISOString(),
      csvFile: automationState.getState().csvFile || path.basename(targetCsv),
    });

    automationState.addLog({
      action: "System",
      message: `Starting Python automation in ${isSendMode ? "SEND" : "DRY RUN"} mode using ${path.basename(targetCsv)}...`,
      status: "info"
    });

    try {
      this.pythonProcess = spawn("python", args, {
        cwd: rootDir,
        env: { ...process.env, PYTHONUNBUFFERED: "1" }
      });
    } catch (err) {
      automationState.updateState({ status: "failed", error: err.message });
      automationState.addLog({ action: "Error", message: `Failed to launch Python: ${err.message}`, status: "error" });
      this.pythonProcess = null;
      throw err;
    }

    const processRef = this.pythonProcess;

    processRef.stdout.on("data", (data) => {
      this._handleOutput(data.toString(), "stdout");
    });

    processRef.stderr.on("data", (data) => {
      this._handleOutput(data.toString(), "stderr");
    });

    processRef.on("close", (code) => {
      if (this.pythonProcess === processRef) {
        this.pythonProcess = null;
      }

      const currentState = automationState.getState();
      if (currentState.status === "stopping") {
        automationState.updateState({
          status: "stopped",
          completedAt: new Date().toISOString()
        });
        automationState.addLog({ action: "System", message: "Automation stopped by user.", status: "warning" });
      } else if (code === 0) {
        automationState.updateState({
          status: "completed",
          completedAt: new Date().toISOString(),
          currentPatient: null
        });
        automationState.addLog({ action: "System", message: "Automation completed successfully!", status: "success" });
      } else {
        automationState.updateState({
          status: "failed",
          completedAt: new Date().toISOString(),
          error: `Python process exited with error code ${code}`
        });
        automationState.addLog({ action: "System", message: `Process exited with code ${code}`, status: "error" });
      }
    });

    processRef.on("error", (err) => {
      this.pythonProcess = null;
      automationState.updateState({
        status: "failed",
        error: err.message
      });
      automationState.addLog({ action: "System", message: `Process error: ${err.message}`, status: "error" });
    });

    return { pid: processRef.pid, mode: isSendMode ? "send" : "dry_run" };
  }

  stopAutomation() {
    if (!this.pythonProcess) {
      return false;
    }

    automationState.updateState({ status: "stopping" });
    automationState.addLog({ action: "System", message: "Sending stop signal to Python process...", status: "warning" });

    const pid = this.pythonProcess.pid;
    try {
      if (process.platform === "win32") {
        execSync(`taskkill /pid ${pid} /T /F`);
      } else {
        this.pythonProcess.kill("SIGINT");
      }
    } catch (err) {
      try {
        this.pythonProcess.kill("SIGKILL");
      } catch (e) {
        // Ignored
      }
    }

    this.pythonProcess = null;
    return true;
  }

  _handleOutput(chunk, streamType) {
    const lines = chunk.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      if (trimmed.includes("[EVENT]")) {
        const jsonPart = trimmed.substring(trimmed.indexOf("[EVENT]") + 7).trim();
        try {
          const event = JSON.parse(jsonPart);
          this._processEvent(event);
        } catch (e) {
          // Fallback to text logging
        }
      } else if (streamType === "stderr" && (trimmed.includes("ERROR") || trimmed.includes("Exception"))) {
        automationState.addLog({ action: "Log", message: trimmed, status: "error" });
      }
    }
  }

  _processEvent(event) {
    switch (event.type) {
      case "LOADED_APPOINTMENTS":
        automationState.updateState({ total: event.total, remaining: event.total });
        automationState.addLog({ action: "CSV", message: `Loaded ${event.total} appointment(s)`, status: "info" });
        break;

      case "AUTH_START":
        automationState.updateState({ status: "logging_in" });
        automationState.addLog({ action: "Weave", message: "Checking / authenticating Weave session...", status: "info" });
        break;

      case "AUTH_SUCCESS":
        automationState.updateState({ status: "running" });
        automationState.addLog({ action: "Weave", message: "Session authenticated successfully", status: "success" });
        break;

      case "AUTH_FAILED":
        automationState.updateState({ status: "failed", error: "Weave authentication failed" });
        automationState.addLog({ action: "Weave", message: "Authentication failed", status: "error" });
        break;

      case "PATIENT_START":
        automationState.updateState({
          currentPatient: { name: event.patient_name, phone: event.phone, position: event.position }
        });
        automationState.addLog({
          patient: event.patient_name,
          action: `[${event.position}/${event.total}] Search & Selection`,
          message: `Processing patient ${event.patient_name}`,
          status: "processing"
        });
        break;

      case "PATIENT_SKIPPED":
        automationState.updateState({
          processed: automationState.getState().processed + 1,
          skipped: automationState.getState().skipped + 1
        });
        automationState.addLog({
          patient: event.patient_name,
          action: "Skipped",
          message: event.reason || "Already sent",
          status: "skipped"
        });
        break;

      case "MESSAGE_SENT":
        automationState.updateState({
          processed: automationState.getState().processed + 1,
          sent: automationState.getState().sent + 1
        });
        automationState.addLog({
          patient: event.patient_name,
          action: "Message Sent",
          message: "SMS sent successfully ✓",
          status: "sent"
        });
        break;

      case "MESSAGE_DRY_RUN":
        automationState.updateState({
          processed: automationState.getState().processed + 1,
          sent: automationState.getState().sent + 1
        });
        automationState.addLog({
          patient: event.patient_name,
          action: "Dry Run Verified",
          message: "Reminder composed & verified (Dry Run)",
          status: "dry_run"
        });
        break;

      case "PATIENT_FAILED":
        automationState.updateState({
          processed: automationState.getState().processed + 1,
          failed: automationState.getState().failed + 1
        });
        automationState.addLog({
          patient: event.patient_name,
          action: "Failed",
          message: event.reason || "Verification failed",
          status: "failed"
        });
        break;

      case "RUN_COMPLETE":
        if (event.stats) {
          automationState.updateState({
            sent: event.stats.sent + (event.stats.dry_run || 0),
            skipped: event.stats.already_sent + (event.stats.skipped || 0),
            failed: event.stats.failed
          });
        }
        break;

      default:
        break;
    }
  }
}

module.exports = new PythonRunner();
