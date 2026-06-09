# Deploying the Carrier Screening Report — Homelab

This page (`report.html`) is a self-contained single-file app that fetches
`couple_report.json` from the same directory.  The JSON file is personal data
and is gitignored — it is **never** committed.  Copy both files together to
the homelab static directory, serve them behind Caddy + Cloudflare Access,
and the page is accessible only to you.

---

## 1. Copy files to the homelab static directory

On the homelab machine, pick an unused port (example: **8899**) and a static
directory:

```bash
mkdir -p ~/srv/carrier
cp output/carrier/couple_report.json ~/srv/carrier/
cp pipeline/carrier/report.html       ~/srv/carrier/
```

`report.html` must sit **next to** `couple_report.json` — the page fetches
`./couple_report.json` at the same path.

---

## 2. Add a Caddy block (or an ad-hoc server)

### Option A — Caddy reverse-proxy (recommended if Caddy already manages your
homelab sites)

Add to your Caddyfile:

```caddyfile
:8899 {
    root * /home/<you>/srv/carrier
    file_server
}
```

Reload Caddy: `sudo systemctl reload caddy`

### Option B — Quick one-liner (no Caddy needed)

```bash
cd ~/srv/carrier && python3 -m http.server 8899
```

Run this in a tmux/screen session or as a systemd unit.

---

## 3. Add a cloudflared ingress entry

In the homelab's `cloudflared/config.yml`, add an entry alongside the existing
`health.jlgao.net` block:

```yaml
ingress:
  - hostname: health.jlgao.net
    service: http://127.0.0.1:<health-port>   # existing entry, do not change
  - hostname: carrier.jlgao.net
    service: http://127.0.0.1:8899
  - service: http_status:404                  # catch-all, must be last
```

Restart the cloudflared tunnel:

```bash
sudo systemctl restart cloudflared
```

---

## 4. USER ACTIONS — cannot be automated (Cloudflare dashboard)

> These steps require your Cloudflare dashboard login.  Complete them
> **before** copying any real `couple_report.json` to the homelab.

### 4a. DNS record

1. Open **Cloudflare dashboard → your domain → DNS**.
2. Add an **A** (or **CNAME**) record:
   - Name: `carrier`
   - Target: your tunnel's catchall / CNAME value (same as `health.jlgao.net`)
   - Proxy status: **Proxied** (orange cloud)

### 4b. Cloudflare Access application

1. Open **Cloudflare Zero Trust → Access → Applications → Add an application**.
2. Choose **Self-hosted**.
3. Settings:
   - Application name: `Carrier Report`
   - Application domain: `carrier.jlgao.net`
4. Create a policy (same pattern as `health.jlgao.net`):
   - Policy name: `Owner only`
   - Action: **Allow**
   - Rule: **Emails** — `georgegao888@gmail.com`
5. Save.

### 4c. Verify the gate BEFORE putting real data behind it

```bash
curl -sI https://carrier.jlgao.net/couple_report.json | head -5
# Expected: HTTP/2 302  (redirect to Cloudflare Access login)
# NOT: HTTP/2 200       (that would mean the gate is open)
```

Only copy `couple_report.json` to the homelab after confirming the 302.

---

## 5. Local preview (no homelab needed)

```bash
cp pipeline/carrier/report.html output/carrier/
cd output/carrier && python3 -m http.server 8899
```

Open <http://127.0.0.1:8899/report.html> in a browser.

Clean up after previewing:

```bash
rm output/carrier/report.html
```

(`pipeline/carrier/report.html` is the canonical copy.)

---

## 6. Updating the report

After re-running the carrier screening pipeline:

```bash
cp output/carrier/couple_report.json ~/srv/carrier/
```

No restart needed — the page fetches the JSON fresh on every load.
