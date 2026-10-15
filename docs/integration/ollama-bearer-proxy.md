# Local Ollama Bearer proxy

Use this operator-run bridge only when a remote OrganizationAI service must reach
the approved local Ollama runtime for a synthetic test. Ollama itself has no
Bearer authentication, so never point a public tunnel directly at port `11434`.

## Boundary and limits

- The proxy binds only to `127.0.0.1:11435` and forwards only to
  `127.0.0.1:11434`.
- It checks one Bearer credential before forwarding any request. It allows only
  `GET /api/tags`, `GET /v1/models`, and `POST /v1/chat/completions`; Ollama
  receives no Bearer header.
- The JSON body cap is 32 MiB, the response cap is 1 MiB, at most two upstream
  requests and eight client connections are active, request bodies time out
  after 30 seconds, and an upstream operation has a 55 second deadline.
- Logs contain only a fixed route label, method, status, duration, and sanitized
  error type. They must never include the credential, request body, or model
  output.

## Start and configure

1. Generate a cryptographically random token of at least 64 ASCII characters.
   Keep the local copy in a machine-protected secret store; this workstation
   uses a DPAPI-protected ignored file. Never put the token in a command line,
   source file, ordinary `.env` file, terminal output, or log.
2. Start `scripts/local_ollama_bearer_proxy.py` with the token injected through
   the process environment as `OLLAMA_PROXY_BEARER_TOKEN`.
3. Start the tunnel with its origin restricted to the proxy and an exact Host
   rewrite:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:11435 --http-host-header 127.0.0.1:11435
   ```

   Never change the origin to port `11434`, bind the proxy to a non-loopback
   interface, add wildcard routes, or disable Bearer validation.
4. Set the three Render API key secrets to the same generated value:
   `LOCAL_VLM_API_KEY`, `AUTH_WORKFLOW_MEDIA_API_KEY`, and
   `AUTH_WORKFLOW_STRATEGY_API_KEY`. Set their corresponding base URLs to the
   current tunnel hostname plus `/v1`. Keep the model IDs and SHA-256 pins in
   sync with the observed Ollama metadata; do not copy a local pin over a
   production pin without checking the runtime digest.
5. Quick Tunnels are temporary. If the hostname changes, update all three
   endpoint variables together and redeploy the environment. When the proxy or
   tunnel is unavailable, evaluation must follow the existing Checker fallback.

## Verify

With `OLLAMA_PROXY_BEARER_TOKEN` injected from the protected local store, run
the verifier against the loopback origin and the current tunnel:

```powershell
python scripts/verify_ollama_bearer_proxy.py --base-url http://127.0.0.1:11435
python scripts/verify_ollama_bearer_proxy.py --base-url https://<current-quick-tunnel-host>
```

It checks missing and wrong credentials, blocked methods and paths, both model
metadata routes, the pinned VLM digest, and real inference with a generated
one-pixel synthetic image. This proves the proxy/tunnel and local runtime only;
it does not prove that the Render backend completed an authenticated workflow.
Use a clearly labeled synthetic plan through the authenticated application for
that end-to-end check.
