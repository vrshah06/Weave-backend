const mongoose = require("mongoose");
const Appointment = require("../models/Appointment");
const Patient = require("../models/Patient");
const { getMemoryStore } = require("./importController");

exports.getAppointments = async (req, res) => {
  try {
    const workspaceId = req.workspaceId;
    const isDbConnected = mongoose.connection.readyState === 1;
    let targetDate = req.query.date;

    if (isDbConnected) {
      if (!targetDate) {
        // Find latest date in DB if no date passed
        const latestAppt = await Appointment.findOne({ workspaceId }).sort({ appointmentDate: -1 });
        targetDate = latestAppt ? latestAppt.appointmentDate : new Date().toISOString().split("T")[0];
      }

      const appointments = await Appointment.find({ workspaceId, appointmentDate: targetDate })
        .populate("patientId", "firstName lastName fullName phone")
        .sort({ appointmentTime: 1 });

      const formatted = appointments.map((a) => ({
        id: a._id,
        patientName: a.patientId ? a.patientId.fullName : "Unknown Patient",
        phone: a.patientId ? a.patientId.phone : "",
        maskedPhone: a.patientId ? maskPhone(a.patientId.phone) : "",
        appointmentDate: a.appointmentDate,
        appointmentTime: a.appointmentTime,
        provider: a.provider || "General Practice",
        reminderSelected: a.reminderSelected,
        reminderStatus: a.reminderStatus
      }));

      // Chronological ascending sort by appointment time
      formatted.sort((a, b) => parseTimeToMinutes(a.appointmentTime) - parseTimeToMinutes(b.appointmentTime));

      return res.json({ date: targetDate, appointments: formatted });
    } else {
      // Memory Store Fallback
      const memStore = getMemoryStore();
      let appts = memStore.appointments.filter(a => a.workspaceId.toString() === workspaceId.toString());
      if (!targetDate && appts.length > 0) {
        targetDate = appts[0].appointmentDate;
      }
      if (targetDate) {
        appts = appts.filter(a => a.appointmentDate === targetDate);
      }
      const formatted = appts.map(a => ({
        id: a._id,
        patientName: a.patientName,
        phone: a.phone,
        maskedPhone: maskPhone(a.phone),
        appointmentDate: a.appointmentDate,
        appointmentTime: a.appointmentTime,
        provider: a.provider || "General Practice",
        reminderSelected: a.reminderSelected,
        reminderStatus: a.reminderStatus
      }));

      // Chronological ascending sort by appointment time
      formatted.sort((a, b) => parseTimeToMinutes(a.appointmentTime) - parseTimeToMinutes(b.appointmentTime));

      return res.json({ date: targetDate || new Date().toISOString().split("T")[0], appointments: formatted });
    }
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

function parseTimeToMinutes(timeStr) {
  if (!timeStr || typeof timeStr !== "string") return 0;
  const cleaned = timeStr.trim();
  const match = cleaned.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
  if (!match) return 0;
  let hours = parseInt(match[1], 10);
  const minutes = parseInt(match[2], 10);
  const period = match[3] ? match[3].toUpperCase() : null;

  if (period === "PM" && hours < 12) hours += 12;
  if (period === "AM" && hours === 12) hours = 0;

  return hours * 60 + minutes;
}


exports.toggleSelection = async (req, res) => {
  try {
    const workspaceId = req.workspaceId;
    const { appointmentIds, selected } = req.body;

    if (!Array.isArray(appointmentIds)) {
      return res.status(400).json({ error: "appointmentIds must be an array" });
    }

    if (mongoose.connection.readyState === 1) {
      await Appointment.updateMany(
        { workspaceId, _id: { $in: appointmentIds } },
        { $set: { reminderSelected: Boolean(selected), updatedAt: new Date() } }
      );
    } else {
      const memStore = getMemoryStore();
      memStore.appointments.forEach((a) => {
        if (appointmentIds.includes(a._id)) {
          a.reminderSelected = Boolean(selected);
        }
      });
    }

    return res.json({ message: "Appointment selection updated", count: appointmentIds.length, selected });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

exports.getAvailableDates = async (req, res) => {
  try {
    const workspaceId = req.workspaceId;
    if (mongoose.connection.readyState === 1) {
      const dates = await Appointment.distinct("appointmentDate", { workspaceId });
      return res.json({ dates: dates.sort().reverse() });
    } else {
      const memStore = getMemoryStore();
      const dates = [...new Set(memStore.appointments.map(a => a.appointmentDate))];
      return res.json({ dates: dates.sort().reverse() });
    }
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

function maskPhone(phone) {
  if (!phone) return "";
  const digits = phone.replace(/\D/g, "");
  if (digits.length >= 4) {
    return "***" + digits.slice(-4);
  }
  return phone;
}
