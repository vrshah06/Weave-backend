const express = require("express");
const controller = require("../controllers/automationController");
const automationState = require("../services/automationState");

const router = express.Router();

router.get("/status", controller.getStatus);
router.get("/logs", controller.getLogs);
router.post("/start", controller.startAutomation);
router.post("/stop", controller.stopAutomation);

// History & Retry Routes
router.get("/runs", controller.getRuns);
router.get("/runs/:id", controller.getRunDetails);
router.post("/retry", controller.retryFailedMessages);

// Confirmations Routes for Last Run
router.get("/confirmations/last", controller.getLastRunConfirmations);
router.post("/confirmations/verify", controller.verifyLastRunConfirmations);

// SSE Stream for real-time live events
router.get("/events", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();

  automationState.addSseClient(res);

  req.on("close", () => {
    automationState.removeSseClient(res);
  });
});

module.exports = router;
