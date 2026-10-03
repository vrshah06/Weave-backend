const mongoose = require("mongoose");

const PatientSchema = new mongoose.Schema({
  workspaceId: { type: mongoose.Schema.Types.ObjectId, ref: "Workspace", required: true, index: true },
  firstName: { type: String, required: true },
  lastName: { type: String, required: true },
  fullName: { type: String, required: true, index: true },
  phone: { type: String, required: true, index: true },
  createdAt: { type: Date, default: Date.now }
});

PatientSchema.index({ workspaceId: 1, phone: 1 });
PatientSchema.index({ workspaceId: 1, fullName: 1 });

module.exports = mongoose.model("Patient", PatientSchema);
