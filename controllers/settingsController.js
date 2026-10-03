const mongoose = require("mongoose");
const Workspace = require("../models/Workspace");

const memorySettings = {
  name: "Default Medical Clinic",
  slug: "default-clinic",
  messageTemplate: "Hi {{patient_name}}, this is a reminder for your appointment on {{appointment_date}} at {{appointment_time}}.",
  timeZone: "America/New_York"
};

exports.getSettings = async (req, res) => {
  try {
    const workspaceId = req.workspaceId;
    if (mongoose.connection.readyState === 1) {
      let ws = await Workspace.findById(workspaceId);
      if (!ws) {
        ws = await Workspace.create(memorySettings);
      }
      return res.json(ws);
    } else {
      return res.json(memorySettings);
    }
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

exports.updateSettings = async (req, res) => {
  try {
    const workspaceId = req.workspaceId;
    const { name, messageTemplate, timeZone } = req.body;

    if (mongoose.connection.readyState === 1) {
      const updated = await Workspace.findByIdAndUpdate(
        workspaceId,
        { $set: { name, messageTemplate, timeZone } },
        { new: true }
      );
      return res.json(updated);
    } else {
      if (name) memorySettings.name = name;
      if (messageTemplate) memorySettings.messageTemplate = messageTemplate;
      if (timeZone) memorySettings.timeZone = timeZone;
      return res.json(memorySettings);
    }
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
