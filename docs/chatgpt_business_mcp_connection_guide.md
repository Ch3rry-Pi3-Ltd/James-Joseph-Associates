# ChatGPT Business MCP Connection Guide

## What Is Ready

The application now exposes a remote, read-only MCP endpoint:

`https://james-joseph-associates.vercel.app/mcp`

It provides six bounded tools:

1. Search candidates for a role using fast evidence retrieval.
2. Inspect one candidate profile and linked company context.
3. Retrieve a candidate's current CV reference and provenance.
4. Search candidates, contacts, interactions, jobs, and opportunities for a company.
5. Search the canonical company directory.
6. Discover company contacts and relationship evidence for a candidate.

The endpoint does not expose SQL, arbitrary tables, record updates, deletes,
outreach actions, or CRM writes.

## Production Configuration

Before connecting ChatGPT, production must contain:

- `MCP_API_TOKEN`: a unique, high-entropy server-side credential.
- `MCP_RATE_LIMIT_PER_MINUTE`: defaults to `60`.
- `MCP_TOOL_TIMEOUT_SECONDS`: defaults to `30` and bounds a complete tool call.
- `MCP_ALLOWED_HOSTS`: include the stable production hostname.
- Supabase migration `0009_mcp_operational_controls.sql`.
- Supabase migration `0016_mcp_read_path_indexes.sql` for the measured MCP
  provenance and recent-employment read paths.

Do not place the bearer credential in source control, screenshots, chat
messages, or client-side environment variables.

## Connect It In ChatGPT Business

This setup must be completed by a ChatGPT Business workspace owner or admin on
the ChatGPT web application.

1. Open **Workspace settings**.
2. Open **Apps** and enable **Developer mode** if it is not already enabled.
3. Choose **Create app**.
4. Enter the production MCP endpoint shown above.
5. Select API-key or bearer authentication if that option is available, then
   provide the production `MCP_API_TOKEN`.
6. Run **Scan tools**.
7. Confirm that exactly the six read-only tools listed above are discovered.
8. Publish the app only to the approved workspace users.

If the workspace setup offers only OAuth or no authentication, stop. Do not
choose an unauthenticated production connection. OAuth should be added to the
backend as the next rollout step.

ChatGPT Business may require an app to be recreated or republished after MCP
tool definitions change. Rescan and verify the tool list after each release.

The August 2026 live recruiter test prompted a material schema refinement to
the candidate-search and company-directory tools. After that release is
deployed, the workspace owner must rescan and republish the app snapshot before
testing the revised behavior.

That hardened release and migration `0016` were deployed and independently
smoke-tested on 22 August 2026. The remaining rollout action is the workspace
owner's **Scan tools** and republish step followed by the documented ChatGPT UAT
prompts; no new credential is required for that rescan.

After deploying or changing a tool contract, run the authenticated read-only
smoke test before asking a workspace user to retry:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_mcp_endpoint.py
```

The runner verifies authentication rejection, the exact six-tool read-only
surface, company prefix/quality metadata, bounded candidate evidence, and tool
timings. It performs no writes and does not print returned recruitment content.

## UAT Prompts

Use these prompts after the connection succeeds:

1. `Find the strongest five candidates for a senior Rust developer working on low-latency electronic trading. Explain the evidence and cite candidate IDs.`
2. `Show the current profile and CV reference for the strongest candidate. Do not invent missing details.`
3. `What contacts, prior interactions, jobs, and opportunities do we have for GSR? Cite the returned record IDs.`
4. `For the selected candidate, identify useful contacts at the target company and explain the relationship evidence.`
5. `List companies whose canonical names begin with "A", limited to 20 results. Include company IDs, provenance, and any quality warnings.`

## Acceptance Checks

- Requests without the MCP credential return `401`.
- Excess requests return `429`.
- Tool discovery shows read-only and non-destructive annotations.
- Responses contain bounded canonical evidence rather than unrestricted database rows.
- Audit rows contain tool name, outcome, duration, argument field names, and
  bounded failure stage/category only.
- No prompt text, CV text, candidate payload, database credential, or bearer token is
  written to the MCP audit table.
