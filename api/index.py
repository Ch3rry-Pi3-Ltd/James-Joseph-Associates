"""
Vercel Python entrypoint for the James Joseph Associates backend.

This module is the thin adapter between Vercel's Python runtime and the real
backend application.

It gives Vercel a stable module-level Asynchronous Server Gateway Interface 
(ASGI) application called `app`, while keeping the actual application 
construction inside `backend.main`.

A simple way to think about this is imagining Vercel getting an HTTP request:

    Browser / Make.com / API client
            ->
    Vercel or local server
            ->
    ASGI interface
            ->
    FastAPI app
            ->
    your route handler

Keeping this file small makes the project easier to maintain because:

- `api.index` only deals with the deployment entrypoint concerns
- `backend.main` owns FastAPI application creation
- `backend.api.router` owns route registration
- `backend.api.v1.*` modules own individual API endpoint groups
- tests can import the same FastAPI app without depending on Vercel internals

In plain language:

- this module answers the question,

    "What should Vercel run when a request reaches the Python API?"

- it does not answer the business questions
- it does not define routes directly
- it does not talk to Supabase directly
- it does not contain LangChain or LangGraph logic

Notes
-----
- Vercel's Python runtime can serve an ASGI app exposed from an entrypoint file.
- The expected app object is imported from `backend.main`.
- All real backend logic should remain in the `backend/` package.
- This keeps deployment wiring separate from application behaviour.

Request flow
------------
A typical request should move through the project like this:

    Vercel
        -> ap.index.app
        -> backend.main.create_app()
        -> backend.api.router
        -> backend.services.<services>
        -> backend.db / backend.retrieval / backend.graphs

This file should stay boring. If it starts accumulating route handlers,
database clients, prompts, graph definitions, or business rules, that logic
probably belongs somewhere under `backend/` instead.
"""

from backend.main import app

__all__ = ["app"]