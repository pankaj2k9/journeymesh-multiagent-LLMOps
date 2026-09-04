# JourneyMesh — hardening checklist for a public repository

Everything in this file is a **manual step**. Nothing here is applied by code,
and none of it happens by default. The workflows, the ignore rules and the
scanners cover what a repository *can* enforce on itself; this covers the rest.

The controlling fact is that **this repository is public**. Its code, its
workflow files and its Actions logs are readable by anyone. A credential that
reaches any commit is exposed the moment it is pushed, and deleting it in a
later commit does not un-expose it — it has to be rotated.

---

## Part 1 — GitHub settings you must configure by hand

### 1.1 The `production` environment

**Settings → Environments → New environment → `production`**

This is the trust boundary. The deployment secrets are scoped to it, so no
pull request and no other job can read them.

| Field | Value |
|---|---|
| Deployment branches | **Selected branches** → `main` only |
| Required reviewers | yourself, if you want every release approved |
| Wait timer | optional, 0 is fine |

**Secrets** (Environment secrets, not repository secrets):

| Name | What it is |
|---|---|
| `OVH_SSH_PRIVATE_KEY` | the private half of the dedicated deploy key, whole file including the header and footer lines |
| `OVH_KNOWN_HOSTS` | output of `ssh-keyscan`, see 2.4 |

**Variables** (same page, Variables tab — none of these is sensitive):

| Name | Example |
|---|---|
| `OVH_HOST` | `51.x.x.x` |
| `OVH_USER` | `deploy` |
| `OVH_SSH_PORT` | `22` |
| `OVH_APP_DIR` | `/opt/journeymesh` |
| `PUBLIC_URL` | `https://journeymesh.example.com` |

> Without a required reviewer, merging to `main` releases to production on its
> own. That is a deliberate choice, not an accident — decide which you want.

Optional repository variable:

| Name | Effect |
|---|---|
| `TRIVY_BLOCKING` | set to `true` to make image vulnerabilities fail CI. Leave unset until the current backlog is cleared. |

### 1.2 Branch protection on `main`

**Settings → Branches → Add branch ruleset** (or the classic protection rule),
targeting `main`:

| Setting | Value |
|---|---|
| Require a pull request before merging | **on** |
| Required approvals | 1, or 0 if you work alone |
| Dismiss stale approvals on new commits | on |
| Require status checks to pass | **on** |
| Required checks | `Quality gate` |
| Require branches to be up to date | on |
| Require conversation resolution | on |
| Block force pushes | **on** |
| Restrict deletions | **on** |
| Require signed commits | optional |
| Allow bypass | nobody, including administrators, if you can live with it |

`Quality gate` is the single job to require: it fails if the frontend, backend,
security or docker job failed, so requiring it requires all of them.

### 1.3 Repository security features

**Settings → Code security**

| Feature | Setting | Why |
|---|---|---|
| Secret scanning | **enable** | free on public repositories |
| Push protection | **enable** | blocks a recognised credential at `git push`, before it is ever public. This is the single highest-value switch on the page. |
| Dependabot alerts | enable | |
| Dependabot security updates | enable | |
| Private vulnerability reporting | enable | gives a reporter somewhere to go that is not a public issue |
| Code scanning (CodeQL) | optional | useful, but heavier than this project needs |

**Settings → Actions → General**

| Setting | Value |
|---|---|
| Actions permissions | allow actions and reusable workflows, restricted to those you select if you want to be strict |
| Fork pull request workflows | **Require approval for all external collaborators** |
| Workflow permissions | **Read repository contents permission** (the workflows here request more where they need it) |
| Allow GitHub Actions to create and approve pull requests | **off** |

### 1.4 Package (GHCR) visibility

**Your profile → Packages → `journeymesh-backend` / `journeymesh-frontend` →
Package settings**

Both packages start private. You have two defensible options.

**Option A — keep them private (recommended).** Nothing about the images is
secret, but a private package is one less thing to reason about, and it stops
anyone from pulling and running a build of your production stack.

The release workflow already handles this: it logs the VPS in to GHCR with the
job's own `GITHUB_TOKEN`, which is valid for the length of that job and is
logged out at the end. Nothing long-lived is stored.

