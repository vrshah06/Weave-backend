const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const mongoose = require("mongoose");
const AutomationRun = require("../models/AutomationRun");
const Appointment = require("../models/Appointment");
const Patient = require("../models/Patient");
const MessageAttempt = require("../models/MessageAttempt");
const { exportDatabaseToPayload } = require("../utils/dbAdapter");
const { emitWorkspaceEvent } = require("../services/socketService");
const automationState = require("../services/automationState");

class AutomationWorker {
  constructor() {
    this.activeProcess = null;
    this.currentRunId = null;
  }

  isRunning() {
    return this.activeProcess !== null;
  }

  async executeRun({ workspaceId, appointmentDate, mode = "dry_run", targetIds = null }) {
    if (this.activeProcess) {
      throw new Error("An automation run is already in progress.");
    }

    const isDbConnected = mongoose.connection.readyState === 1;
    const isSendMode = mode === "send";

    // 1. Export MongoDB records to worker payload
    const { csvPath, count, items } = await exportDatabaseToPayload(workspaceId, appointmentDate, targetIds);

    if (count === 0) {
      throw new Error("No selected appointments found for the specified date.");
    }

    // 2. Create AutomationRun record in MongoDB
    let runRecord = null;
    if (isDbConnected) {
      runRecord = await AutomationRun.create({
        workspaceId,
        appointmentDate: appointmentDate || new Date().toISOString().split("T")[0],
        mode,
        status: "STARTING",
        totalSelected: count
      });
      this.currentRunId = runRecord._id.toString();
    } else {
      this.currentRunId = "run_" + Date.now();
    }

    // Reset local in-memory state
    automationState.resetForRun();
    automationState.updateState({
      status: "starting",
      mode,
      total: count,
      remaining: count,
      startedAt: new Date().toISOString()
    });

    emitWorkspaceEvent(workspaceId, "automation:started", {
      runId: this.currentRunId,
      mode,
      total: count,
      date: appointmentDate
    });

    const rootDir = path.resolve(__dirname, "../");
    const modeFlag = isSendMode ? "--send" : "--dry-run";
    const args = ["main.py", modeFlag, "--file", csvPath];

    try {
      this.activeProcess = spawn("python", args, {
        cwd: rootDir,
        env: { ...process.env, PYTHONUNBUFFERED: "1" }
      });
    } catch (err) {
      this.activeProcess = null;
      if (runRecord) {
        await AutomationRun.findByIdAndUpdate(runRecord._id, { status: "FAILED" });
      }
      throw err;
    }

    const processRef = this.activeProcess;
    const runId = this.currentRunId;

    this.runStats = {
      processed: 0,
      sent: 0,
      confirmed: 0,
      failed: 0,
      skipped: 0
    };

    processRef.stdout.on("data", (chunk) => {
      this._handleChunk(chunk.toString(), workspaceId, runId, items);
    });

    processRef.stderr.on("data", (chunk) => {
      this._handleChunk(chunk.toString(), workspaceId, runId, items);
    });

    processRef.on("close", async (code) => {
      if (this.activeProcess === processRef) {
        this.activeProcess = null;
      }

      // Cleanup temp CSV
      try {
        if (fs.existsSync(csvPath)) fs.unlinkSync(csvPath);
      } catch (e) {
        // Ignored
      }

      // Check if any items remained in processing without final event
      if (items && Array.isArray(items)) {
        for (const item of items) {
          if (isDbConnected) {
            try {
              const appt = await Appointment.findById(item.appointmentId);
              if (appt && (appt.reminderStatus === "PENDING" || appt.reminderStatus === "SENDING" || appt.reminderStatus === "SELECTED")) {
                await Appointment.findByIdAndUpdate(item.appointmentId, {
                  reminderStatus: "SKIPPED",
                  updatedAt: new Date()
                });
                this.runStats.processed += 1;
                this.runStats.skipped += 1;
              }
            } catch (e) {
              // Ignored
            }
          }
        }
      }

      const finalStatus = code === 0 ? "COMPLETED" : "FAILED";

      // 3. Trigger Confirmation State Sync
      emitWorkspaceEvent(workspaceId, "automation:confirming", { runId });

      if (isDbConnected && runRecord) {
        await AutomationRun.findByIdAndUpdate(runRecord._id, {
          status: finalStatus,
          completedAt: new Date(),
          totalProcessed: this.runStats.processed,
          totalSent: this.runStats.sent,
          totalConfirmed: this.runStats.confirmed,
          totalFailed: this.runStats.failed,
          totalSkipped: this.runStats.skipped
        });
      }

      automationState.updateState({
        status: finalStatus.toLowerCase(),
        completedAt: new Date().toISOString(),
        currentPatient: null
      });

      automationState.addLog({
        patient: "System",
        action: "Run Finished",
        status: finalStatus === "COMPLETED" ? "success" : "failed",
        message: `Automation run finished with code ${code} (${finalStatus}). Processed: ${this.runStats.processed}/${count}`
      });

      emitWorkspaceEvent(workspaceId, `automation:${finalStatus.toLowerCase()}`, {
        runId,
        code
      });
    });

    return { runId, count, mode };
  }

