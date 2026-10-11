import { describe, expect, it } from "vitest";
import { parseSSE } from "./sse";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of parseSSE(stream)) events.push(event);
  return events;
}

describe("parseSSE", () => {
  it("yields named events with their data", async () => {
    const events = await collect(
      streamOf('event: trace\ndata: {"node":"router"}\n\nevent: answer\ndata: {"status":"ok"}\n\n'),
    );
    expect(events).toEqual([
      { event: "trace", data: '{"node":"router"}' },
      { event: "answer", data: '{"status":"ok"}' },
    ]);
  });

  it("reassembles an event split across chunks", async () => {
    const events = await collect(streamOf("event: tr", 'ace\ndata: {"no', 'de":"rag"}\n', "\n"));
    expect(events).toEqual([{ event: "trace", data: '{"node":"rag"}' }]);
  });

  it("accepts CRLF line endings and joins multi-line data", async () => {
    const events = await collect(streamOf("event: answer\r\ndata: line1\r\ndata: line2\r\n\r\n"));
    expect(events).toEqual([{ event: "answer", data: "line1\nline2" }]);
  });

  it("ignores comments and defaults the event name to message", async () => {
    const events = await collect(streamOf(": ping\n\ndata: x\n\n"));
    expect(events).toEqual([{ event: "message", data: "x" }]);
  });
});