You only need a persistent credential on the VPS if you want to `docker compose
pull` **outside** a release. If so, create a fine-grained personal access token
with **`read:packages` only**, no other scope and no repository write, and store
it on the VPS alone:

```bash
# on the VPS, as the deploy user
read -rs GHCR_TOKEN            # paste the token; -s keeps it off the screen
echo "$GHCR_TOKEN" | docker login ghcr.io -u <your-github-username> --password-stdin
unset GHCR_TOKEN
```

That writes `~/.docker/config.json` for the deploy user. Check its permissions:

```bash
chmod 600 ~/.docker/config.json
```

Never put that token in `docker-compose.prod.yml`, in git, or in a workflow.

**Option B — make them public.** Acceptable here, because the images contain
no secret: CI asserts that on every run by checking for `.env` files, private
key material and credential-shaped environment variables in both images. If you
choose this, the VPS needs no registry login at all. Re-read that CI step
before you rely on it.

Under **Package settings → Manage Actions access**, confirm this repository has
`Write` so the release workflow can push.

---

## Part 2 — VPS setup you must do by hand

### 2.1 The deploy user

`deploy/bootstrap-vps.sh` does this for you. By hand it is:

```bash
sudo adduser --disabled-password --gecos "JourneyMesh deploy" deploy
sudo usermod -aG docker deploy
sudo install -d -m 0750 -o deploy -g deploy /opt/journeymesh /opt/journeymesh/backups
sudo install -d -m 0750 -o deploy -g deploy /opt/proxy
```

`--disabled-password` means the account has no password to guess; it is
reachable only by key.

**No sudo is granted, and none is needed.** Membership of the `docker` group is
what lets `deploy` run the release, and nothing in the deployment path calls
`sudo`. Be aware that the `docker` group is effectively root on this host — that
is a property of Docker, not of this setup — which is exactly why the group has
one member and that member exists only for deployment.

### 2.2 The deploy key

A key for the workflow, separate from any human's key, so either can be revoked
without disturbing the other. No passphrase, because no human types it.

```bash
# on your laptop
ssh-keygen -t ed25519 -C "journeymesh-github-actions-deploy" \
  -f ~/.ssh/journeymesh_deploy -N ""

# install the PUBLIC half on the VPS
ssh-copy-id -i ~/.ssh/journeymesh_deploy.pub deploy@<vps-ip>

# prove it works before relying on it
ssh -i ~/.ssh/journeymesh_deploy deploy@<vps-ip> 'id -un && docker ps'
```

Then put the **private** half in the `production` environment as
`OVH_SSH_PRIVATE_KEY`:

```bash
cat ~/.ssh/journeymesh_deploy      # copy the whole thing, including both
                                   # -----BEGIN/END----- lines
```

Never commit it. `.gitignore` already excludes `id_ed25519`, `*_ed25519` and
`*.pem`, but the rule is: it goes in one place, and that place is GitHub.

### 2.3 Optional: restrict what the deploy key may do

If you want the key to be usable for deployment and nothing else, add a
`command=` restriction in front of it in
`/home/deploy/.ssh/authorized_keys`, pointing at a wrapper that only runs
`deploy.sh`. This project does **not** do that, because the release workflow
also runs `scp`, `docker compose logs` and health checks over the same
connection, and a forced command would break them. Worth knowing the option
exists if you later move all of that into `deploy.sh`.

### 2.4 The host key

This is what stops a redirected DNS record or a hijacked IP from collecting the
deploy key on first connection. Run it from a network you trust, ideally the
VPS console rather than over the internet:

```bash
# from your laptop
ssh-keyscan -p 22 <vps-ip>
```

Cross-check it against the fingerprint the VPS reports about itself:

```bash
# on the VPS
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Paste the `ssh-keyscan` output into the `OVH_KNOWN_HOSTS` environment secret.
If the VPS is ever rebuilt, its host key changes and this must be updated —
the release will fail loudly at "Configure SSH" until it is, which is the
correct behaviour.

### 2.5 Firewall

Order matters. Add the SSH rule **before** enabling a default-deny firewall, or
you will drop the session you are typing into.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    comment 'ssh'          # FIRST, always
sudo ufw allow 80/tcp    comment 'http/acme'
sudo ufw allow 443/tcp   comment 'https'
sudo ufw allow 443/udp   comment 'https http/3'
sudo ufw enable                                  # only now
sudo ufw status verbose
```

