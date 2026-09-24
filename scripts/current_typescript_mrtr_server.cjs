/* Bounded capability probe for the stable TypeScript SDK v2 stdio MRTR surface. */
const { McpServer, inputRequired, acceptedContent, createRequestStateCodec, fromJsonSchema } = require('@modelcontextprotocol/server');
const { serveStdio } = require('@modelcontextprotocol/server/stdio');

const codec = createRequestStateCodec({
  key: Buffer.alloc(32, 37),
  ttlSeconds: 600,
  bind: () => 'synthetic-principal',
});
const server = new McpServer(
  { name: 'typescript-capability-probe', version: '0.0.1' },
  { capabilities: { tools: {} }, requestState: { verify: codec.verify } },
);
server.registerTool('probe_roundtrip', { inputSchema: fromJsonSchema({ type: 'object', properties: { operation_id: { type: 'string' } }, required: ['operation_id'] }) }, async ({ operation_id }, ctx) => {
  const response = acceptedContent(ctx.mcpReq.inputResponses, 'body');
  if (response === undefined) {
    return inputRequired({
      inputRequests: { body: inputRequired.elicit({
        message: 'Synthetic body?',
        requestedSchema: { type: 'object', properties: { body: { type: 'string' } }, required: ['body'] },
      }) },
      requestState: await codec.mint({ operation_id }, ctx),
    });
  }
  const state = ctx.mcpReq.requestState();
  if (state?.operation_id !== operation_id) throw new Error('operation binding mismatch');
  return { content: [{ type: 'text', text: 'accepted' }], structuredContent: { operation_id, accepted: response.body === 'alpha' } };
});
serveStdio(() => server);
