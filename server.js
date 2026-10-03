const http = require("http");
const express = require("express");
const cors = require("cors");
const path = require("path");
const fs = require("fs");
const connectDB = require("./config/db");
const { workspaceContext } = require("./middleware/workspaceContext");
const { initSocket } = require("./services/socketService");

// Route imports
const importRoutes = require("./routes/importRoutes");
const appointmentRoutes = require("./routes/appointmentRoutes");
const automationRoutes = require("./routes/automationRoutes");
const patientRoutes = require("./routes/patientRoutes");
const settingsRoutes = require("./routes/settingsRoutes");

const app = express();
const server = http.createServer(app);
const PORT = process.env.PORT || 5000;

// Initialize Socket.IO
initSocket(server);

// Middleware
app.use(cors());
app.use(express.json());
app.use(workspaceContext);

// Connect to MongoDB
connectDB();

// API Routes
app.use("/api/import", importRoutes);
app.use("/api/appointments", appointmentRoutes);
app.use("/api/automation", automationRoutes);
app.use("/api/patients", patientRoutes);
app.use("/api/settings", settingsRoutes);

// Health check endpoint
app.get("/api/health", (req, res) => {
  res.json({ status: "healthy", timestamp: new Date().toISOString() });
});

// Serve frontend build static files in production / network mode
const frontendDistPath = path.resolve(__dirname, "../frontend/dist");
if (fs.existsSync(frontendDistPath)) {
  app.use(express.static(frontendDistPath));
  app.get("*", (req, res) => {
    if (!req.path.startsWith("/api")) {
      res.sendFile(path.join(frontendDistPath, "index.html"));
    }
  });
}

const HOST = process.env.HOST || "0.0.0.0";

server.listen(PORT, HOST, () => {
  console.log(`==================================================`);
  console.log(`WEAVE AUTOMATION BACKEND & FRONTEND SERVER RUNNING`);
  console.log(`Local Access:   http://localhost:${PORT}`);
  console.log(`Network Access: http://0.0.0.0:${PORT}`);
  console.log(`==================================================`);
});
