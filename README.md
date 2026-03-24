<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Logo" width="75%"/>

</br>
<em>A Simple and Universal Swarm Intelligence Engine, Predicting Anything</em>

</div>

## ⚡ Project Overview

**MiroFish** is a next-generation AI prediction engine powered by multi-agent technology. By extracting seed information from the real world (such as breaking news, policy drafts, or financial signals), it automatically constructs a high-fidelity parallel digital world. Within this space, thousands of intelligent agents with independent personalities, long-term memory, and behavioral logic freely interact and undergo social evolution. You can inject variables dynamically from a "God's-eye view" to precisely deduce future trajectories — **rehearse the future in a digital sandbox, and win decisions after countless simulations**.

> You only need to: Upload seed materials (data analysis reports or interesting novel stories) and describe your prediction requirements in natural language</br>
> MiroFish will return: A detailed prediction report and a deeply interactive high-fidelity digital world

### Our Vision

MiroFish is dedicated to creating a swarm intelligence mirror that maps reality. By capturing the collective emergence triggered by individual interactions, we break through the limitations of traditional prediction:

- **At the Macro Level**: We are a rehearsal laboratory for decision-makers, allowing policies and public relations to be tested at zero risk
- **At the Micro Level**: We are a creative sandbox for individual users — whether deducing novel endings or exploring imaginative scenarios, everything can be fun, playful, and accessible

From serious predictions to playful simulations, we let every "what if" see its outcome, making it possible to predict anything.

## This Repository Variant

This local implementation is **not** using Zep Cloud for graph building.

Instead, it uses:

- `Graphiti` for knowledge-graph construction
- a local `Neo4j` database running on your own machine
- separate provider settings for the main app, Graphiti extraction, embeddings, and reranking
- optional local vector models through `Ollama` or `LM Studio`

What that means in practice:

- you need a local Neo4j instance running before graph building will work
- you can run OpenAI-only, Anthropic plus local vectors, or a mixed setup
- the old Zep-based quick start is no longer the correct setup path for this implementation

If you want a full beginner-friendly walkthrough, including where to get API keys and exactly which models to set, start here:

- [`SETUP.md`](./SETUP.md)

Quick template choices:

- `OpenAI-only`: `.env.openai.example`
- `Anthropic + OpenAI vectors`: `.env.anthropic.example`
- `All local via Ollama`: `.env.ollama.example`
- `All local via LM Studio`: `.env.lmstudio.example`
- `Mixed/custom`: `.env.example`

## 🔄 Workflow

1. **Graph Building**: Seed extraction & Individual/collective memory injection & GraphRAG construction
2. **Environment Setup**: Entity relationship extraction & Persona generation & Agent configuration injection
3. **Simulation**: Dual-platform parallel simulation & Auto-parse prediction requirements & Dynamic temporal memory updates
   > **Tip:** Keep simulations at or below **20 rounds** to avoid hitting OpenAI/Anthropic rate limits.
4. **Report Generation**: ReportAgent with rich toolset for deep interaction with post-simulation environment
5. **Deep Interaction**: Chat with any agent in the simulated world & Interact with ReportAgent

## 🚀 Quick Start

### Recommended Path

For this Graphiti + Neo4j implementation, the recommended path is:

1. Follow [`SETUP.md`](./SETUP.md) from top to bottom
2. Start Neo4j locally first
3. Copy the env template that matches your provider setup
4. Install dependencies
5. Start the app with `npm run dev`

### Fast Summary

From the project root:

```bash
# 1. Start Neo4j (persistent data via Docker volume)
docker compose up neo4j -d

# 2. Copy the environment file
cp .env.openai.example .env

# 3. Install root + frontend + backend dependencies
npm run setup:all

# 4. Install the extra packages required by this Graphiti build
cd backend
uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"
cd ..

# 5. Start both frontend and backend
npm run dev
```

### One-Click Start

Instead of running each step manually, use the provided setup script:

**Windows (PowerShell):**
```powershell
.\start.ps1
```

**macOS / Linux (Bash):**
```bash
chmod +x start.sh
./start.sh
```

The script will check for required dependencies (Python 3.11+, Node 18+, Docker, uv) and **install any that are missing** (via `winget` on Windows, or `brew`/`apt`/`dnf`/`pacman` on macOS/Linux), then start Neo4j, install all project packages, and launch the app.

> **Note:** You still need to edit `.env` with your API keys before the app will work. The script copies `.env.openai.example` as a starting point if no `.env` exists.

### Required Services For This Version

Before starting the app, make sure you have all of these ready:

- local Neo4j running on `bolt://localhost:7687`
- the API keys required by the providers you chose in `.env`
- Ollama or LM Studio running if you selected local vector providers
- a completed `.env` file

Recommended models:

- `LLM_MODEL_NAME=gpt-5.4-mini`
- `ANTHROPIC_MODEL_NAME=claude-sonnet-4-6`
- `GRAPHITI_EMBEDDER_MODEL=nomic-embed-text` for Ollama
- `MIROFISH_SEARCH_PROVIDER=anthropic`
- `MIROFISH_SEARCH_MODEL=claude-sonnet-4-6`

### Local Addresses During Development

When you run `npm run dev`, the local addresses are:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:5001`
- Backend health check: `http://localhost:5001/health`
- Neo4j Browser: `http://localhost:7474`

### Docker Note

The included `docker-compose.yml` includes a Neo4j service with persistent volumes.

To start Neo4j before running the app:

```bash
docker compose up neo4j -d
```

This stores graph data in a Docker volume so it survives container restarts.

If you use Docker for the full stack:

```bash
docker compose up -d
```

### Important Note About Zep

This implementation no longer uses Zep Cloud for the graph-building pipeline.

- `ZEP_API_KEY` is not required for local Graphiti graph building
- local Neo4j is now required instead
- local vector providers are `ollama` and `lmstudio`
- built-in web search still expects real OpenAI or Anthropic APIs

## License

This repository is a modified version of the original `MiroFish` project from:

- [github.com/666ghj/MiroFish](https://github.com/666ghj/MiroFish)

This project remains licensed under the GNU Affero General Public License v3.0:

- [`LICENSE`](./LICENSE)

Fork and modification notices for this repository are documented in:

- [`NOTICE.md`](./NOTICE.md)

Practical AGPL distribution and deployment notes for this repository are documented in:

- [`AGPL-COMPLIANCE.md`](./AGPL-COMPLIANCE.md)

If you run this modified version for users over a network, the AGPL requires you to make the corresponding source code of the running version available to those users.

## Contributing

- [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- [`SECURITY.md`](./SECURITY.md)

## Contact

For private questions, collaboration, or licensing-related contact:

- `th0mg0y@proton.me`
