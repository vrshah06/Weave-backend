const fs = require("fs");
const path = require("path");
const mongoose = require("mongoose");
const Patient = require("../models/Patient");
const Appointment = require("../models/Appointment");
const { parseAppointmentCsv } = require("../utils/csvParser");

// In-memory store fallback if MongoDB is in offline mode
const memoryStore = {
  patients: [],
  appointments: []
};

exports.importCsv = async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No CSV file uploaded." });
    }

    const content = fs.readFileSync(req.file.path, "utf-8");
    
    // Sync newly uploaded CSV file to data/appointments.csv
    try {
      const dataDir = path.resolve(__dirname, "../data");
      if (!fs.existsSync(dataDir)) {
        fs.mkdirSync(dataDir, { recursive: true });
      }
      fs.writeFileSync(path.join(dataDir, "appointments.csv"), content, "utf-8");
    } catch (e) {
      // Ignored
    }

    // Clean up temp file
    try {
      fs.unlinkSync(req.file.path);
    } catch (e) {
      // Ignored
    }

    const { rows, totalReceived, errors } = parseAppointmentCsv(content);

    let importedCount = 0;
    let duplicateCount = 0;
    let invalidCount = errors.length;

    const workspaceId = req.workspaceId;
    const isDbConnected = mongoose.connection.readyState === 1;

    for (const row of rows) {
      if (isDbConnected) {
        try {
          // 1. Find or create patient
          let patient = await Patient.findOne({ workspaceId, phone: row.phone });
          if (!patient) {
            patient = await Patient.create({
              workspaceId,
              firstName: row.firstName,
              lastName: row.lastName,
              fullName: row.fullName,
              phone: row.phone
            });
          }

          // 2. Create or update appointment
          const appointmentFilter = {
            workspaceId,
            patientId: patient._id,
            appointmentDate: row.appointmentDateIso,
            appointmentTime: row.appointmentTime
          };

          const existingAppointment = await Appointment.findOne(appointmentFilter);
          if (existingAppointment) {
            duplicateCount++;
          } else {
            await Appointment.create({
              ...appointmentFilter,
              provider: row.provider,
              reminderSelected: true,
              reminderStatus: "PENDING"
            });
            importedCount++;
          }
        } catch (err) {
          if (err.code === 11000) {
            duplicateCount++;
          } else {
            invalidCount++;
          }
        }
      } else {
        // Fallback in-memory storage
        let patient = memoryStore.patients.find(p => p.phone === row.phone);
        if (!patient) {
          patient = { _id: Date.now() + Math.random(), workspaceId, fullName: row.fullName, phone: row.phone };
          memoryStore.patients.push(patient);
        }

        const exists = memoryStore.appointments.find(a => 
          a.patientId === patient._id && 
          a.appointmentDate === row.appointmentDateIso && 
          a.appointmentTime === row.appointmentTime
        );

        if (exists) {
          duplicateCount++;
        } else {
          memoryStore.appointments.push({
            _id: Date.now() + Math.random(),
            workspaceId,
            patientId: patient._id,
            patientName: row.fullName,
            phone: row.phone,
            appointmentDate: row.appointmentDateIso,
            appointmentTime: row.appointmentTime,
            provider: row.provider,
            reminderSelected: true,
            reminderStatus: "PENDING"
          });
          importedCount++;
        }
      }
    }

    return res.json({
      message: "CSV import completed successfully",
      summary: {
        rowsReceived: totalReceived,
        imported: importedCount,
        duplicates: duplicateCount,
        invalid: invalidCount
      }
    });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};

exports.getMemoryStore = () => memoryStore;
