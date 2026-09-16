# Security and Repository Hygiene

This project connects to a brokerage account. Treat every API key, API secret, request token, and access token as sensitive.

## Rules for local use

- Keep `credentials.txt` on the local machine only.
- Never paste an access token into frontend code, browser storage, screenshots, issues, or commits.
- Let FastAPI handle the Kite token exchange and saved session.
- Revoke or rotate credentials immediately if they are exposed.
- Use the dashboard only from a trusted computer and network.

## Before publishing to GitHub

Run these checks from the project folder:

```powershell
git status --ignored
git diff --cached
```

Confirm the following are ignored:

- `credentials.txt`
- `.env` files
- Python virtual environments and caches
- `node_modules` and Vite build output
- Runtime logs
- Generated signal exports
- Any local session or token file

Also search the staged diff for words such as `api_secret`, `access_token`, `request_token`, and `credentials` before pushing.

If a secret is ever committed, removing it in a later commit is not sufficient. Rotate the secret and remove it from the repository history before publishing.
