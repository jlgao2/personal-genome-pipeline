# Deploying the Genome Report — Homelab

`genome_report.html` is a self-contained single-file report (all CSS inline,
no external dependencies).  It is generated from `output/health_summary.md`
and written to `output/specialist/genome_report.html`.  That directory is
gitignored — the HTML is personal data and is **never** committed.  The build
script (`build_genome_report.py`) is non-personal and is tracked.

---

## 0. Regenerate the report

```bash
python3 pipeline/report/build_genome_report.py
# → writes output/specialist/genome_report.html
```

---

## 1. Copy file to the homelab static directory

On the homelab machine, pick an unused port (example: **8902**) and a static
directory:

```bash
mkdir -p ~/srv/genome
cp output/specialist/genome_report.html ~/srv/genome/
```

The file is self-contained — no companion JSON needed.

---

## 2. Add a Caddy block

Add to your Caddyfile alongside the existing `health.jlgao.net` entries:

```caddyfile
:8902 {
    root * /home/<you>/srv/genome
    file_server
}
```

Reload Caddy:

```bash
sudo systemctl reload caddy
```

---

## 3. Add a cloudflared ingress entry

In the homelab's `cloudflared/config.yml`, add an entry alongside the existing
`health.jlgao.net` block:

```yaml
ingress:
  - hostname: health.jlgao.net
    service: http://127.0.0.1:<health-port>   # existing entry, do not change
  - hostname: genome.jlgao.net
    service: http://127.0.0.1:8902
  - service: http_status:404                  # catch-all, must be last
```

Restart the cloudflared tunnel:

```bash
sudo systemctl restart cloudflared
```

---

## 4. USER ACTIONS — cannot be automated (Cloudflare dashboard)

> Complete these steps **before** copying the real `genome_report.html`
> to the homelab.  The gate must be verified first (step 4c).

### 4a. DNS record

1. Open **Cloudflare dashboard → your domain → DNS**.
2. Add a **CNAME** record:
   - Name: `genome`
   - Target: same tunnel CNAME value as `health.jlgao.net`
   - Proxy status: **Proxied** (orange cloud)

### 4b. Cloudflare Access application

1. Open **Cloudflare Zero Trust → Access → Applications → Add an application**.
2. Choose **Self-hosted**.
3. Settings:
   - Application name: `Genome Report`
   - Application domain: `genome.jlgao.net`
4. Create a policy (same pattern as `health.jlgao.net`):
   - Policy name: `Owner only`
   - Action: **Allow**
   - Rule: **Emails** — `georgegao888@gmail.com`
5. Save.

### 4c. Verify the gate BEFORE copying the report to the homelab

```bash
curl -sI https://genome.jlgao.net/genome_report.html | head -5
# Expected: HTTP/2 302  (redirect to Cloudflare Access login)
# NOT: HTTP/2 200       (that would mean the gate is open — do not proceed)
```

Only copy `genome_report.html` to the homelab after confirming the 302.

---

## 5. Local preview (no homelab needed)

```bash
python3 pipeline/report/build_genome_report.py
cd output/specialist && python3 -m http.server 8902
```

Open <http://127.0.0.1:8902/genome_report.html> in a browser.

---

## 6. Updating the report

After re-running the pipeline and updating `output/health_summary.md`:

```bash
python3 pipeline/report/build_genome_report.py
cp output/specialist/genome_report.html ~/srv/genome/
```

No restart needed — the file is served statically.
