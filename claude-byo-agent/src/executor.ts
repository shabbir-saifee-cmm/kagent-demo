import { query } from '@anthropic-ai/claude-agent-sdk';
import {
  Task,
  TaskState,
  TaskStatusUpdateEvent,
  TaskArtifactUpdateEvent,
  Artifact,
  Message,
  Role,
} from '@a2a-js/sdk';
import {
  AgentExecutor,
  RequestContext,
  ExecutionEventBus,
  AgentEvent,
} from '@a2a-js/sdk/server';

function textOf(message: Message): string {
  const part = message.parts.find((p) => p.content?.$case === 'text');
  return part?.content?.$case === 'text' ? part.content.value.trim() : '';
}

function agentMessage(taskId: string, contextId: string, text: string): Message {
  return {
    role: Role.ROLE_AGENT,
    messageId: crypto.randomUUID(),
    parts: [
      {
        content: { $case: 'text', value: text },
        metadata: undefined,
        filename: '',
        mediaType: 'text/plain',
      },
    ],
    taskId,
    contextId,
    extensions: [],
    metadata: {},
    referenceTaskIds: [],
  };
}

/**
 * Bridges A2A task requests to the Claude Agent SDK, authenticated via
 * CLAUDE_CODE_OAUTH_TOKEN (a Claude Pro/Max/Team subscription token from
 * `claude setup-token`), not a metered ANTHROPIC_API_KEY.
 */
export class ClaudeAgentExecutor implements AgentExecutor {
  private readonly cancelledTasks = new Set<string>();

  public cancelTask = async (taskId: string, _eventBus: ExecutionEventBus): Promise<void> => {
    this.cancelledTasks.add(taskId);
  };

  async execute(requestContext: RequestContext, eventBus: ExecutionEventBus): Promise<void> {
    const userMessage = requestContext.userMessage;
    const taskId = requestContext.taskId;
    const contextId = requestContext.contextId;
    const existingTask = requestContext.task;

    try {
      const taskSnapshot: Task = existingTask ?? {
        id: taskId,
        contextId,
        status: {
          state: TaskState.TASK_STATE_SUBMITTED,
          timestamp: new Date().toISOString(),
          message: undefined,
        },
        artifacts: [],
        history: [userMessage],
        metadata: userMessage.metadata,
      };
      eventBus.publish(AgentEvent.task(taskSnapshot));

      eventBus.publish(
        AgentEvent.statusUpdate({
          taskId,
          contextId,
          status: {
            state: TaskState.TASK_STATE_WORKING,
            message: agentMessage(taskId, contextId, 'Working on it...'),
            timestamp: new Date().toISOString(),
          },
          metadata: {},
        } satisfies TaskStatusUpdateEvent)
      );

      const prompt = textOf(userMessage) || 'Hello';
      let resultText = '';

      for await (const sdkMessage of query({ prompt })) {
        if (this.cancelledTasks.has(taskId)) {
          eventBus.publish(
            AgentEvent.statusUpdate({
              taskId,
              contextId,
              status: { state: TaskState.TASK_STATE_CANCELED, timestamp: new Date().toISOString(), message: undefined },
              metadata: {},
            } satisfies TaskStatusUpdateEvent)
          );
          return;
        }
        if (sdkMessage.type === 'result' && sdkMessage.subtype === 'success') {
          resultText = sdkMessage.result;
        }
      }

      const artifact: Artifact = {
        artifactId: crypto.randomUUID(),
        name: 'Result',
        description: 'Claude Agent SDK response',
        parts: [
          {
            content: { $case: 'text', value: resultText || '(no response)' },
            metadata: undefined,
            filename: '',
            mediaType: 'text/plain',
          },
        ],
        metadata: undefined,
        extensions: [],
      };
      eventBus.publish(
        AgentEvent.artifactUpdate({
          taskId,
          contextId,
          artifact,
          lastChunk: true,
          append: false,
          metadata: undefined,
        } satisfies TaskArtifactUpdateEvent)
      );

      eventBus.publish(
        AgentEvent.statusUpdate({
          taskId,
          contextId,
          status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
          metadata: undefined,
        } satisfies TaskStatusUpdateEvent)
      );
    } finally {
      this.cancelledTasks.delete(taskId);
    }
  }
}
