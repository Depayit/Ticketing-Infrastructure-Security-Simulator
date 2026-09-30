# Remote CLI setup

Run the Defense Lab on a Linux server with Git, Docker, and the Docker Compose plugin. Connect to that server over SSH from any computer or phone with an SSH client. The device used for SSH does not need Docker.

## Install from GitHub

```sh
git clone --filter=blob:none --sparse https://github.com/Depayit/Ticketing-Infrastructure-Security-Simulator.git
cd Ticketing-Infrastructure-Security-Simulator
git sparse-checkout set defense-bot
mkdir -p "$HOME/.local/bin"
chmod +x defense-bot/bin/defense-demo
ln -s "$(pwd)/defense-bot/bin/defense-demo" "$HOME/.local/bin/defense-demo"
```

If `~/.local/bin` is not in your `PATH`, run `export PATH="$HOME/.local/bin:$PATH"` in the current shell and add that line to your shell profile for future sessions. The checkout must be accessible to the account running the CLI. A private GitHub repository requires Git credentials on the server.

## Use

```sh
defense-demo up
defense-demo status
defense-demo health
defense-demo smoke
defense-demo loadgen
defense-demo down
```

`up` starts the gateway and its Redis, queue, seat, payment, and fraud dependencies. `loadgen` runs only against the gateway within the same Compose network. Its JSON results are saved in `defense-bot/reports/`. Use `SCENARIO_PACK=medium defense-demo loadgen` for the bounded medium scenario pack; see [SCENARIOS.md](SCENARIOS.md) for the scenario definitions.

To update the installation:

```sh
git pull --ff-only
defense-demo up
```

The gateway binds to `127.0.0.1:8090` on the server. For access through a domain, configure DNS and an HTTPS reverse proxy to this address. Restrict access to `/admin`, `/admin/api/*`, `/api/defense-toggles`, and write access to `/api/event-config` before exposing the lab to the internet: these controls have no authentication in the current application. Keep Redis and the other service ports private.
