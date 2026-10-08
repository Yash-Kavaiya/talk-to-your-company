// WebSocket client: reconnects by itself and dispatches messages by their `type` field.

export class Link {
  constructor(onStatus) {
    this.handlers = new Map();
    this.onStatus = onStatus;
    this.socket = null;
    this.connect();
  }

  on(type, handler) {
    this.handlers.set(type, handler);
  }

  connect() {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    this.socket = new WebSocket(`${scheme}://${location.host}/ws`);
    this.socket.onopen = () => this.onStatus(true);
    this.socket.onclose = () => {
      this.onStatus(false);
      setTimeout(() => this.connect(), 1000);
    };
    this.socket.onmessage = (message) => {
      const data = JSON.parse(message.data);
      const handler = this.handlers.get(data.type);
      if (handler) handler(data);
    };
  }

  send(message) {
    if (this.socket.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }
}
