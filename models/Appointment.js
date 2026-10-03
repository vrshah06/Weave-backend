const mongoose = require("mongoose");

const AppointmentSchema = new mongoose.Schema({
  workspaceId: { type: mongoose.Schema.Types.ObjectId, ref: "Workspace", required: true, index: true },
  patientId: { type: mongoose.Schema.Types.ObjectId, ref: "Patient", required: true, index: true },
  appointmentDate: { type: String, required: true, index: true }, // Format: YYYY-MM-DD
  appointmentTime: { type: String, required: true },
  provider: { type: String, default: "" },
  reminderSelected: { type: Boolean, default: true },
  reminderStatus: {
    type: String,
    enum: ['PENDING', 'SELECTED', 'SENDING', 'SENT', 'CONFIRMED', 'NOT_CONFIRMED', 'FAILED', 'SKIPPED'],
    default: 'PENDING',
    index: true
  },
  createdAt: { type: Date, default: Date.now },
  updatedAt: { type: Date, default: Date.now }
});

AppointmentSchema.index({ workspaceId: 1, appointmentDate: 1 });
AppointmentSchema.index({ workspaceId: 1, patientId: 1, appointmentDate: 1, appointmentTime: 1 }, { unique: true });

module.exports = mongoose.model("Appointment", AppointmentSchema);
