const express = require("express");
const multer = require("multer");
const path = require("path");
const fs = require("fs");
const importController = require("../controllers/importController");

const router = express.Router();
const uploadDir = path.resolve(__dirname, "../../data/uploads");
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}

const upload = multer({ dest: uploadDir });

router.post("/csv", upload.single("file"), importController.importCsv);

module.exports = router;
