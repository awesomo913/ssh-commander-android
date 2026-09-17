"""SSH Commander — Boss Mode Scenarios v2.

8 new scenarios covering real hacking and defense workflows.
Each cmd_key is an exact match of the "cmd" field in commands.py.
"""

NEW_BOSS_SCENARIOS = [
    # ─────────────────────────────────────────────────────────────────────────
    # 1. Pivot Through a Jump Host
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "Pivot Through a Jump Host",
        "story": (
            "ATTACKER MODE. You've popped a bastion (jump) host sitting at the "
            "edge of the network. The real prize — a database server at 10.0.0.50 "
            "— is firewalled from the internet but reachable from the bastion. "
            "You need to SSH-hop through the bastion to land a shell on the "
            "database server without leaving a noisy double-hop in the logs. "
            "Agent forwarding lets your local keys ride through the first hop so "
            "the inner host never asks for credentials you don't have."
        ),
        "steps": [
            {
                "hint": (
                    "Load your private key into the SSH agent so it can travel "
                    "with you through the hop."
                ),
                "cmd_key": "ssh-add <keyfile>",
            },
            {
                "hint": (
                    "Connect to the bastion at 192.168.1.5 WITH agent forwarding "
                    "enabled (-A). This is what lets the inner server accept your "
                    "key even though it has never seen it."
                ),
                "cmd_key": "ssh -A <user>@<host>",
            },
            {
                "hint": (
                    "Now you are on the bastion. SSH from here to the internal "
                    "database server at 10.0.0.50. Your forwarded agent handles "
                    "auth automatically."
                ),
                "cmd_key": "ssh <user>@<host>",
            },
            {
                "hint": (
                    "Verify the active SSH connections on the bastion to confirm "
                    "your pivot session shows up — and to see what else is open."
                ),
                "cmd_key": "ss -tnp | grep ssh",
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Set Up a Covert Reverse Tunnel
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "Set Up a Covert Reverse Tunnel",
        "story": (
            "ATTACKER MODE. You have a foothold on a target inside a corporate "
            "network. The firewall blocks all inbound connections from the "
            "internet, but the target can make outbound calls on port 22 — "
            "IT never restricted that. You control a VPS (your 'call-home' "
            "server) at 203.0.113.10. The plan: make the target call out to your "
            "VPS and open a reverse tunnel, so you can SSH back in from anywhere. "
            "This is one of the most common persistence techniques in real "
            "red-team engagements."
        ),
        "steps": [
            {
                "hint": (
                    "From the TARGET machine, open a reverse tunnel to your VPS. "
                    "This binds port 2222 on the VPS back to the target's SSH port "
                    "(-R 2222:localhost:22). The connection goes OUT through the "
                    "firewall, so it isn't blocked."
                ),
                "cmd_key": "ssh -R <remoteport>:<localhost>:<localport> <user>@<host>",
            },
            {
                "hint": (
                    "To make the tunnel survive session drops, use a keepalive so "
                    "the connection doesn't idle out. Reconnect to your VPS with "
                    "ServerAliveInterval set."
                ),
                "cmd_key": "ssh -o ServerAliveInterval=60 <user>@<host>",
            },
            {
                "hint": (
                    "Check active SSH connections on the target to confirm the "
                    "outbound tunnel is established and which process owns it."
                ),
                "cmd_key": "ss -tnp | grep ssh",
            },
            {
                "hint": (
                    "From your VPS, SSH to localhost:2222 to land back on the "
                    "target through the tunnel. You now have persistent access "
                    "from the internet despite the inbound firewall."
                ),
                "cmd_key": "ssh -p <port> <user>@<host>",
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Exfiltrate Data via Encrypted Channel
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "Exfiltrate Data via Encrypted Channel",
        "story": (
            "ATTACKER MODE. You found a directory of sensitive documents on the "
            "target at /home/analyst/reports/. The company runs a DLP "
            "(data loss prevention) appliance that flags large unencrypted file "
            "transfers and keywords in plain HTTP/FTP. SCP tunnels everything "
            "inside SSH — fully encrypted end-to-end — so the DLP appliance "
            "sees only an SSH stream, not the contents. Your job: pull the "
            "folder out cleanly, verify the transfer, then wipe your tracks."
        ),
        "steps": [
            {
                "hint": (
                    "Copy the entire reports/ directory from the target to your "
                    "local machine using recursive SCP (-r). Everything travels "
                    "inside the SSH encrypted channel."
                ),
                "cmd_key": "scp -r <dir> <user>@<host>:<dest>",
            },
            {
                "hint": (
                    "After the transfer, pull down just the top-level index file "
                    "separately to confirm the transfer completed without "
                    "corruption."
                ),
                "cmd_key": "scp <user>@<host>:<file> <dest>",
            },
            {
                "hint": (
                    "Use rsync to do a final delta-sync — this catches any files "
                    "that were written AFTER you started the first scp and makes "
                    "sure your local copy is complete."
                ),
                "cmd_key": "rsync -avz <user>@<host>:<src> <dest>",
            },
            {
                "hint": (
                    "Check the SSH connection log on the target to see what your "
                    "session left behind — know your footprint before you leave."
                ),
                "cmd_key": "sudo journalctl -u sshd -n 50",
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Blue Team: Hunt the Intruder
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "Blue Team: Hunt the Intruder",
        "story": (
            "DEFENDER MODE. Your SIEM (Security Information and Event Management "
            "system — the tool that watches all logs and fires alerts) just paged "
            "you at 2 AM: suspicious SSH activity on prod-web-01. Someone may "
            "be logged in right now, or they may have left already. Your job is "
            "to find them, reconstruct their timeline, check the SSH daemon logs "
            "for auth attempts, and verify whether fail2ban (the automated "
            "IP-blocking tool) caught them. Move fast — every minute they are "
            "inside is another minute of damage."
        ),
        "steps": [
            {
                "hint": (
                    "First: is anyone on the machine right now? Run the command "
                    "that shows every currently logged-in user, their terminal, "
                    "and where they connected from."
                ),
                "cmd_key": "who",
            },
            {
                "hint": (
                    "Check the recent login history. This shows every user who "
                    "logged in or out — including the IP addresses — going back "
                    "days or weeks."
                ),
                "cmd_key": "last",
            },
            {
                "hint": (
                    "Pull the last 50 lines of the SSH daemon's log. You'll see "
                    "exactly which IPs tried to authenticate, which usernames they "
                    "guessed, and whether any succeeded."
                ),
                "cmd_key": "sudo journalctl -u sshd -n 50",
            },
            {
                "hint": (
                    "Check fail2ban's status for the SSH service. This tells you "
                    "how many IPs have been auto-banned, the ban count, and "
                    "whether the attacker's IP is already blocked."
                ),
                "cmd_key": "sudo fail2ban-client status sshd",
            },
            {
                "hint": (
                    "Check active SSH connections right now — see which processes "
                    "are holding open connections and what remote IPs they point "
                    "to."
                ),
                "cmd_key": "ss -tnp | grep ssh",
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Harden a Fresh Server
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "Harden a Fresh VPS Before the Bots Find It",
        "story": (
            "DEFENDER MODE. You just spun up a fresh Ubuntu VPS at a cloud "
            "provider. It's live on a public IP with port 22 open and password "
            "authentication enabled. Automated SSH bots scan the entire internet "
            "every few hours — yours will be found within minutes. A weak or "
            "reused password is all it takes to own it. The fix: switch to "
            "key-only authentication and disable passwords entirely. Run these "
            "steps in order — if you restart sshd BEFORE your key is in place, "
            "you lock yourself out."
        ),
        "steps": [
            {
                "hint": (
                    "Generate a new ed25519 key pair. ed25519 is shorter, faster, "
                    "and more secure than the older RSA-2048. Label it with a "
                    "comment so you know which machine it came from."
                ),
                "cmd_key": "ssh-keygen -t ed25519 -C <comment>",
            },
            {
                "hint": (
                    "Copy your new public key to the server. This one command "
                    "creates ~/.ssh/authorized_keys on the remote and appends "
                    "your key. You still log in with your password this one time."
                ),
                "cmd_key": "ssh-copy-id <user>@<host>",
            },
            {
                "hint": (
                    "Print your public key and verify it landed on the server "
                    "correctly. A corrupted key copy is the #1 reason people lock "
                    "themselves out in the next step."
                ),
                "cmd_key": "cat ~/.ssh/id_ed25519.pub",
            },
            {
                "hint": (
                    "Open the SSH server config. You need to set "
                    "'PasswordAuthentication no' and 'PubkeyAuthentication yes'. "
                    "DO NOT close this editor until after you verify key login "
                    "works."
                ),
                "cmd_key": "sudo nano /etc/ssh/sshd_config",
            },
            {
                "hint": (
                    "Restart the SSH daemon so your config changes take effect. "
                    "After this, password logins are dead — only key holders get "
                    "in."
                ),
                "cmd_key": "sudo systemctl restart sshd",
            },
            {
                "hint": (
                    "Open a NEW terminal (keep your existing session open as a "
                    "safety net) and verify you can still log in using your key."
                ),
                "cmd_key": "ssh -i <keyfile> <user>@<host>",
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 6. CTF: Reach the Hidden Service
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "CTF: Reach the Hidden Service",
        "story": (
            "CTF (Capture The Flag) challenge. The flag lives on a web service "
            "running on port 8080 at 172.16.0.10 — a host deep inside a private "
            "network that is not routable from the internet. You have SSH access "
            "to a pivot host at 192.168.1.5 which CAN reach 172.16.0.10. "
            "Local port forwarding is your tool: tell SSH to listen on a local "
            "port, and every connection to that port gets tunneled through the "
            "pivot to the hidden service. From your laptop's perspective, the "
            "hidden service will appear on localhost."
        ),
        "steps": [
            {
                "hint": (
                    "Create a local port forward: bind localhost:8080 on your "
                    "machine, tunnel it through the pivot at 192.168.1.5, and "
                    "have it exit at 172.16.0.10:8080. Use -N so SSH doesn't "
                    "open a shell — just the tunnel."
                ),
                "cmd_key": "ssh -N -L <localport>:<remotehost>:<remoteport> <user>@<host>",
            },
            {
                "hint": (
                    "Run a quick command on the pivot host to verify it can reach "
                    "the target — confirm the path is clear before you chase a "
                    "dead tunnel."
                ),
                "cmd_key": "ssh <user>@<host> '<command>'",
            },
            {
                "hint": (
                    "With the tunnel running, use SCP over the forwarded port to "
                    "retrieve the flag file from the hidden service's machine."
                ),
                "cmd_key": "scp <user>@<host>:<file> <dest>",
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Deploy and Monitor a Remote Script
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "Deploy and Monitor a Remote Script",
        "story": (
            "OPS MODE. You need to push a monitoring script (monitor.py) to 10 "
            "remote servers and start it running in the background — it should "
            "keep running even after you close the SSH connection. Then you need "
            "to verify it is actually alive on each server without manually "
            "logging into every one. This is a bread-and-butter sysadmin and "
            "red-team persistence pattern: drop a script, detach it, confirm it "
            "is running."
        ),
        "steps": [
            {
                "hint": (
                    "Push monitor.py to the remote server's /tmp/ directory. "
                    "SCP copies the file over the encrypted SSH channel."
                ),
                "cmd_key": "scp <file> <user>@<host>:<dest>",
            },
            {
                "hint": (
                    "Start the script in the background using nohup. nohup "
                    "(no hang-up) tells the OS to keep the process alive even "
                    "after your SSH session ends. The & sends it to background "
                    "immediately."
                ),
                "cmd_key": "ssh <user>@<host> 'nohup <cmd> &'",
            },
            {
                "hint": (
                    "Verify the script is running: SSH in and run a one-shot "
                    "remote command to check the process list without opening "
                    "a full interactive shell."
                ),
                "cmd_key": "ssh <user>@<host> '<command>'",
            },
            {
                "hint": (
                    "Start a named tmux session on the remote so you have a "
                    "persistent workspace to monitor logs even if you disconnect "
                    "and reconnect later."
                ),
                "cmd_key": "tmux new -s <name>",
            },
            {
                "hint": (
                    "Reconnect to that tmux session from a fresh SSH login to "
                    "confirm the session and your monitoring output survived the "
                    "disconnect."
                ),
                "cmd_key": "tmux attach -t <name>",
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Fix a Broken SSH Setup
    # ─────────────────────────────────────────────────────────────────────────
    {
        "title": "Fix a Broken SSH Setup After a Migration",
        "story": (
            "TROUBLESHOOTING MODE. Your team just migrated a server to new "
            "hardware. Same IP, fresh OS install. Now SSH refuses to connect: "
            "you get a terrifying 'REMOTE HOST IDENTIFICATION HAS CHANGED' "
            "warning — your laptop's known_hosts file still has the OLD server's "
            "fingerprint and thinks this might be a man-in-the-middle attack. "
            "On top of that, the file copy that moved your home directory "
            "corrupted the permissions on ~/.ssh, and your key wasn't added to "
            "the new server. Fix it step by step — this is the exact checklist "
            "every sysadmin has memorized."
        ),
        "steps": [
            {
                "hint": (
                    "Remove the old (now wrong) host key from your known_hosts "
                    "file. SSH stored the old server's fingerprint; after a "
                    "reinstall the fingerprint changed and SSH is correctly "
                    "blocking you. This clears it so you can trust the new one."
                ),
                "cmd_key": "ssh-keygen -R <host>",
            },
            {
                "hint": (
                    "Fix the permissions on your ~/.ssh directory. SSH will "
                    "silently refuse to use keys if the directory is group- or "
                    "world-readable. 700 means only you can read/write/enter it."
                ),
                "cmd_key": "chmod 700 ~/.ssh",
            },
            {
                "hint": (
                    "Fix the permissions on your private key file. SSH won't "
                    "touch a private key that other users can read. 600 means "
                    "only you can read and write it."
                ),
                "cmd_key": "chmod 600 ~/.ssh/id_ed25519",
            },
            {
                "hint": (
                    "Copy your public key to the new server. The migration wiped "
                    "authorized_keys on the remote, so the server doesn't know "
                    "your key yet. ssh-copy-id handles this in one shot — it logs "
                    "in with your password and appends your key."
                ),
                "cmd_key": "ssh-copy-id <user>@<host>",
            },
            {
                "hint": (
                    "Test the full connection now. If everything is fixed you "
                    "should get a shell with no warnings and no password prompt."
                ),
                "cmd_key": "ssh <user>@<host>",
            },
        ],
    },
]
