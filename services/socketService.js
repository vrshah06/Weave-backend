const { Server } = require("socket.io");

let io = null;

const initSocket = (server) => {
  io = new Server(server, {
    cors: {
      origin: "*",
      methods: ["GET", "POST"]
    }
  });

  io.on("connection", (socket) => {
    socket.on("join_workspace", (workspaceId) => {
      const room = `ws_${workspaceId}`;
      socket.join(room);
    });
  });

  return io;
};

const getIO = () => {
  return io;
};

const emitWorkspaceEvent = (workspaceId, eventType, data) => {
  if (!io) return;
  const room = `ws_${workspaceId || "default"}`;
  io.to(room).emit(eventType, { ...data, timestamp: new Date().toISOString() });
  // Also emit globally for standard listener
  io.emit(eventType, { ...data, timestamp: new Date().toISOString() });
};

module.exports = { initSocket, getIO, emitWorkspaceEvent };
