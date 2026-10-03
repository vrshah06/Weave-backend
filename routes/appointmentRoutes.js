const express = require("express");
const appointmentController = require("../controllers/appointmentController");

const router = express.Router();

router.get("/", appointmentController.getAppointments);
router.get("/dates", appointmentController.getAvailableDates);
router.patch("/selection", appointmentController.toggleSelection);

module.exports = router;
