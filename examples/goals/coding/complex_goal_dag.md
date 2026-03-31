# Workato Community Voices - MCP Server for Community Intelligence

## Complete Project Specification

### Project Overview

**workato-comm-voices** is a Model Context Protocol (MCP) server that gives AI agents
real-time access to Workato's developer community across every channel where builders
gather: Systematic, Reddit, Slack, and Discord. It aggregates posts from live and
synthetic sources, normalizes them into a unified schema, and surfaces them as MCP tools
an AI agent can reason over.

This goal is designed to produce a deeply layered task decomposition graph with
cross-cutting dependencies — ideal for exercising DAG validation before multi-agent
orchestration.

---

## Technology Stack

- **Runtime**: Node.js 20, TypeScript (strict mode)
- **MCP**: `@modelcontextprotocol/sdk` with SSE transport
- **Database**: Neon (serverless Postgres) via `postgres.js`
- **Deploy**: Fly.io (persistent SSE connections)
- **Community sources**: Reddit public API (live), Systematic (scaffolded), Slack & Discord (synthetic)
- **Testing**: Vitest for unit/integration, Playwright for MCP endpoint E2E

---

## Architecture

```
Claude Desktop / Agent
        |
        v  MCP (SSE)
workato-comm-voices (Fly.io)
        |
        |-- GET /community-posts
        |       |-- Reddit r/workato (live)
        |       |-- Systematic (scaffolded, pending auth)
        |       |-- Slack (synthetic)
        |       +-- Discord (synthetic)
        |
        |-- MCP Tools
        |       +-- get_community_posts (platform/region/type filters)
        |
        +-- Neon DB (community posts persistence)
                |-- posts
                |-- members
                +-- post_tags
```

---

## Deliverables

### 1. Database Layer (Neon / Postgres)

Create the database schema and access layer:

```sql
CREATE TABLE posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL CHECK (platform IN ('systematic','discord','slack','reddit')),
    author TEXT NOT NULL,
    region TEXT NOT NULL CHECK (region IN ('us','europe','india','japan','brazil','unknown')),
    content TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('question','feature_request','announcement')),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT NOT NULL
);

CREATE TABLE members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL,
    region TEXT NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE post_tags (
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (post_id, tag)
);

CREATE INDEX idx_posts_platform ON posts(platform);
CREATE INDEX idx_posts_region ON posts(region);
CREATE INDEX idx_posts_type ON posts(type);
CREATE INDEX idx_posts_timestamp ON posts(timestamp DESC);
```

Implement a `db.ts` module exposing typed query helpers:
- `insertPost(post: PostInput): Promise<Post>`
- `queryPosts(filters: PostFilters): Promise<Post[]>`
- `upsertMember(member: MemberInput): Promise<Member>`
- `tagPost(postId: string, tags: string[]): Promise<void>`

### 2. Community Source Adapters

Each adapter must implement a common interface:

```typescript
interface CommunityAdapter {
    platform: Platform;
    fetch(options: FetchOptions): Promise<RawPost[]>;
    normalize(raw: RawPost[]): Post[];
}
```

Build four adapters:
- **RedditAdapter** — live fetch from Reddit public JSON API (`r/workato.json`)
- **SystematicAdapter** — scaffolded stub returning empty array with TODO for OAuth
- **SlackAdapter** — synthetic data generator returning realistic mock posts
- **DiscordAdapter** — synthetic data generator returning realistic mock posts

Each adapter depends on the shared `Post` type from the database layer.

### 3. Aggregation Engine

Build a `CommunityAggregator` class that:
- Accepts all four adapters via constructor injection
- Fetches from all sources concurrently (`Promise.allSettled`)
- Normalizes and deduplicates results
- Persists new posts to Neon via the db layer
- Returns the unified, filtered result set

The aggregator depends on all four adapters AND the database layer.

### 4. MCP Server with SSE Transport

Implement the MCP server using `@modelcontextprotocol/sdk`:

```typescript
const server = new Server({ name: "workato-community", version: "1.0.0" }, {
    capabilities: { tools: {} }
});

server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [{
        name: "get_community_posts",
        description: "Fetch recent posts across all community channels",
        inputSchema: {
            type: "object",
            properties: {
                platform: { type: "string", enum: ["systematic","discord","slack","reddit","all"] },
                region: { type: "string", enum: ["us","europe","india","japan","brazil","all"] },
                type: { type: "string", enum: ["question","feature_request","announcement","all"] },
                limit: { type: "integer", minimum: 1, maximum: 50, default: 10 }
            }
        }
    }]
}));
```

The MCP tool handler calls the aggregation engine.

### 5. SSE Transport & HTTP Layer

