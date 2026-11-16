# Sandbox agent POC

A plain agent with a shell runs in its own Agent Substrate sandbox. It can reach only
the destinations we allow, and it uses a GitHub credential it never holds.

**What it demos:**
- **Only where we allow:** the GitHub API works; everything else (Google, the weather,
  webhook.site) is blocked.
- **Never holds secrets:** it calls GitHub as its own account, but finds no token in its
  environment or files. Substrate's egress gateway adds the token on the way out.
- **Contained:** each chat is its own sandbox. A file saved in one chat doesn't exist in
  the next, even for the same user.

```
sandbox-agent (Substrate sandbox) ──"Authorization: Bearer placeholder"──▶ egress gateway ──real token──▶ api.github.com
                                  ──anything else──▶ egress gateway ──✕ blocked
```

| Path | What it is |
|---|---|
| `sandbox-agent.yaml` | The agent: only kagent's built-in shell and file tools, short plain answers, sends a placeholder `Authorization` header for GitHub |
| `egresspolicy-github.yaml` | Allows `https://api.github.com` only and injects the `github-agent-token` Secret into `Authorization` |
| `ready.sh` | Demo state: builds the Secret from `.secrets/github-agent-token.txt`, applies the policy and agent |
| `reset.sh` | Turns it off again: no network access, no token |
| `trust-corporate-ca.sh` | Only behind a TLS-inspecting proxy: adds `.secrets/ca-bundle.pem` to the egress gateway (re-run after Substrate upgrades) |

## Setup

1. Put the agent's own GitHub token in `.secrets/github-agent-token.txt` (a separate
   "bot" account, so it's clearly the agent's identity, not yours).
2. `./ready.sh`

## Run

Chat with `sandbox-agent`:

1. "Can you reach google.com?" → not reachable.
2. "What's GitHub's zen message today?" → works.
3. "Who am I on GitHub?" → the bot account.
4. "Check whether you have any GitHub credentials anywhere: environment, files, settings. What did you find?" → none.
5. "Remember this for me: the launch code is 4471. Save it to a file." Then, in a **new chat**:
   "What's the launch code I gave you earlier? Check your files." → nothing there.

Afterwards: `./reset.sh` to remove network access and the token.
