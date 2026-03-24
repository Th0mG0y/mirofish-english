# MiroFish Setup Guide

This guide is written for someone who just wants the project to run.

Read this whole file once before you start clicking things.

## What Is Different In This Version

This repository has been customized to use:

- `Graphiti` for graph building
- a local `Neo4j` database on your own computer
- `Anthropic` for Graphiti entity extraction
- `OpenAI` for the main app model and Graphiti embeddings/reranking

This means:

- you do **not** need Zep Cloud for graph building anymore
- you **do** need a running local Neo4j database
- you currently need **both** an OpenAI API key and an Anthropic API key for the full app to work correctly

## What You Need Before You Start

Install these first:

| Thing | Why you need it | Where to get it |
|---|---|---|
| Node.js 18 or newer | Runs the frontend and npm commands | [nodejs.org](https://nodejs.org/en/download) |
| Python 3.11 or 3.12 | Runs the backend | [python.org](https://www.python.org/downloads/) |
| `uv` | The backend uses it to manage Python packages | [uv install guide](https://docs.astral.sh/uv/getting-started/installation/) |
| Docker Desktop or Neo4j Desktop | Needed to run Neo4j locally | [Docker Desktop](https://www.docker.com/products/docker-desktop/) or [Neo4j Desktop](https://neo4j.com/download/) |

If you are on Windows:

- when installing Python, make sure you tick `Add Python to PATH`
- after installing software, close and reopen PowerShell before continuing

## Accounts And API Keys You Need

### 1. OpenAI account

You need this because this implementation uses OpenAI-compatible calls for:

- the main application model
- Graphiti embeddings
- Graphiti reranking

How to get the key:

1. Go to [platform.openai.com](https://platform.openai.com/)
2. Sign in or create an account
3. Add billing to the account if OpenAI asks for it
4. Open the API keys page: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
5. Click `Create new secret key`
6. Copy the key immediately and keep it somewhere safe

Recommended model to use:

- `gpt-4o-mini`

### 2. Anthropic account

You need this because Graphiti in this project uses Anthropic for graph/entity extraction.

How to get the key:

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign in or create an account
3. Add billing if required
4. Open the keys page: [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
5. Create a new API key
6. Copy the key immediately and keep it somewhere safe

Recommended model to use:

- `claude-sonnet-4-6`

### 3. Neo4j login

You also need a Neo4j username and password.

If you use the Docker command later in this guide, the login will be:

- username: `neo4j`
- password: `password`

You can change that if you want, but then you must also put the same values in your `.env` file.

## Recommended Settings To Use

If you want the easiest setup, use these exact values:

```env
MIROFISH_LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o-mini

ANTHROPIC_MODEL_NAME=claude-sonnet-4-6

MIROFISH_SEARCH_PROVIDER=anthropic
MIROFISH_SEARCH_MODEL=claude-sonnet-4-6

MIROFISH_ENABLE_SEARCH_ENRICHMENT=false
```

Why these values:

- `gpt-4o-mini` is a lower-cost OpenAI model and is a simple starting point
- `claude-sonnet-4-6` is a solid default for Anthropic
- turning search enrichment off keeps setup simpler and cheaper for a first run

## Step 1. Check That The Tools Installed Correctly

Open PowerShell in the project folder and run:

```powershell
node -v
python --version
uv --version
```

You should see version numbers printed out.

If one of those commands says it is not recognized:

- close PowerShell
- reopen it
- try again
- if it still fails, that tool was not installed correctly yet

## Step 2. Start Neo4j

You have two ways to do this.

### Option A. Start Neo4j with Docker Desktop

This is the easiest option for most people.

1. Make sure Docker Desktop is open and fully started
2. Run this in PowerShell:

```powershell
docker run -d --name neo4j -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/password neo4j:5.26
```

What this does:

- downloads Neo4j if you do not already have it
- starts Neo4j in the background
- opens port `7687` for the app
- opens port `7474` for the Neo4j browser

After that, open:

- [http://localhost:7474](http://localhost:7474)

Sign in with:

- username: `neo4j`
- password: `password`

If Docker says the container name already exists, it usually means Neo4j was already created earlier. In that case try:

```powershell
docker start neo4j
```

### Option B. Start Neo4j with Neo4j Desktop

If you prefer a desktop app instead of Docker:

1. Install Neo4j Desktop from [neo4j.com/download](https://neo4j.com/download/)
2. Create a local database
3. Set the username and password
4. Start the database
5. Make sure the connection URL is `bolt://localhost:7687`
6. Write down the username and password because you will need them in `.env`

## Step 3. Create Your `.env` File

From the project root, copy the example file.

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

Then open `.env` in a text editor and replace the values with your real keys.

Use this as your starting point:

```env
# Main app model
MIROFISH_LLM_PROVIDER=openai
LLM_API_KEY=your-openai-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o-mini

# Graphiti extraction
ANTHROPIC_API_KEY=your-anthropic-api-key-here
ANTHROPIC_MODEL_NAME=claude-sonnet-4-6

# Optional search features
MIROFISH_SEARCH_PROVIDER=anthropic
MIROFISH_SEARCH_MODEL=claude-sonnet-4-6
MIROFISH_ENABLE_SEARCH_ENRICHMENT=false
MIROFISH_MAX_SEARCHES_PER_AGENT=5
MIROFISH_NEWS_INJECTION_INTERVAL=0

# Local Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Legacy Zep key
# This Graphiti version does not use Zep for graph building.
ZEP_API_KEY=

# App basics
SECRET_KEY=mirofish-secret-key
FLASK_DEBUG=True
OASIS_DEFAULT_MAX_ROUNDS=10
MIROFISH_TIMEZONE=us_eastern
MIROFISH_LOCALE=en-US
MIROFISH_REGION=US
REPORT_AGENT_MAX_TOOL_CALLS=5
REPORT_AGENT_MAX_REFLECTION_ROUNDS=2
REPORT_AGENT_TEMPERATURE=0.5
```

Important notes:

- `LLM_API_KEY` should be a real OpenAI key in this implementation
- `ANTHROPIC_API_KEY` should be a real Anthropic key
- `ZEP_API_KEY` is no longer required for the Graphiti graph-building path
- if you changed the Neo4j password, change `NEO4J_PASSWORD` here too

## Step 4. Install Project Dependencies

From the project root, run:

```powershell
npm run setup:all
```

This installs:

- the root Node packages
- the frontend packages
- the backend Python packages that are listed in `backend/pyproject.toml`

## Step 5. Install The Extra Backend Packages Required By This Graphiti Version

This step is important.

The customized Graphiti + Neo4j implementation needs a few extra backend packages that are not fully covered by the current backend sync command by itself.

Run this from the `backend` folder:

```powershell
cd backend
uv run python -m pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"
```

Why this step exists:

- `graphiti-core==0.28.2` is the graph system used by this version
- `neo4j==5.26.0` avoids the version conflict described during the Graphiti migration
- `anthropic` is needed for the Anthropic API client

If PowerShell says a package is already installed, that is fine.

## Step 6. Start The App

Go back to the project root and run:

```powershell
cd ..
npm run dev
```

That starts both services:

- frontend: [http://localhost:5173](http://localhost:5173)
- backend API: [http://localhost:5001](http://localhost:5001)

If you prefer to run them separately, use two terminals:

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

## Step 7. Check That Everything Works

Open these in your browser:

- frontend: [http://localhost:5173](http://localhost:5173)
- backend health check: [http://localhost:5001/health](http://localhost:5001/health)

The backend health check should return:

```json
{"status":"ok","service":"MiroFish Backend"}
```

If the frontend loads and the backend health page works, the project is running.

## Step 8. First-Time Graph Build Note

The first time you build a graph:

- Graphiti will create Neo4j indexes automatically
- this can make the first graph build a little slower than later runs

That is normal.

## If Something Goes Wrong

### Problem: `python`, `node`, or `uv` is not recognized

That tool is either not installed or not added to your system `PATH`.

Fix:

1. reinstall that tool
2. make sure the installer adds it to `PATH`
3. close and reopen PowerShell

### Problem: Docker command fails

Check these first:

- Docker Desktop is open
- virtualization is enabled on your machine
- no other app is already using ports `7474` or `7687`

### Problem: Frontend opens, but graph building fails

The most common reasons are:

- Neo4j is not running
- `ANTHROPIC_API_KEY` is missing or invalid
- `LLM_API_KEY` is missing or invalid
- the wrong Neo4j Python package version is installed

Run this again inside `backend`:

```powershell
uv run python -m pip install "neo4j==5.26.0"
```

### Problem: Backend starts, but some AI features fail

Double-check:

- your OpenAI account has billing enabled
- your Anthropic account has billing enabled
- the API keys in `.env` are real keys, not placeholders
- you did not leave quotation marks around the keys unless you intentionally want them there

### Problem: Neo4j browser does not open

Try:

- [http://localhost:7474](http://localhost:7474)

If it still does not load, Neo4j is probably not running yet.

## Simplest Working Checklist

If you only want the short version, this is the order:

1. Install Node.js, Python, `uv`, and Docker Desktop
2. Create an OpenAI API key
3. Create an Anthropic API key
4. Start Neo4j locally
5. Copy `.env.example` to `.env`
6. Paste in your real API keys and Neo4j password
7. Run `npm run setup:all`
8. Run `cd backend` and `uv run python -m pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"`
9. Run `cd ..` and `npm run dev`
10. Open [http://localhost:5173](http://localhost:5173)

## Final Reminder

For this customized implementation, the safest beginner setup is:

- OpenAI key: required
- Anthropic key: required
- local Neo4j: required
- Zep Cloud key: not required for graph building