Create an Express server exposing:
- `GET /health` — health check returning `{ status: "ok" }`
- `GET /sse` — SSE endpoint for MCP client connections
- `GET /community-posts` — REST fallback endpoint (calls aggregator directly)
- Auth middleware validating `Authorization: Bearer <token>` from env

The HTTP layer depends on the MCP server and aggregator.

### 6. Unified Type System

Define and export all shared types in a `types.ts` module:

```typescript
type Platform = "systematic" | "discord" | "slack" | "reddit";
type Region = "us" | "europe" | "india" | "japan" | "brazil" | "unknown";
type PostType = "question" | "feature_request" | "announcement";

interface Post {
    id: string;
    platform: Platform;
    author: string;
    region: Region;
    content: string;
    type: PostType;
    timestamp: string;
    source: string;
}

interface PostFilters {
    platform?: Platform | "all";
    region?: Region | "all";
    type?: PostType | "all";
    limit?: number;
}

interface FetchOptions {
    limit?: number;
    since?: Date;
}
```

Every other module imports from this one — it has no dependencies itself but is
depended on by everything else. This creates a hub node in the DAG.

### 7. Configuration & Environment

Create a `config.ts` module that:
- Loads env vars (`DATABASE_URL`, `WORKATO_API_TOKEN`, `COMM_VOICES_API_TOKEN`, `PORT`)
- Validates all required vars are present at startup
- Exports a typed `Config` object

The config module depends only on the type system and is depended on by the
database layer, adapters, and HTTP layer.

### 8. Testing Suite

Write tests covering:
- **Unit tests** for each adapter's `normalize()` method
- **Unit tests** for the aggregator's dedup and filter logic
- **Integration tests** for DB query helpers against a test database
- **E2E test** hitting `/community-posts` and verifying the response schema

Tests depend on every module they cover — creating many leaf-node edges in the DAG.

### 9. Deployment Configuration

Create:
- `fly.toml` — Fly.io deployment config (Node 20, port 3000, health check)
- `Dockerfile` — multi-stage build (install, build, runtime)
- `.env.example` — template with all required env vars documented
- `tsconfig.json` — strict TypeScript config

Deployment config depends on the HTTP layer being complete.

---

## Dependency Graph (Expected DAG Structure)

This goal is specifically designed to produce a task decomposition with rich
dependency structure for DAG validation testing:

```
types.ts (hub — no deps, everything depends on it)
    |
    +-- config.ts (depends on types)
    |       |
    |       +-- db.ts (depends on types, config)
    |       |       |
    |       |       +-- RedditAdapter (depends on types, db)
    |       |       +-- SystematicAdapter (depends on types, db)
    |       |       +-- SlackAdapter (depends on types, db)
    |       |       +-- DiscordAdapter (depends on types, db)
    |       |               |
    |       |               +-- CommunityAggregator (depends on all adapters + db)
    |       |                       |
    |       |                       +-- MCP Server (depends on aggregator)
    |       |                               |
    |       +-------------------------------+-- HTTP/SSE Layer (depends on MCP + config)
    |                                               |
    |                                               +-- Deployment (depends on HTTP)
    |
    +-- Tests (depend on adapters, aggregator, db, HTTP)
```

Key DAG properties this exercises:
- **Hub node**: `types.ts` is depended on by 8+ tasks
- **Diamond dependencies**: multiple paths converge at the aggregator
- **Fan-out**: 4 parallel adapter tasks from the db layer
- **Fan-in**: aggregator collects all 4 adapters
- **Linear chain**: MCP -> HTTP -> Deployment
- **Wide leaf layer**: test tasks reference many upstream nodes

---

## Success Criteria

- All TypeScript files compile with `tsc --strict` and zero errors
- `GET /health` returns 200 with `{ status: "ok" }`
- `GET /community-posts` returns valid JSON matching the `Post[]` schema
- MCP tool `get_community_posts` is discoverable via the SSE endpoint
- All unit and integration tests pass
- Reddit adapter fetches live data from `r/workato`
- Synthetic adapters return realistic, schema-compliant mock data
- Database migrations run cleanly against a fresh Neon instance
- Docker image builds successfully with multi-stage Dockerfile
- Fly.io config is valid and deployable

---

## Why This Goal Tests DAG Validation

Unlike the simple calculator goal (flat, no dependencies) or the PawShare goal
(deep but mostly linear), this goal produces a **wide diamond DAG** with:

1. A shared root node everything depends on (types)
2. Multiple parallel workstreams (4 adapters)
3. A convergence point (aggregator)
4. Cross-cutting concerns (config is needed at multiple depths)
5. A leaf layer with many inbound edges (tests)

This structure is the most likely to surface cycle detection bugs, missing-dependency
errors, and topological sort edge cases in the DAG validator.
