import express from 'express';
import { A2A_PROTOCOL_VERSION, AgentCard, AGENT_CARD_PATH } from '@a2a-js/sdk';
import { InMemoryTaskStore, TaskStore, DefaultRequestHandler } from '@a2a-js/sdk/server';
import { agentCardHandler, jsonRpcHandler, UserBuilder } from '@a2a-js/sdk/server/express';
import { duplicateInterfacesForLegacy } from '@a2a-js/sdk/compat/v0_3';
import { ClaudeAgentExecutor } from './executor.js';

// kagent's BYO Agent contract: the container must serve A2A on port 8080.
const PORT = process.env.PORT || 8080;

// kagent 0.10.x's controller/UI omits the A2A-Version header, so per spec
// it's treated as v0.3 (the legacy wire format) — duplicateInterfacesForLegacy
// advertises a v0.3-compatible mirror of the JSONRPC binding so those
// requests are accepted instead of rejected with VersionNotSupported.
const supportedInterfaces = duplicateInterfacesForLegacy(
  [
    {
      url: `http://localhost:${PORT}/`,
      protocolBinding: 'JSONRPC',
      tenant: '',
      protocolVersion: A2A_PROTOCOL_VERSION,
    },
  ],
  ['JSONRPC']
);

const agentCard: AgentCard = {
  name: 'claude-byo-agent',
  description:
    'Claude Code / Claude Agent SDK running as a kagent BYO Agent, authenticated with a personal Claude subscription (CLAUDE_CODE_OAUTH_TOKEN) instead of a metered Anthropic API key.',
  supportedInterfaces,
  provider: { organization: 'kagent-wild-panda', url: '' },
  version: '0.1.0',
  capabilities: { streaming: true, pushNotifications: false, extensions: [], extendedAgentCard: false },
  securitySchemes: {},
  securityRequirements: [],
  defaultInputModes: ['text'],
  defaultOutputModes: ['text', 'task-status'],
  skills: [
    {
      id: 'claude_agent',
      name: 'Claude Agent',
      description: 'General-purpose assistant backed by the Claude Agent SDK.',
      tags: ['claude'],
      examples: ['What can you help me with?'],
      inputModes: ['text'],
      outputModes: ['text', 'task-status'],
      securityRequirements: [],
    },
  ],
  documentationUrl: '',
  signatures: [],
};

const taskStore: TaskStore = new InMemoryTaskStore();
const requestHandler = new DefaultRequestHandler(agentCard, taskStore, new ClaudeAgentExecutor());

const app = express();
app.use(
  `/${AGENT_CARD_PATH}`,
  agentCardHandler({ agentCardProvider: requestHandler, legacyCompat: { enabled: true } })
);
app.use(
  jsonRpcHandler({
    requestHandler,
    userBuilder: UserBuilder.noAuthentication,
    legacyCompat: { enabled: true },
  })
);
app.get('/health', (_req, res) => res.status(200).send('ok'));

app.listen(PORT, () => {
  console.log(`[claude-byo-agent] listening on :${PORT}`);
});