Expected result — these four and nothing else:

| Port | Why |
|---|---|
| 22/tcp | SSH |
| 80/tcp | ACME challenge and the redirect to HTTPS |
| 443/tcp | HTTPS |
| 443/udp | HTTP/3, optional |

Not open, and must never be: **5432** (PostgreSQL) and **8000** (the API).
Neither publishes a host port at all, so the firewall is a second line of
defence rather than the only one.

### 2.6 SSH hardening — the safe order

Do this **last**, after key login is confirmed, and never from a single
session. The failure mode is losing access to the machine.

```bash
# 1. session A: log in with the key and KEEP IT OPEN
ssh -i ~/.ssh/journeymesh_deploy deploy@<vps-ip>

# 2. session B: apply the hardening
ssh deploy@<vps-ip>
sudo HARDEN_SSH=1 bash /tmp/bootstrap-vps.sh

# 3. session C: prove key login still works BEFORE closing A
ssh -i ~/.ssh/journeymesh_deploy deploy@<vps-ip> 'echo still in'
```

That sets `PasswordAuthentication no`, `PermitRootLogin no` and
`KbdInteractiveAuthentication no`, and validates the configuration with
`sshd -t` before reloading. The script refuses to run if the deploy user's
`authorized_keys` is empty.

If OVHcloud gives you KVM or rescue-mode console access, know how to reach it
before you start. It is the way back from a mistake here.

### 2.7 The production environment file

```bash
ls -l /opt/journeymesh/.env
# -rw------- 1 deploy deploy ... .env
```

```bash
sudo chown deploy:deploy /opt/journeymesh/.env
sudo chmod 600 /opt/journeymesh/.env
```

Owner-only. No group, no other. It holds the database password and every
provider key, and it is the reason those values never travel through GitHub.

Nothing in the release path reads it, prints it, or rewrites it. A release
rewrites `/opt/journeymesh/.env.images`, which contains two image references
and nothing else.

---

## Part 3 — If a credential is ever exposed

A public repository means exposure is immediate and permanent. Assume any
credential that reached a commit, a log, or an issue is compromised.

**Rotate first. Clean history second. In that order** — history rewriting takes
time, and the old value is valid the whole while.

| Credential | How to rotate |
|---|---|
| `POSTGRES_PASSWORD` | generate a new one, `ALTER USER journeymesh WITH PASSWORD '…'`, update `/opt/journeymesh/.env`, `docker compose up -d` |
| `GROQ_API_KEY` | revoke and reissue in the Groq console |
| `TAVILY_API_KEY` | revoke and reissue in the Tavily dashboard |
| `AVIATIONSTACK_API_KEY` | reissue in the AviationStack dashboard |
| `OPENWEATHER_API_KEY` | reissue in the OpenWeather dashboard |
| `LANGSMITH_API_KEY` | revoke and reissue in LangSmith |
| `OVH_SSH_PRIVATE_KEY` | generate a new key pair, `ssh-copy-id` the new public half, remove the old line from `authorized_keys`, update the environment secret |
| A GHCR token | delete it in **Settings → Developer settings → Personal access tokens**, then `docker logout ghcr.io` on the VPS |

Then, only if the value actually reached a commit:

```bash
# git-filter-repo, not filter-branch
pip install git-filter-repo
git filter-repo --replace-text <(echo 'THE_LEAKED_VALUE==>REDACTED')
git push --force --all
```

Force-pushing a public repository does not recall forks, clones, or anything a
crawler already fetched. This is why rotation comes first and why the fix is
never "delete it in the next commit".

**Current status of this repository:** gitleaks scans the full history on every
CI run and reports clean. That was also confirmed by hand across all commits at
the time this file was written: no real credential has ever been committed.
Every match for a key-shaped pattern is a documented placeholder — the local
development password `journeymesh`, `your_groq_api_key` in the README, or an
explicitly fake key in a test.

One caveat worth knowing: scanners allowlist well-known documentation values,
so a clean gitleaks run is evidence, not proof. Push protection (1.3) is the
control that actually prevents the problem.
