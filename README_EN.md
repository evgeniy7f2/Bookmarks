# Bookmarks 🔖

**Bookmarks** is a small personal bookmark manager that runs on your own
server (Ubuntu Server, systemd). Keep links in groups, mark favorites,
search by tags and open sites in one click. All data lives in a single
SQLite database on your server — no external services, no subscriptions,
no third-party clouds.

## Features

- **Groups, tags and favorites** — any organization of your links
- **Instant search** — by name, description and tags
- **Multiple users** — personal accounts with individual quotas
- **Admin panel** — user management, quotas, account locking
- **PWA** — the UI can be "installed" as an app on your phone or computer
- **Light and dark themes**, interface in Russian and English
- **Auto-updates** — right from the "About" section
- **Online database backups** with rotation of old copies

Requirements: Ubuntu Server 22.04/24.04, Python 3.10+
(if Python is missing, the install script installs it for you).

## Installation

1. Get the `ubuntu_sp` folder onto the server (e.g. into your home
   directory):

   ```bash
   cd ~
   git clone https://github.com/evgeniy7f2/Bookmarks.git
   ```

   or download the archive from GitHub. Make sure you are in the folder
   that contains `install.sh`, `app.py` and `bookmarks/`.

2. Run the installer:

   ```bash
   cd <folder with install.sh>
   sudo bash install.sh
   ```

3. Answer three questions (Enter — accept the default in brackets):

   | Question | Default | Meaning |
   |---|---|---|
   | Install directory | `/opt/bookmarks` | where the program files and data live |
   | Port | `8765` | TCP port for HTTP |
   | Access | `external` | `internal` — from the server itself only (127.0.0.1); `external` — from the network (0.0.0.0) |

4. The script installs the dependencies, copies the files, creates the
   systemd service `bookmarks` (auto-start on boot, auto-restart on
   failure), verifies the server start and prints the address.

5. Open the address in a browser and register: **the first registered
   user automatically becomes the administrator** (gets the admin panel).

### Non-interactive install

```bash
INSTALL_DIR=/opt/bookmarks PORT=8765 BIND=external sudo bash install.sh
```

`BIND`: `external` (0.0.0.0) or `internal` (127.0.0.1).

### Access with an internal address (internal)

If `internal` is chosen, the app is reachable from the server itself only.
From your PC the easiest way is an SSH tunnel:

```bash
ssh -L 8765:localhost:8765 <user>@<server-address>
```

then open `http://127.0.0.1:8765` in a local browser.

## Updates

- **Check**: the **"About" → "Check for updates"** section.
  When a new version appears, a scrolling notification in the status bar
  reminds you as well (visible to administrators).
- **Update**: the **"Update"** button — the service is stopped for a few
  seconds, the files are replaced (**data is untouched**), the service is
  restarted. The page reloads by itself.

New versions are published in the `update/` folder on GitHub
(an archive named `update_vX_Y_Z.tar`, e.g. `update_v1_4_2.tar`).
For offline updates you can drop such an archive into the local
`update/` folder next to the installation — it is found without internet.

## Backups

- **Manually**: `sudo /opt/bookmarks/backup.sh` — a consistent database
  copy appears in `data/backups/` (the last 7 copies are kept, older
  ones are removed; `KEEP=14 ./backup.sh` — change the count).
- **Automatically** (daily at 03:00):

  ```bash
  sudo crontab -e
  0 3 * * * /opt/bookmarks/backup.sh >> /var/log/bookmarks-backup.log 2>&1
  ```

- **Restore**: `sudo systemctl stop bookmarks` → replace
  `data/bookmarks.db` with a backup file → `sudo systemctl start bookmarks`.

## Useful commands

| Task | Command |
|---|---|
| Service status | `systemctl status bookmarks` |
| Live logs | `journalctl -u bookmarks -f` |
| Restart | `sudo systemctl restart bookmarks` |
| List users | `sudo /opt/bookmarks/.venv/bin/python /opt/bookmarks/manage.py list-users` |
| Reset a password | `sudo /opt/bookmarks/.venv/bin/python /opt/bookmarks/manage.py reset-password <user>` (the new password is printed) |
| Block / unblock a user | `… manage.py lock-user <user>` / `… manage.py unlock-user <user>` |
| Make an admin | `… manage.py make-admin <user>` |

## Changing the port or the bind address

1. `sudo nano /etc/systemd/system/bookmarks.service` — change `--host`
   and `--port` in the `ExecStart` line;
2. update the port in the `install.json` file in the install directory
   (the auto-updater checks the server on exactly this port after an
   update);
3. `sudo systemctl daemon-reload && sudo systemctl restart bookmarks`.

If you change the port for external access, do not forget the firewall
rule: `sudo ufw allow <port>/tcp`.

## Uninstall

```bash
sudo systemctl disable --now bookmarks
sudo rm /etc/systemd/system/bookmarks.service
sudo rm /etc/polkit-1/rules.d/90-bookmarks.rules
sudo rm -rf /opt/bookmarks    # including the data (data/)
sudo userdel bookmarks
sudo systemctl daemon-reload
```
