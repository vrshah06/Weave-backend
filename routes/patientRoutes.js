const express = require("express");
const patientController = require("../controllers/patientController");

const router = express.Router();

router.get("/", patientController.getPatients);
router.get("/:id/history", patientController.getPatientHistory);

module.exports = router;
