# Strongly.AI Platform Deployment

Open Notebook can be deployed on the Strongly.AI marketplace platform with automatic service discovery and header-based authentication.

## Features

When running on Strongly.AI:
- **AI Gateway Integration**: All LLM calls route through Strongly's AI Gateway
- **Header-Based Authentication**: User identity injected via proxy headers
- **Service Discovery**: Database and API connections configured automatically via `STRONGLY_SERVICES`
- **No API Keys Required**: LLM access managed by the platform

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `STRONGLY_MODE` | Set to `true` to enable Strongly.AI integration |
| `STRONGLY_SERVICES` | JSON containing platform service configurations |

### STRONGLY_SERVICES Format

The platform injects a `STRONGLY_SERVICES` environment variable with service configurations:

```json
{
  "services": {
    "ai_gateway": {
      "base_url": "https://gateway.strongly.ai/v1",
      "api_key": "platform-managed-key"
    }
  }
}
```

### Authentication Headers

The Strongly.AI proxy injects these headers on all requests:

| Header | Description |
|--------|-------------|
| `X-Auth-User-Id` | Unique user identifier |
| `X-Auth-User-Email` | User's email address |
| `X-Auth-User-Name` | User's display name |
| `X-Auth-App-Role` | User's role in this app (admin, developer, app) |
| `X-Auth-Platform-Role` | User's platform-wide role |
| `X-Auth-Authenticated` | `true` if user is authenticated |

## Deployment Files

### strongly.manifest.yml

Defines the application for the Strongly.AI platform:

```yaml
name: open-notebook
displayName: Open Notebook
type: fullstack

app:
  frontend:
    port: 3000
    buildCommand: cd frontend && npm install && npm run build
    startCommand: cd frontend && npm start

  backend:
    port: 5055
    runtime: python
    pythonVersion: "3.11"
    startCommand: python run_api.py
    env:
      - name: STRONGLY_MODE
        value: "true"

port: 8088

services:
  - name: ai_gateway
    required: true

databases:
  - type: surrealdb
    name: open_notebook
```

### docker-compose.strongly.yml

For local testing with Strongly.AI configuration:

```bash
docker-compose -f docker-compose.strongly.yml up --build
```

## API Endpoints

### GET /api/strongly/status

Returns Strongly.AI integration status:

```json
{
  "enabled": true,
  "ai_gateway_configured": true,
  "ai_gateway_url": "https://gateway.strongly.ai/v1"
}
```

### GET /api/strongly/models

Lists available models from the AI Gateway.

### POST /api/strongly/sync-models

Syncs available AI Gateway models to Open Notebook's database as `openai_compatible` provider models.

### DELETE /api/strongly/models

Removes all synced AI Gateway models from the database.

## Model Selection

In Strongly.AI mode, models are restricted to those available through the AI Gateway:

1. On startup, the app configures the `openai_compatible` provider to use the AI Gateway
2. Use `/api/strongly/sync-models` to import available models
3. Select synced models in the Settings page

The AI Gateway supports various models including:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Local models (via Ollama)
- Other OpenAI-compatible endpoints

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Strongly.AI Platform                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │   Proxy     │───▶│ Open Notebook │───▶│  AI Gateway   │  │
│  │ (Auth Hdrs) │    │   Backend     │    │  (LLM APIs)   │  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
│         │                  │                                 │
│         │                  ▼                                 │
│         │           ┌──────────────┐                        │
│         │           │   SurrealDB   │                        │
│         │           └──────────────┘                        │
│         ▼                                                    │
│  ┌─────────────┐                                            │
│  │  Frontend   │                                            │
│  │  (Next.js)  │                                            │
│  └─────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### AI Gateway not configured

If `/api/strongly/status` shows `ai_gateway_configured: false`:
1. Verify `STRONGLY_SERVICES` environment variable is set
2. Check the JSON format is valid
3. Ensure `ai_gateway` section exists with `base_url` and `api_key`

### Models not appearing

1. Call `POST /api/strongly/sync-models` to import models
2. Check the AI Gateway is accessible
3. Verify the API key has permission to list models

### Authentication errors

If seeing 401 errors:
1. Verify `STRONGLY_MODE=true` is set
2. Check proxy is injecting `X-Auth-*` headers
3. Ensure `X-Auth-Authenticated` header is `true`
