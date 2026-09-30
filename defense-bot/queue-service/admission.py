"""Atomic Redis Waiting Room admission for FIFO and Bot Score priority modes."""

import hashlib
import time

from shared.config import ADMISSION_RATE, TOKEN_TTL_SEC
from shared.redis_client import r

ADMIT_BATCH = min(ADMISSION_RATE, 25)

ADMIT_SCRIPT = """
local queue, sequence, window, admitted_prefix = KEYS[1], KEYS[2], KEYS[3], KEYS[4]
local member, mode = ARGV[1], ARGV[2]
local score, rate, batch, ttl = tonumber(ARGV[3]), tonumber(ARGV[4]), tonumber(ARGV[5]), tonumber(ARGV[6])
local marker = admitted_prefix .. member
if redis.call('EXISTS', marker) == 0 then
  local previous = redis.call('ZSCORE', queue, member)
  if not previous then
    local seq = redis.call('INCR', sequence)
    local rank_score = seq
    if mode == 'priority_score' then rank_score = score * 1000000000 + seq end
    redis.call('ZADD', queue, rank_score, member)
  elseif mode == 'priority_score' then
    local seq = tonumber(previous) % 1000000000
    redis.call('ZADD', queue, score * 1000000000 + seq, member)
  end
end
local used = tonumber(redis.call('GET', window) or '0')
local slots = math.min(batch, math.max(0, rate - used))
if slots > 0 then
  local winners = {}
  local inspected = 0
  while #winners < slots and inspected < 1000 do
    local first = redis.call('ZRANGE', queue, 0, 0)
    if #first == 0 then break end
    local winner = first[1]
    redis.call('ZREM', queue, winner)
    if redis.call('EXISTS', 'defense:waiting:joined:' .. winner) == 1 then
      redis.call('SETEX', admitted_prefix .. winner, ttl, '1')
      table.insert(winners, winner)
    end
    inspected = inspected + 1
  end
  if #winners > 0 then
    redis.call('INCRBY', window, #winners)
    redis.call('EXPIRE', window, 2)
  end
end
if redis.call('EXISTS', marker) == 1 then return {1, 0} end
local rank = redis.call('ZRANK', queue, member)
return {0, rank and rank + 1 or 0}
"""


def member_id(event_id: str, session_id: str) -> str:
    return hashlib.sha256(f"{event_id}:{session_id}".encode()).hexdigest()[:32]


def admission(event_id: str, session_id: str, bot_score: int, mode: str, rate: int = ADMISSION_RATE) -> tuple[bool, int, str]:
    member = member_id(event_id, session_id)
    joined_key = f"defense:waiting:joined:{member}"
    r.set(joined_key, str(time.time()), nx=True, ex=TOKEN_TTL_SEC)
    r.expire(joined_key, TOKEN_TTL_SEC)
    event_hash = hashlib.sha256(event_id.encode()).hexdigest()[:16]
    prefix = f"defense:waiting:{event_hash}:{mode}"
    keys = [f"{prefix}:rank", f"{prefix}:sequence", f"{prefix}:window:{int(time.time())}", f"{prefix}:admitted:"]
    admitted, position = r.eval(ADMIT_SCRIPT, len(keys), *keys, member, mode, bot_score,
                                rate, min(rate, ADMIT_BATCH), TOKEN_TTL_SEC)
    return bool(admitted), int(position), member


ISSUE_SCRIPT = """
local existing = redis.call('GET', KEYS[1])
if existing then return existing end
redis.call('SETEX', KEYS[1], tonumber(ARGV[1]), ARGV[2])
redis.call('SETEX', KEYS[2], tonumber(ARGV[1]), ARGV[3])
return ARGV[2]
"""


def issue_once(event_id: str, member: str, response_json: str, token_key: str, token_meta_json: str) -> str:
    event_hash = hashlib.sha256(event_id.encode()).hexdigest()[:16]
    issued_key = f"defense:waiting:{event_hash}:issued:{member}"
    return r.eval(ISSUE_SCRIPT, 2, issued_key, token_key, TOKEN_TTL_SEC, response_json, token_meta_json)
