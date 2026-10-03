const mongoose = require("mongoose");
const Patient = require("../models/Patient");
const MessageAttempt = require("../models/MessageAttempt");
const Appointment = require("../models/Appointment");
const { getMemoryStore } = require("./importController");

exports.getPatients = async (req, res) => {
  try {
    const workspaceId = req.workspaceId;
    if (mongoose.connection.readyState === 1) {
      const patients = await Patient.find({ workspaceId }).sort({ lastName: 1, firstName: 1 });
      return res.json(patients);
    } else {
      const memStore = getMemoryStore();
      const patients = memStore.patients.filter(p => p.workspaceId.toString() === workspaceId.toString());
      return res.json(patients);
    }
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

exports.getPatientHistory = async (req, res) => {
  try {
    const workspaceId = req.workspaceId;
    const patientId = req.params.id;

    if (mongoose.connection.readyState === 1) {
      const attempts = await MessageAttempt.find({ workspaceId, patientId })
        .populate("appointmentId", "appointmentDate appointmentTime provider")
        .sort({ createdAt: -1 });
      return res.json(attempts);
    } else {
      return res.json([]);
    }
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
