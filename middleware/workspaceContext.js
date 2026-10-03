const mongoose = require("mongoose");
const Workspace = require("../models/Workspace");

let defaultWorkspaceId = null;

const ensureWorkspaceExists = async () => {
  if (defaultWorkspaceId && mongoose.connection.readyState === 1) {
    return defaultWorkspaceId;
  }
  try {
    if (mongoose.connection.readyState === 1) {
      let ws = await Workspace.findOne({ slug: "default-clinic" });
      if (!ws) {
        ws = await Workspace.create({
          name: "Default Medical Clinic",
          slug: "default-clinic",
          messageTemplate: "Hi {{patient_name}}, this is a reminder for your appointment on {{appointment_date}} at {{appointment_time}}."
        });
      }
      defaultWorkspaceId = ws._id;
      return ws._id;
    }
  } catch (err) {
    console.warn("[WorkspaceMiddleware] Database warning, using fallback ID:", err.message);
  }
  return new mongoose.Types.ObjectId("60d5ecb8b3b3b3b3b3b3b3b3");
};

const workspaceContext = async (req, res, next) => {
  try {
    const workspaceId = await ensureWorkspaceExists();
    req.workspaceId = workspaceId;
    req.workspace = {
      _id: workspaceId,
      name: "Default Medical Clinic",
      slug: "default-clinic"
    };
    next();
  } catch (err) {
    return res.status(500).json({ error: "Failed to resolve workspace context." });
  }
};

module.exports = { workspaceContext, ensureWorkspaceExists };
