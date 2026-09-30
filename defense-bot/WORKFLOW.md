# Defense Lab workflow

This lab models a ticket sale. It is not a connection to a live ticketing platform. The current working path is **Sensor → Waiting Room → Seat Lock → Checkout**. On first run, the workflow configuration is `custom`, with no Login Gate or form CAPTCHA and `fifo_rate` admission. Existing demos therefore retain their route order.

The original demo still displays its client-side final CAPTCHA animation when the default `custom`/`none` settings are active. That animation is separate from the new server checked form CAPTCHA and does not grant a server pass.

## Profiles

| Profile | Route | Stored configuration |
| --- | --- | --- |
| A | Waiting Room → Login Gate → Seat Map | Login before seat |
| B | Login Gate → Waiting Room → Seat Map | Login before queue |
| C | Waiting Room → Seat Map, with random CAPTCHA | `random`, rate 0.25 |
| D | Login Gates at queue, seat and lock; random CAPTCHA; score priority | Login at all three points, rate 0.5, `priority_score` |
| custom | Operator defined | All workflow fields editable |

The profiles above are configuration presets. Login and form CAPTCHA are enforced at the configured positions. The queue uses an atomic Redis sorted waiting list: FIFO by join sequence or priority by Bot Score, with FIFO ties. Sensor challenge is separate from form CAPTCHA and continues to run at Bot Score ≥55.

## Configuration contract

`GET/POST /api/event-config` includes a nested `workflow` object. `GET/POST /api/defense-toggles` also exposes the same workflow fields at its top level for operators. Both routes write one Redis key, `defense:config:workflow`, so their values cannot drift. A POST may contain a partial workflow; a named profile expands to its preset. `custom` accepts:

| Field | Values | Default |
| --- | --- | --- |
| `WORKFLOW_PROFILE` | `A`, `B`, `C`, `D`, `custom` | `custom` |
| `REQUIRE_LOGIN_BEFORE_QUEUE` | boolean | `false` |
| `REQUIRE_LOGIN_BEFORE_SEAT` | boolean | `false` |
| `REQUIRE_LOGIN_BEFORE_LOCK` | boolean | `false` |
| `CAPTCHA_POSITION` | `queue`, `booking`, `seat`, `lock`, `checkout`, `random`, `none` | `none` |
| `CAPTCHA_RANDOM_RATE` | number from 0 to 1 | `0` |
| `QUEUE_MODE` | `off`, `fifo_rate`, `priority_score` | `fifo_rate` |

Configuration writes are validated and take effect in Redis immediately. The admin Event Config dialog can save a preset or a custom configuration. Changing queue mode clears the waiting list; previously issued tokens retain their TTL.

## Session and score semantics

- **Bot Score:** 0 is more human-like; 100 is more bot-like. Sensor challenge starts at 55. The score is currently calculated from submitted sensor signals, with higher signal count lowering the score.
- **Sensor Session:** `defense_sid` cookie or `x-session-id` identifies the sensor state. It is not an authenticated account.
- **Auth Session:** `defense_auth` is a separate HttpOnly cookie backed by Redis. Mock login accepts an email and any nonempty password; it is only a lab identity, not real authentication. The cookie is bound to the Sensor Session.
- **Queue Token / Admit Token:** Issued by `queue-service` after the admission window allows a request. The token is stored with event, IP, sensor session, issue time and optional `user_id`. Profile A binds the token on login after admission; Profile B issues it with the user ID.
- **Form CAPTCHA:** The gateway presents a server checked arithmetic challenge at `queue`, `booking`, `seat`, `lock` or `checkout`. In `random` mode, each position has one stable decision per session and event. Probability grows with Bot Score. Passes expire after five minutes. This is a mock challenge for testing gate placement, not a production solver-resistant CAPTCHA.
- **Seat Lock / Hold:** A Redis Lua operation atomically creates a temporary cart and seat hold. A periodic sweep and read path release expired holds; a failed payment releases its own hold. Repeated failed holds can temporarily block the Sensor Session and IP.

## Gate checks

| Profile | Expected first gate | After admission | Before seat lock |
| --- | --- | --- | --- |
| A | Waiting Room | `need_login`, then bind Admit Token to user | Bound token required |
| B | `need_login` before Waiting Room | Already authenticated | Bound token required |
| C | Random `need_captcha` at each configured point | May require CAPTCHA | Position pass checked in seat service |
| D | Login, then random CAPTCHA | May require CAPTCHA | Auth, bound token and CAPTCHA checked |

The gateway returns `need_login`, `need_captcha`, or `need_sensor` from queue status. Other funnel APIs return the same states with HTTP 428. Queue, seat and payment services repeat the relevant gate checks so direct calls to their published local ports cannot skip these gates. `POST /api/auth/login` accepts a mock email and nonempty password; `POST /api/captcha/verify` checks an issued challenge with at most three attempts. Reset Seats & Sessions clears Auth Sessions and CAPTCHA state.

See [ARCHITECTURE.md](ARCHITECTURE.md) for service ownership and [GLOSSARY.md](GLOSSARY.md) for terms.