  stopRun(workspaceId) {
    if (!this.activeProcess) return false;
    try {
      const pid = this.activeProcess.pid;
      if (process.platform === "win32") {
        execSync(`taskkill /pid ${pid} /T /F`);
      } else {
        this.activeProcess.kill("SIGKILL");
      }
    } catch (e) {
      // Ignored
    }
    this.activeProcess = null;
    automationState.updateState({ status: "stopped", currentPatient: null });
    automationState.addLog({
      patient: "System",
      action: "Stop Command",
      status: "warning",
      message: "Automation process manually stopped by user"
    });
    emitWorkspaceEvent(workspaceId, "automation:stopped", { runId: this.currentRunId });
    return true;
  }

  _handleChunk(text, workspaceId, runId, items) {
    const lines = text.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      if (trimmed.includes("[EVENT]")) {
        const jsonStr = trimmed.substring(trimmed.indexOf("[EVENT]") + 7).trim();
        try {
          const event = JSON.parse(jsonStr);
          this._processEvent(event, workspaceId, runId, items);
        } catch (e) {
          // Fallback log
        }
      }
    }
  }

  async _processEvent(event, workspaceId, runId, items) {
    const isDbConnected = mongoose.connection.readyState === 1;

    switch (event.type) {
      case "PATIENT_START":
        automationState.updateState({
          status: "running",
          currentPatient: { name: event.patient_name, phone: event.phone }
        });
        automationState.addLog({
          patient: event.patient_name,
          action: "Processing Patient",
          status: "running",
          message: `Navigating to patient chat (${event.phone})`
        });

        emitWorkspaceEvent(workspaceId, "automation:patient", {
          runId,
          patientName: event.patient_name,
          phone: event.phone,
          position: event.position
        });
        break;

      case "MESSAGE_SENT":
      case "MESSAGE_DRY_RUN":
        {
          const matched = items.find(i => i.phone === event.phone || i.patient_name === event.patient_name);
          const isSent = event.type === "MESSAGE_SENT";

          this.runStats.processed += 1;
          if (isSent) {
            this.runStats.sent += 1;
          } else {
            this.runStats.confirmed += 1;
          }

          automationState.updateState({
            processed: this.runStats.processed,
            sent: this.runStats.sent + this.runStats.confirmed,
            remaining: Math.max(0, automationState.getState().total - this.runStats.processed)
          });

          automationState.addLog({
            patient: event.patient_name,
            action: isSent ? "Message Sent" : "Dry Run Verified",
            status: isSent ? "sent" : "dry_run",
            message: isSent
              ? `Successfully dispatched appointment reminder SMS to ${event.phone}`
              : `Dry Run: Verified chat window and reminder text for ${event.patient_name}`
          });

          if (isDbConnected && matched) {
            try {
              // Update Appointment status to SENT / CONFIRMED
              await Appointment.findByIdAndUpdate(matched.appointmentId, {
                reminderStatus: isSent ? "SENT" : "CONFIRMED",
                updatedAt: new Date()
              });

              // Create MessageAttempt record
              const attemptCount = await MessageAttempt.countDocuments({
                workspaceId,
                appointmentId: matched.appointmentId
              });

              await MessageAttempt.create({
                workspaceId,
                patientId: matched.patientId,
                appointmentId: matched.appointmentId,
                automationRunId: runId,
                attemptNumber: attemptCount + 1,
                message: `Appointment reminder for ${matched.appointment_date} at ${matched.appointment_time}`,
                status: isSent ? "SENT" : "CONFIRMED",
                sentAt: new Date(),
                confirmedAt: isSent ? null : new Date()
              });
            } catch (e) {
              console.warn("Error updating DB on message sent:", e.message);
            }
          }

          emitWorkspaceEvent(workspaceId, "automation:sent", {
            runId,
            patientName: event.patient_name,
            phone: event.phone,
            isDryRun: !isSent
          });
        }
        break;

      case "PATIENT_FAILED":
        {
          const matched = items.find(i => i.phone === event.phone || i.patient_name === event.patient_name);

          this.runStats.processed += 1;
          this.runStats.failed += 1;

          automationState.updateState({
            processed: this.runStats.processed,
            failed: this.runStats.failed,
            remaining: Math.max(0, automationState.getState().total - this.runStats.processed)
          });

          automationState.addLog({
            patient: event.patient_name || "Unknown",
            action: "Message Failed / Not Delivered",
            status: "failed",
            message: event.reason || "Message not delivered or failed"
          });

          if (isDbConnected && matched) {
            try {
              await Appointment.findByIdAndUpdate(matched.appointmentId, {
                reminderStatus: "FAILED",
                updatedAt: new Date()
              });

              const attemptCount = await MessageAttempt.countDocuments({
                workspaceId,
                appointmentId: matched.appointmentId
              });

              await MessageAttempt.create({
                workspaceId,
                patientId: matched.patientId,
                appointmentId: matched.appointmentId,
                automationRunId: runId,
                attemptNumber: attemptCount + 1,
                message: `Appointment reminder attempt`,
                status: "FAILED",
                failureReason: event.reason || "Not Delivered",
                failedAt: new Date()
              });
            } catch (e) {
              // Ignored
            }
          }

          emitWorkspaceEvent(workspaceId, "automation:failed", {
            runId,
            patientName: event.patient_name,
            reason: event.reason
          });
        }
        break;

      case "PATIENT_SKIPPED":
        {
          const matched = items.find(i => i.phone === event.phone || i.patient_name === event.patient_name);
          this.runStats.processed += 1;
          this.runStats.skipped += 1;

          automationState.updateState({
            processed: this.runStats.processed,
            skipped: this.runStats.skipped,
            remaining: Math.max(0, automationState.getState().total - this.runStats.processed)
          });

          automationState.addLog({
            patient: event.patient_name || "Unknown",
            action: "Patient Skipped",
            status: "skipped",
            message: event.reason || "Skipped (incomplete processing or recipient not found)"
          });

          if (isDbConnected && matched) {
            try {
              await Appointment.findByIdAndUpdate(matched.appointmentId, {
                reminderStatus: "SKIPPED",
                updatedAt: new Date()
              });
            } catch (e) {
              // Ignored
            }
          }

          emitWorkspaceEvent(workspaceId, "automation:skipped", {
            runId,
            patientName: event.patient_name,
            reason: event.reason
          });
        }
        break;

      default:
        break;
    }
  }

  async _runAutomaticConfirmation(workspaceId, runId, isSendMode) {
    // Keep message statuses intact without force-confirming failed messages
    return;
  }

}

module.exports = new AutomationWorker();
