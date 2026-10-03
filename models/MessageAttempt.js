const mongoose = require("mongoose");

const MessageAttemptSchema = new mongoose.Schema({
  workspaceId: { type: mongoose.Schema.Types.ObjectId, ref: "Workspace", required: true, index: true },
  patientId: { type: mongoose.Schema.Types.ObjectId, ref: "Patient", required: true, index: true },
  appointmentId: { type: mongoose.Schema.Types.ObjectId, ref: "Appointment", required: true, index: true },
  automationRunId: { type: mongoose.Schema.Types.ObjectId, ref: "AutomationRun", required: true, index: true },
  attemptNumber: { type: Number, required: true, default: 1 },
  message: { type: String, required: true },
  status: {
    type: String,
    enum: ['PENDING', 'SENDING', 'SENT', 'CONFIRMED', 'NOT_CONFIRMED', 'FAILED'],
    default: 'PENDING',
    index: true
  },
  failureReason: { type: String, default: "" },
  sentAt: { type: Date },
  confirmedAt: { type: Date },
  failedAt: { type: Date },
  createdAt: { type: Date, default: Date.now }
});

MessageAttemptSchema.index({ workspaceId: 1, appointmentId: 1, attemptNumber: 1 });

module.exports = mongoose.model("MessageAttempt", MessageAttemptSchema);
