# Remote access: laptop to desktop

Drive the desktop's Herdr (and its agents) from the laptop over SSH. Agents,
processes and files stay on the desktop. The laptop only sends keystrokes and
draws the screen. It does **not** move a session that is already running on the
laptop.

Desktop = Windows 11, local account `Nassim`, LAN IP `192.168.2.128`.
Laptop = Windows. Both on the same network.

## 1. SSH server on the desktop (elevated PowerShell)

OpenSSH Server ships with Windows but is disabled.

```powershell
Set-Service sshd -StartupType Automatic
Start-Service sshd
Get-NetConnectionProfile   # NetworkCategory must be Private (the firewall rule is Private-only)
```

## 2. Key login (no password)

The PIN is not the account password and SSH cannot use it. Use a key.

On the laptop: `ssh-keygen -t ed25519`, then print `~\.ssh\id_ed25519.pub`.

On the desktop (elevated). The account is an administrator, so the key goes in
`administrators_authorized_keys`, not `~\.ssh\authorized_keys`, and the file
must have these permissions or sshd ignores it:

```powershell
$f = "$env:ProgramData\ssh\administrators_authorized_keys"
Set-Content -Path $f -Encoding ascii -Value '<the ssh-ed25519 line>'
icacls $f /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
```

Test from the laptop: `ssh Nassim@192.168.2.128`.

Optional hardening: set `PasswordAuthentication no` in
`C:\ProgramData\ssh\sshd_config`, run `sshd.exe -t`, then `Restart-Service sshd`.
Keep a working session open while you test.

## 3. Add the machine in Herdr (on the laptop)

Herdr runs `ssh` without prompts, so a key with a passphrase must be loaded in
the agent first (elevated PowerShell, once):

```powershell
Set-Service ssh-agent -StartupType Automatic
Start-Service ssh-agent
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

Then:

```
hc machine add desktop
```

(or "Add machine" in the app). Accept the offer to install Herdr on the desktop.
The flag is `--name`, not `--label`.

A terminal inside Herdr runs on the **desktop**, even while you type on the
laptop. To run something on the laptop itself, use a plain terminal outside
Herdr, or switch Herdr back to Local.

## 4. `~/.ssh/config` on the laptop

```
Host desktop
    HostName 192.168.2.128
    User Nassim
    AddKeysToAgent yes
    LocalForward 4387 127.0.0.1:4387
```

`AddKeysToAgent` stops the passphrase prompt after reboots. `LocalForward` is
the Lavish tunnel (next section).

## 5. Lavish pages from the laptop

Lavish serves pages from a local web server on the desktop and opens the
desktop's browser. Facts that make this simple:

- Port is fixed: `4387` (override: `LAVISH_AXI_PORT`; leave it alone).
- All agents on the desktop share one server on that port. Only the
  `/session/<id>` path differs per page, and the agent prints it.
- It listens on `127.0.0.1` only, so the laptop needs a tunnel.
- Requests under any other hostname (the LAN IP) get `403 forbidden host`.
  Always browse `http://127.0.0.1:4387/...` on the laptop.

To view a page: in a terminal on the laptop (not in Herdr), run

```
ssh -N desktop
```

and leave it open, then open the session URL the agent gave you in the laptop's
browser. Annotations and "Send to Agent" travel back over the same tunnel.
Port taken on the laptop? Use a different local port:
`ssh -N -L 5000:127.0.0.1:4387 Nassim@192.168.2.128`.

Alternative, untested: Tailscale on both machines makes Lavish also listen on
the desktop's Tailscale address and print a MagicDNS link, so no tunnel. The
Lavish server is unauthenticated and can serve local files, so only do this on
a tailnet you alone use.

## Not verified

- Re-adding the machine as `hc machine add desktop` so Herdr opens the
  `LocalForward` itself. Use `ssh -N desktop` meanwhile.
- Anything off the home network (VPN, Nord "local network access", Tailscale).
- Windows server support in Herdr is documented as rough in places.
