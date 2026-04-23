import json
import unittest

from app.core.dead_letter_queue import DeadLetterQueue
from app.core.delivery_trace import DeliveryTraceView
from app.core.message_bus import MessageBus, MessageType
from app.core.message_replay import MessageReplay
from app.core.message_sweeper import MessageSweeper


class _FakePipeline:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.results = []

    def xadd(self, key, data, maxlen=None):
        entry_id = f"{len(self.redis.streams.setdefault(key, [])) + 1}-0"
        self.redis.streams.setdefault(key, []).append((entry_id, data))
        self.results.append(entry_id)
        return self

    def zadd(self, key, mapping):
        self.redis.zsets.setdefault(key, []).append(mapping)
        self.results.append(True)
        return self

    def zremrangebyrank(self, key, start, end):
        self.results.append(True)
        return self

    def publish(self, channel, message):
        self.redis.published.append((channel, message))
        self.results.append(True)
        return self

    def execute(self):
        return list(self.results)


class _FakeRedis:
    def __init__(self):
        self.kv = {}
        self.streams = {}
        self.zsets = {}
        self.hashes = {}
        self.lists = {}
        self.published = []
        self.groups = set()
        self.acked = []
        self.autoclaimed = []

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True

    def pipeline(self):
        return _FakePipeline(self)

    def keys(self, pattern):
        if pattern == "mb:stream:*":
            return list(self.streams.keys())
        return []

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value
        return 1

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)
        return 1

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        if end == -1:
            return values[start:]
        return values[start:end + 1]

    def xlen(self, key):
        return len(self.streams.get(key, []))

    def xgroup_create(self, stream, group, id="0", mkstream=True):
        self.groups.add((stream, group))
        return True

    def xreadgroup(self, groupname, consumername, streams, count=None, block=None):
        stream_key = next(iter(streams.keys()))
        entries = self.streams.get(stream_key, [])[:count or len(self.streams.get(stream_key, []))]
        return [(stream_key, entries)] if entries else []

    def xack(self, stream, group, entry_id):
        self.acked.append((stream, group, entry_id))
        return 1

    def xautoclaim(self, stream, group, consumer, min_idle_time, start_id, count=1):
        self.autoclaimed.append((stream, group, consumer, min_idle_time, start_id, count))
        return start_id, [], []

    def zcard(self, key):
        return len(self.zsets.get(key, []))


class MessageReliabilityTests(unittest.TestCase):
    def test_consumer_group_read_path_assigns_stream_entry_and_consumer(self):
        bus = MessageBus(redis_client=_FakeRedis())
        bus.publish("planner_agent", "bp_agent", MessageType.QUERY, {"q": 1}, conversation="conv-1")

        messages = bus.get_messages(receiver="bp_agent", consumer="bp_agent", max_count=1, use_consumer_groups=True)

        self.assertEqual(len(messages), 1)
        pending = bus.get_pending("bp_agent")
        self.assertEqual(pending[0]["consumer"], "bp_agent")
        self.assertTrue(pending[0]["stream_entry_id"])

    def test_ack_removes_pending_and_records_trace(self):
        bus = MessageBus(redis_client=_FakeRedis())
        msg = bus.publish("planner_agent", "bp_agent", MessageType.QUERY, {"q": 1}, conversation="conv-1")
        bus.get_messages(receiver="bp_agent", consumer="bp_agent", max_count=1, use_consumer_groups=True)
        self.assertEqual(len(bus.get_pending("bp_agent")), 1)

        acked = bus.ack_message("bp_agent", msg.delivery_id)

        self.assertTrue(acked)
        self.assertEqual(len(bus.get_pending("bp_agent")), 0)
        self.assertEqual(len(bus._redis.acked), 1)
        trace = DeliveryTraceView(bus).fetch(msg.delivery_id)
        self.assertEqual(trace["last_event"], "acknowledged")

    def test_nack_moves_message_to_dead_letter(self):
        bus = MessageBus(redis_client=_FakeRedis())
        msg = bus.publish("planner_agent", "bp_agent", MessageType.QUERY, {"q": 1}, conversation="conv-1")

        nacked = bus.nack_message("bp_agent", msg.delivery_id, reason="handler failed", requeue=False)

        self.assertTrue(nacked)
        dead_letters = DeadLetterQueue(bus).get_dead_letters("bp_agent")
        self.assertEqual(len(dead_letters), 1)
        self.assertEqual(dead_letters[0]["reason"], "handler failed")

    def test_replay_and_sweeper_can_reclaim_stale_pending(self):
        bus = MessageBus(redis_client=_FakeRedis())
        msg = bus.publish("planner_agent", "bp_agent", MessageType.QUERY, {"q": 1}, conversation="conv-1")

        pending_key = next(iter(bus._redis.hashes))
        payload = json.loads(bus._redis.hashes[pending_key][msg.delivery_id])
        payload["pending_since"] = 0
        bus._redis.hashes[pending_key][msg.delivery_id] = json.dumps(payload)

        sweep = MessageSweeper(bus).sweep_agent("bp_agent", max_idle_seconds=1)
        reclaimed = MessageReplay(bus).replay_pending("bp_agent", min_idle_seconds=1)

        self.assertGreaterEqual(sweep["reclaimed"], 1)
        self.assertEqual(len(reclaimed), 0)
        self.assertEqual(len(bus._redis.autoclaimed), 1)


if __name__ == "__main__":
    unittest.main()
