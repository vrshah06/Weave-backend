const mongoose = require("mongoose");
const dns = require("dns");

const connectDB = async () => {
  try {
    dns.setServers(["8.8.8.8", "1.1.1.1"]);
  } catch (e) {
    // Ignore if custom DNS cannot be set
  }

  const mongoURI = process.env.MONGODB_URI || "mongodb://127.0.0.1:27017/weave_automation";
  try {
    const conn = await mongoose.connect(mongoURI, {
      serverSelectionTimeoutMS: 10000,
    });
    console.log(`[MongoDB] Connected: ${conn.connection.host}`);
    return conn;
  } catch (err) {
    console.warn(`[MongoDB] Connection Warning: ${err.message}. Operating in memory fallback mode.`);
    return null;
  }
};

module.exports = connectDB;
