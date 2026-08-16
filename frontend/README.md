# Frontend Studio

CortexExtract web studio — Next.js 14 (App Router), TypeScript (strict), Tailwind CSS, Zustand, Monaco Editor, Framer Motion.

## Run

```bash
npm install
npm run dev        # http://localhost:3000
```

## Checks

```bash
npx tsc --noEmit
npm run lint
npm run build
```

The studio talks to the FastAPI backend on `http://localhost:8000`. See the [root README](../README.md) for the full setup, API, and security model.