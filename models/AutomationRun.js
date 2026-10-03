const mongoose = require("mongoose");

const AutomationRunSchema = new mongoose.Schema({
  workspaceId: { type: mongoose.Schema.Types.ObjectId, ref: "Workspace", required: true, index: true },
  appointmentDate: { type: String, required: true },
  mode: { type: String, enum: ['dry_run', 'send'], default: 'dry_run' },
  status: {
    type: String,
    enum: ['QUEUED', 'STARTING', 'LOGGING_IN', 'RUNNING', 'CONFIRMING', 'COMPLETED', 'FAILED', 'STOPPED'],
    default: 'QUEUED',
    index: true
  },
  startedAt: { type: Date, default: Date.now },
  completedAt: { type: Date },
  totalSelected: { type: Number, default: 0 },
  totalProcessed: { type: Number, default: 0 },
  totalSent: { type: Number, default: 0 },
  totalConfirmed: { type: Number, default: 0 },
  totalFailed: { type: Number, default: 0 },
  totalSkipped: { type: Number, default: 0 },
  totalNotConfirmed: { type: Number, default: 0 }
});

module.exports = mongoose.model("AutomationRun", AutomationRunSchema);
