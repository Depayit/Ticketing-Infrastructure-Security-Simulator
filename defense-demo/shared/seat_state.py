"""Atomic seat hold lifecycle shared by booking and payment services."""

import json
import time

from shared.redis_client import r


def seat_key(event_id, seat_id):
    return f"defense:seat:{event_id}:{seat_id}"


def cart_key(cart_id):
    return f"defense:cart:{cart_id}"


CLEANUP_LUA = """
local function record_abuse(state)
  for _, pair in ipairs({{'session:', state.session_id or ''}, {'ip:', state.ip or ''}}) do
    if pair[2] ~= '' and pair[2] ~= 'sim_bot' then
      local key = 'defense:abuse:' .. pair[1] .. pair[2]
      local count = redis.call('INCR', key)
      redis.call('EXPIRE', key, 3600)
      if count >= 3 then redis.call('SETEX', 'defense:ban:hold:' .. pair[1] .. pair[2], 600, '1') end
    end
  end
end
local function cleanup(raw, seat_key, now)
  if not raw then return {status='available', session_id='', cart_id=''} end
  local state = cjson.decode(raw)
  if state.status == 'locked' and (not state.cart_id or redis.call('EXISTS', 'defense:cart:' .. state.cart_id) == 0 or tonumber(state.expires_at or 0) <= now) then
    record_abuse(state)
    redis.call('INCR', 'defense:metric:hold_expired_total')
    state = {status='available', session_id='', cart_id=''}
    redis.call('SET', seat_key, cjson.encode(state))
  end
  return state
end
"""

READ_SCRIPT = CLEANUP_LUA + """
return cjson.encode(cleanup(redis.call('GET', KEYS[1]), KEYS[1], tonumber(ARGV[1])))
"""

LOCK_SCRIPT = CLEANUP_LUA + """
local state = cleanup(redis.call('GET', KEYS[1]), KEYS[1], tonumber(ARGV[1]))
if state.status ~= 'available' then return 'unavailable' end
if redis.call('EXISTS', 'defense:ban:hold:session:' .. ARGV[2]) == 1 or redis.call('EXISTS', 'defense:ban:hold:ip:' .. ARGV[3]) == 1 then
  return 'abuse_blocked'
end
redis.call('SET', KEYS[1], ARGV[4])
redis.call('SETEX', KEYS[2], tonumber(ARGV[5]), ARGV[6])
return 'locked'
"""

RELEASE_SCRIPT = CLEANUP_LUA + """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local state = cjson.decode(raw)
if state.status ~= 'locked' or state.cart_id ~= ARGV[1] then return 0 end
if ARGV[2] == '1' then record_abuse(state) end
redis.call('SET', KEYS[1], cjson.encode({status='available', session_id='', cart_id=''}))
redis.call('DEL', KEYS[2])
return 1
"""

COMMIT_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw or redis.call('EXISTS', KEYS[2]) == 0 then return 0 end
local state = cjson.decode(raw)
if state.status ~= 'locked' or state.cart_id ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2])
redis.call('DEL', KEYS[2])
redis.call('LPUSH', KEYS[3], ARGV[3])
return 1
"""


def read_seat(event_id, seat_id):
    return json.loads(r.eval(READ_SCRIPT, 1, seat_key(event_id, seat_id), time.time()))


def lock_hold(event_id, seat_id, cart_id, session_id, ip, cart, ttl):
    now = time.time()
    state = {"status": "locked", "session_id": session_id, "ip": ip, "cart_id": cart_id,
             "expires_at": now + ttl}
    return r.eval(LOCK_SCRIPT, 2, seat_key(event_id, seat_id), cart_key(cart_id), now,
                  session_id, ip, json.dumps(state), ttl, json.dumps(cart))


def release_hold(event_id, seat_id, cart_id, count_abuse=False):
    return bool(r.eval(RELEASE_SCRIPT, 2, seat_key(event_id, seat_id), cart_key(cart_id),
                       cart_id, "1" if count_abuse else "0"))


def commit_hold(event_id, seat_id, cart_id, order):
    sold = {"status": "sold", "session_id": order.get("session_id", ""), "cart_id": "",
            "order_id": order["order_id"]}
    committed = bool(r.eval(COMMIT_SCRIPT, 3, seat_key(event_id, seat_id), cart_key(cart_id),
                            "defense:orders", cart_id, json.dumps(sold), json.dumps(order)))
    if committed:
        session_id = order.get("session_id", "")
        if session_id:
            r.delete(f"defense:abuse:session:{session_id}")
    return committed
