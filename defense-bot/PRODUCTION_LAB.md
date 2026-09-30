# Private Defense Lab deployment (Debian 13)

This deployment runs the simulated ticket buyer journey and the admin control room on one VM. It is for lab data only: login, CAPTCHA, bot scoring, payments and OTP are simulations. It does not connect to ThaiTicketMajor or process real payments. The catalog at `/events` supports multiple concurrent events; each has its own queue, seats, prices, ticket limit, sale status and sale-start time. Defense toggles and workflow profiles apply to the whole lab.

## 1. Prerequisites

Install Docker Engine and the Compose plugin using the [official Debian instructions](https://docs.docker.com/engine/install/debian/). Confirm `sudo docker compose version` works. Install Git. Keep SSH access to the VM while making network changes.

Install Tailscale on the VM and on each tester device using the [official Linux instructions](https://tailscale.com/docs/install/linux) (or the matching client for the tester's OS). Join the VM to a tailnet whose access policy permits only the lab team. Check the tailnet policy before inviting testers: the default policy can permit more members than the lab group. A public DNS name is not required. Do not use Tailscale Funnel, which publishes to the internet.

## 2. Get the application

On the VM, clone this repository or update an existing checkout:

```sh
git clone https://github.com/Depayit/Ticketing-Infrastructure-Security-Simulator.git
cd Ticketing-Infrastructure-Security-Simulator/defense-bot
```

If the repository is private, use your authorized Git credentials. Use the revision containing `docker-compose.production.yml`.

## 3. Create the admin secret

```sh
cp .env.production.example .env.production
openssl rand -hex 32
```

Put the random value in `LAB_ADMIN_PASSWORD` in `.env.production`, set the admin username as desired, then restrict the file:

```sh
chmod 600 .env.production
```

Do not commit this file or paste its contents into chat. The production gateway refuses to start without the password. The lab buyer login is intentionally a mock identity; the admin password is separate.

## 4. Start and verify

```sh
sudo docker compose --env-file .env.production -f docker-compose.defense.yml -f docker-compose.production.yml config --quiet
sudo docker compose --env-file .env.production -f docker-compose.defense.yml -f docker-compose.production.yml up -d --build
sudo docker compose --env-file .env.production -f docker-compose.defense.yml -f docker-compose.production.yml ps
curl -fsS http://127.0.0.1:8090/health
```

Only the gateway is needed by users. Compose publishes gateway, Redis and internal service ports on `127.0.0.1` only. Redis uses a persistent Docker volume with append-only persistence. Back up that volume before upgrades or resets if lab state matters. The admin reset buttons intentionally remove lab state.

On the existing `worklivebot` VM, the checkout is `/home/dannyfolderss/Ticketing-Infrastructure-Security-Simulator/defense-bot`. Its admin credentials are in `.env.production`, readable by `dannyfolderss` and root. Retrieve them locally on the VM without posting the password in chat:

```sh
cd /home/dannyfolderss/Ticketing-Infrastructure-Security-Simulator/defense-bot
cat .env.production
```

## 5. Make the site available only inside the lab network

After `sudo tailscale up` has joined the VM to the team's tailnet, run:

```sh
sudo tailscale serve --bg 8090
tailscale serve status
```

Serve displays an HTTPS `*.ts.net` URL accessible only to authorized tailnet members. The tailnet must have HTTPS certificates enabled; the first Serve command may prompt for this in the admin console. Configure Tailscale access policy to limit the VM to the lab group and avoid sharing the device outside that group. Share the Serve URL with testers. `/admin` prompts for the separate admin credentials. Keep the VM firewall closed for ports 8090–8094, 6380, 9090 and 3000; Tailscale Serve reads the gateway locally. The gateway uses Tailscale Serve's authenticated user header for per-tester queue and WAF identity. See [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve) and its [identity-header behavior](https://tailscale.com/docs/features/tailscale-serve#identity-headers).

## 6. Acceptance check

From a tester device in the tailnet, open `/events`, select an event and walk through sensor, waiting room, seat lock, checkout and mock 3DS. Open `/admin` with the admin credentials; create events, select one to edit its name, supported zone prices, ticket limit and sale status, or set its sale-start time. `paused` stops new queue entries and seat locks for that event; `sold_out` marks its sales closed. Existing seat holds can complete payment. Workflow and defense settings affect all events. Test one workflow profile at a time.

The automated `lab-smoke` profile resets seats and changes workflow settings. Run it only on a disposable lab state, not while testers are active. The mock OTP is `123456` and must never be presented as a real payment flow.

## Operations

```sh
sudo docker compose --env-file .env.production -f docker-compose.defense.yml -f docker-compose.production.yml logs --tail=100 gateway
sudo docker compose --env-file .env.production -f docker-compose.defense.yml -f docker-compose.production.yml ps
```

To update, back up Redis, pull a reviewed revision, then repeat the `up -d --build` command. To stop access through Tailscale Serve, run `sudo tailscale serve off`.
