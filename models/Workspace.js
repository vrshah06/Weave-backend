const mongoose = require("mongoose");

const WorkspaceSchema = new mongoose.Schema({
  name: { type: String, required: true, default: "Default Medical Clinic" },
  slug: { type: String, required: true, unique: true, default: "default-clinic", index: true },
  messageTemplate: {
    type: String,
    default: "Hi {{patient_name}}, this is a reminder for your appointment on {{appointment_date}} at {{appointment_time}}."
  },
  timeZone: { type: String, default: "America/New_York" },
  createdAt: { type: Date, default: Date.now }
});

module.exports = mongoose.model("Workspace", WorkspaceSchema);
