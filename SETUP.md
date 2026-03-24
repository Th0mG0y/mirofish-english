# MiroFish Setup Guide

This guide is written for someone who wants the app to run without guessing.

Read it once from top to bottom before you start.

## Quick Start (One-Click Setup)

If you just want to get running as fast as possible, use the automated setup script. It will check for required tools, install any that are missing, start Neo4j, install all project dependencies, and launch the app.

**Windows (PowerShell):**

```powershell
.\start.ps1
```

**macOS / Linux (Bash):**

```bash
chmod +x start.sh
./start.sh
```

> **Note:** You still need to edit `.env` with your API keys before the app will work. The script copies `.env.openai.example` as a starting point if no `.env` exists. See [Accounts And Keys You May Need](#accounts-and-keys-you-may-need) below for how to get API keys.

If you prefer to set things up manually, or need a non-default provider configuration, continue reading below.

---

## What Is Different In This Version

This repository no longer uses Zep Cloud for graph building.

It now uses:

- `Graphiti` for graph building
- a local `Neo4j` database on your own computer
- separate provider settings for the main app, Graphiti extraction, embeddings, and reranking
- optional local vector models through `Ollama` or `LM Studio`

That means:

- you do need local Neo4j
- you do not need Zep Cloud for graph building
- you do not always need both OpenAI and Anthropic anymore

## Choose Your Setup Type

Pick one of these before you continue:

| Setup type | What you need | Example file |
|---|---|---|
| OpenAI-only | OpenAI key + Neo4j | `.env.openai.example` |
| Anthropic + OpenAI vectors | Anthropic key + OpenAI key + Neo4j | `.env.anthropic.example` |
| All local via Ollama | Neo4j + Ollama | `.env.ollama.example` |
| All local via LM Studio | Neo4j + LM Studio | `.env.lmstudio.example` |
| Mixed/custom | Any combination you want | `.env.example` |

## Important Search Note

Built-in web search works with real OpenAI or Anthropic APIs.

If you point an OpenAI-compatible setting to Ollama or LM Studio:

- text generation can work
- embeddings can work
- Graphiti local reranking can work
- built-in web search will not work there

If you want to keep setup simple, set:

- `MIROFISH_ENABLE_SEARCH_ENRICHMENT=false`

## What You Need Before You Start

Install these first:

| Thing | Why you need it | Where to get it |
|---|---|---|
| Node.js 18 or newer | Runs the frontend and npm commands | [nodejs.org](https://nodejs.org/en/download) |
| Python 3.11 or 3.12 | Runs the backend | [python.org](https://www.python.org/downloads/) |
| `uv` | The backend uses it to install Python packages | [uv install guide](https://docs.astral.sh/uv/getting-started/installation/) |
| Docker Desktop or Neo4j Desktop | Runs Neo4j locally | [Docker Desktop](https://www.docker.com/products/docker-desktop/) or [Neo4j Desktop](https://neo4j.com/download/) |
| Ollama or LM Studio | Only needed if you want local embeddings/reranking | [ollama.com](https://ollama.com/) or [lmstudio.ai](https://lmstudio.ai/) |

If you are on Windows:

- during Python installation, tick `Add Python to PATH`
- after installing tools, close and reopen PowerShell

## Accounts And Keys You May Need

### OpenAI

You need an OpenAI key if any of these use `openai`:

- `MIROFISH_LLM_PROVIDER`
- `MIROFISH_SEARCH_PROVIDER`
- `GRAPHITI_LLM_PROVIDER`
- `GRAPHITI_EMBEDDER_PROVIDER`
- `GRAPHITI_RERANKER_PROVIDER`

How to get it:

1. Go to [platform.openai.com](https://platform.openai.com/)
2. Create an account or sign in
3. Add billing if OpenAI asks for it
4. Open [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
5. Click `Create new secret key`
6. Copy the key immediately

Recommended starter models:

- main app: `gpt-5.4-mini`
- Graphiti extraction if you use OpenAI: `gpt-5.4-mini`
- Graphiti embeddings: `text-embedding-3-small`
- Graphiti reranking: `gpt-5.4-mini`

### Anthropic

You need an Anthropic key if any of these use `anthropic`:

- `MIROFISH_LLM_PROVIDER`
- `MIROFISH_SEARCH_PROVIDER`
- `GRAPHITI_LLM_PROVIDER`

How to get it:

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an account or sign in
3. Add billing if needed
4. Open [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
5. Create a new API key
6. Copy the key immediately

Recommended starter model:

- `claude-sonnet-4-6`

### Neo4j Login

If you use the Docker command in this guide, the default Neo4j login is:

- username: `neo4j`
- password: `password`

If you choose a different password, put the same password in `.env`.

## Step 1. Check Your Tools

Open PowerShell in the project folder and run:

```powershell
node -v
python --version
uv --version
```

You should see version numbers.

If a command says it is not recognized:

1. close PowerShell
2. reopen it
3. try again
4. reinstall that tool if it still fails

## Step 2. Start Neo4j

### Option A. Use Docker Desktop (recommended)

This is the easiest option for most people. The project includes a `docker-compose.yml` with a Neo4j service that uses persistent volumes, so your graph data survives container restarts.

From the project root, run:

```powershell
docker compose up neo4j -d
```

Then open:

- [http://localhost:7474](http://localhost:7474)

Log in with:

- username: `neo4j`
- password: `password`

To stop Neo4j without losing data:

```powershell
docker compose stop neo4j
```

To start it again later:

```powershell
docker compose up neo4j -d
```

### Option B. Use Neo4j Desktop

1. Install Neo4j Desktop
2. Create a local database
3. Set the username and password
4. Start it
5. Make sure the connection URL is `bolt://localhost:7687`

## Step 3. If You Want Local Vectors, Start Ollama Or LM Studio

You only need this step if `GRAPHITI_EMBEDDER_PROVIDER` or `GRAPHITI_RERANKER_PROVIDER` will use `ollama` or `lmstudio`.

### Option A. Ollama

1. Install Ollama from [ollama.com](https://ollama.com/)
2. Open a terminal
3. Pull an embedding model:

```powershell
ollama pull nomic-embed-text
```

4. Make sure Ollama is running

The default OpenAI-compatible URL used by this repo is:

- `http://localhost:11434/v1`

Recommended Ollama model:

- `nomic-embed-text`

### Option B. LM Studio

1. Install LM Studio from [lmstudio.ai](https://lmstudio.ai/)
2. Download a chat model and an embedding-capable model inside LM Studio
3. Start the local server
4. Turn on the OpenAI-compatible API
5. Confirm the server is listening on port `1234`

The default URL used by this repo is:

- `http://localhost:1234/v1`

Recommended LM Studio model:

- the embedding model name shown inside LM Studio after you load it

## Step 4. Create Your `.env` File

From the project root, copy the example that matches your setup.

### OpenAI-only

```powershell
Copy-Item .env.openai.example .env
```

### Anthropic + OpenAI vectors

```powershell
Copy-Item .env.anthropic.example .env
```

### All local via Ollama

```powershell
Copy-Item .env.ollama.example .env
```

### All local via LM Studio

```powershell
Copy-Item .env.lmstudio.example .env
```

### Mixed/custom

```powershell
Copy-Item .env.example .env
```

Then open `.env` and replace the placeholder values with your real values.

## Step 5. Pick The Right Env Settings

### Option 1. OpenAI-only

Use this when you want the whole app to run through OpenAI-compatible APIs.

```env
MIROFISH_LLM_PROVIDER=openai
LLM_API_KEY=your-openai-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-5.4-mini

GRAPHITI_LLM_PROVIDER=openai
GRAPHITI_LLM_MODEL=gpt-5.4-mini

GRAPHITI_EMBEDDER_PROVIDER=openai
GRAPHITI_EMBEDDER_MODEL=text-embedding-3-small

GRAPHITI_RERANKER_PROVIDER=openai
GRAPHITI_RERANKER_MODEL=gpt-5.4-mini
```

### Option 2. Anthropic + OpenAI vectors

Use this when you want Claude for the app and Graphiti extraction, but OpenAI for embeddings and reranking.

```env
MIROFISH_LLM_PROVIDER=anthropic
LLM_API_KEY=your-openai-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-5.4-mini
ANTHROPIC_API_KEY=your-anthropic-api-key-here
ANTHROPIC_MODEL_NAME=claude-sonnet-4-6

GRAPHITI_LLM_PROVIDER=anthropic
GRAPHITI_LLM_MODEL=claude-sonnet-4-6

GRAPHITI_EMBEDDER_PROVIDER=openai
GRAPHITI_EMBEDDER_MODEL=text-embedding-3-small

GRAPHITI_RERANKER_PROVIDER=openai
GRAPHITI_RERANKER_MODEL=gpt-5.4-mini
```

### Option 3. All local via Ollama

Use this when you want the whole project on local Ollama models and do not want cloud API keys.

```env
MIROFISH_LLM_PROVIDER=openai
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen3:14b

GRAPHITI_LLM_PROVIDER=openai
GRAPHITI_LLM_BASE_URL=http://localhost:11434/v1
GRAPHITI_LLM_MODEL=qwen3:14b

GRAPHITI_EMBEDDER_PROVIDER=ollama
GRAPHITI_EMBEDDER_BASE_URL=http://localhost:11434/v1
GRAPHITI_EMBEDDER_MODEL=nomic-embed-text

GRAPHITI_RERANKER_PROVIDER=ollama
GRAPHITI_RERANKER_BASE_URL=http://localhost:11434/v1
GRAPHITI_RERANKER_MODEL=nomic-embed-text
```

### Option 4. All local via LM Studio

Use this when you want the whole project on local LM Studio models and do not want cloud API keys.

```env
MIROFISH_LLM_PROVIDER=openai
LLM_API_KEY=lm-studio
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL_NAME=your-loaded-lm-studio-chat-model

GRAPHITI_LLM_PROVIDER=openai
GRAPHITI_LLM_BASE_URL=http://localhost:1234/v1
GRAPHITI_LLM_MODEL=your-loaded-lm-studio-chat-model

GRAPHITI_EMBEDDER_PROVIDER=lmstudio
GRAPHITI_EMBEDDER_BASE_URL=http://localhost:1234/v1
GRAPHITI_EMBEDDER_MODEL=your-loaded-lm-studio-embedding-model

GRAPHITI_RERANKER_PROVIDER=lmstudio
GRAPHITI_RERANKER_BASE_URL=http://localhost:1234/v1
GRAPHITI_RERANKER_MODEL=your-loaded-lm-studio-embedding-model
```

### Option 5. Mixed

You can mix providers however you want.

Example:

- main app: Anthropic
- search: Anthropic
- Graphiti extraction: OpenAI
- Graphiti embeddings: Ollama
- Graphiti reranking: LM Studio

## Step 6. Install Project Dependencies

From the project root, run:

```powershell
npm run setup:all
```

## Step 7. Install The Extra Backend Packages For This Graphiti Build

Run this from the `backend` folder:

```powershell
cd backend
uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"
```

If PowerShell says some of them are already installed, that is fine.

## Step 8. Start The App

Go back to the project root and run:

```powershell
cd ..
npm run dev
```

That starts:

- frontend: [http://localhost:5173](http://localhost:5173)
- backend: [http://localhost:5001](http://localhost:5001)

If you prefer two terminals:

Terminal 1:

```powershell
cd backend
uv run python run.py
```

Terminal 2:

```powershell
cd frontend
npm run dev
```

## Step 9. Check That Everything Works

Open:

- frontend: [http://localhost:5173](http://localhost:5173)
- backend health check: [http://localhost:5001/health](http://localhost:5001/health)

The health response should look like:

```json
{"status":"ok","service":"MiroFish Backend"}
```

## Step 10. First Graph Build Note

The first graph build may be slower because Graphiti creates Neo4j indexes the first time.

That is normal.

## Troubleshooting

### `python`, `node`, or `uv` is not recognized

That tool is not installed correctly or is missing from `PATH`.

Fix:

1. reinstall that tool
2. make sure the installer adds it to `PATH`
3. close and reopen PowerShell

### Neo4j does not start

Check:

- Docker Desktop is open
- no other app is already using ports `7474` or `7687`
- Neo4j Desktop is not trying to use the same ports at the same time

### Graph building fails when using Anthropic + OpenAI vectors

Check:

- Neo4j is running
- `ANTHROPIC_API_KEY` is real and valid
- `LLM_API_KEY` is real and valid
- `GRAPHITI_EMBEDDER_PROVIDER=openai`
- `GRAPHITI_RERANKER_PROVIDER=openai`

### Graph building fails when using OpenAI-only

Check:

- `LLM_API_KEY` is real and valid
- `GRAPHITI_LLM_PROVIDER=openai`
- `GRAPHITI_EMBEDDER_PROVIDER=openai`
- `GRAPHITI_RERANKER_PROVIDER=openai`

### Search features fail while using Ollama or LM Studio

That is usually because local OpenAI-compatible servers do not provide the built-in web search APIs this app expects.

Fix:

1. set `MIROFISH_ENABLE_SEARCH_ENRICHMENT=false`
2. keep `MIROFISH_SEARCH_PROVIDER=anthropic` or a real OpenAI account

## Simplest Working Checklists

> **Tip:** For the OpenAI-only setup you can skip all manual steps and just run `.\start.ps1` (Windows) or `./start.sh` (macOS/Linux). The script handles everything below automatically — you only need to fill in your API key in `.env` afterwards.

### OpenAI-only

1. Install Node.js, Python, `uv`, and Docker Desktop
2. Create an OpenAI API key
3. Start Neo4j: `docker compose up neo4j -d`
4. Copy `.env.openai.example` to `.env`
5. Fill in your OpenAI key
6. Run `npm run setup:all`
7. Run `cd backend`
8. Run `uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"`
9. Run `cd ..`
10. Run `npm run dev`

### Anthropic + OpenAI vectors

1. Install Node.js, Python, `uv`, and Docker Desktop
2. Create an Anthropic API key
3. Start Neo4j: `docker compose up neo4j -d`
4. Create an OpenAI API key
5. Copy `.env.anthropic.example` to `.env`
6. Fill in your Anthropic key and OpenAI key
7. Run `npm run setup:all`
8. Run `cd backend`
9. Run `uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"`
10. Run `cd ..` and `npm run dev`

### All local via LM Studio

1. Install Node.js, Python, `uv`, Docker Desktop, and LM Studio
2. Start Neo4j: `docker compose up neo4j -d`
3. Load a chat model and an embedding model in LM Studio
4. Start the LM Studio local server on port `1234`
5. Copy `.env.lmstudio.example` to `.env`
6. Replace the model names with the exact names shown by LM Studio
7. Run `npm run setup:all`
8. Run `cd backend`
9. Run `uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"`
10. Run `cd ..` and `npm run dev`

### All local via Ollama

1. Install Node.js, Python, `uv`, Docker Desktop, and Ollama
2. Start Neo4j: `docker compose up neo4j -d`
3. Run `ollama pull nomic-embed-text`
4. Make sure your Ollama chat model is also pulled
5. Copy `.env.ollama.example` to `.env`
6. Replace the model names if needed
7. Run `npm run setup:all`
8. Run `cd backend`
9. Run `uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"`
10. Run `cd ..` and `npm run dev`

## Final Reminder

For this customized implementation:

- Zep Cloud key: not required for graph building
- local Neo4j: always required
- OpenAI key: only required if you choose OpenAI for one of the provider slots
- Anthropic key: only required if you choose Anthropic for one of the provider slots
- Ollama or LM Studio: only required if you choose local vector models