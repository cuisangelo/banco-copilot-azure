export interface SSEMessage {
  event: string;
  data: string;
}

export async function* parseSSE(stream: ReadableStream<Uint8Array>): AsyncGenerator<SSEMessage> {
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let event = "message";
  let data: string[] = [];

  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop()!;
    for (const line of lines) {
      if (line === "") {
        if (data.length > 0) yield { event, data: data.join("\n") };
        event = "message";
        data = [];
      } else if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data.push(line.slice(5).replace(/^ /, ""));
      }
    }
  }
}
