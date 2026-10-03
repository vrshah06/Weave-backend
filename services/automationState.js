class AutomationState {
  constructor() {
    this.reset();
    this.sseClients = new Set();
  }

  reset() {
    this.state = {
      status: "idle", // idle, starting, logging_in, running, stopping, completed, failed, stopped
      mode: "dry_run", // dry_run or send
      total: 0,
      processed: 0,
      sent: 0,
      failed: 0,
      skipped: 0,
      remaining: 0,
      currentPatient: null,
      startedAt: null,
      completedAt: null,
      error: null,
      csvFile: "appointments.csv",
      logs: []
    };
  }

  resetForRun() {
    const currentCsvFile = this.state?.csvFile || "appointments.csv";
    const currentTotal = this.state?.total || 0;
    this.state = {
      status: "idle",
      mode: "dry_run",
      total: currentTotal,
      processed: 0,
      sent: 0,
      failed: 0,
      skipped: 0,
      remaining: currentTotal,
      currentPatient: null,
      startedAt: null,
      completedAt: null,
      error: null,
      csvFile: currentCsvFile,
      logs: []
    };
    this.broadcast({ type: "state_update", state: this.state });
  }

  getState() {
    return { ...this.state };
  }

  updateState(partial) {
    this.state = { ...this.state, ...partial };
    if (this.state.total > 0) {
      this.state.remaining = Math.max(0, this.state.total - this.state.processed);
    }
    this.broadcast({ type: "state_update", state: this.state });
  }

  addLog(entry) {
    const logItem = {
      id: Date.now() + Math.random().toString(36).substring(2, 6),
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      ...entry
    };
    this.state.logs.push(logItem);
    if (this.state.logs.length > 500) {
      this.state.logs.shift();
    }
    this.broadcast({ type: "log", log: logItem });
  }

  addSseClient(res) {
    this.sseClients.add(res);
    // Immediately send current state on connect
    res.write(`data: ${JSON.stringify({ type: "init", state: this.state })}\n\n`);
  }

  removeSseClient(res) {
    this.sseClients.delete(res);
  }

  broadcast(data) {
    const payload = `data: ${JSON.stringify(data)}\n\n`;
    for (const client of this.sseClients) {
      client.write(payload);
    }
  }
}

module.exports = new AutomationState();
