import unittest

from app.core.message_bus import MessageBus, MessageType
from app.core.message_delivery import build_delivery_envelope, derive_idempotency_key
from app.core.message_types import DeliveryState


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

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True

    def pipeline(self):
        return _FakePipeline(self)

    def keys(self, pattern):
        return []

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value
        return 1

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])


class MessageDeliveryFoundationTests(unittest.TestCase):
    def test_delivery_envelope_builds_idempotent_metadata(self):
        envelope = build_delivery_envelope(
            sender="planner_agent",
            receiver="bp_agent",
            msg_type="QUERY",
            content={"question": "vendor name"},
            conversation="conv-1",
            reply_to=None,
        )
        self.assertTrue(envelope.delivery_id)
        self.assertTrue(envelope.idempotency_key)
        self.assertGreater(envelope.sequence_no, 0)
        self.assertEqual(envelope.delivery_state, DeliveryState.PENDING.value)

    def test_same_message_shape_derives_same_idempotency_key(self):
        one = derive_idempotency_key("a", "b", "QUERY", {"x": 1}, "conv-1")
        two = derive_idempotency_key("a", "b", "QUERY", {"x": 1}, "conv-1")
        self.assertEqual(one, two)

    def test_message_bus_suppresses_duplicate_delivery(self):
        bus = MessageBus(redis_client=_FakeRedis())
        first = bus.publish(
            sender="planner_agent",
            receiver="bp_agent",
            msg_type=MessageType.QUERY,
            content={"question": "vendor name"},
            conversation="conv-1",
        )
        second = bus.publish(
            sender="planner_agent",
            receiver="bp_agent",
            msg_type=MessageType.QUERY,
            content={"question": "vendor name"},
            conversation="conv-1",
        )
        self.assertEqual(first.delivery_state, DeliveryState.PENDING.value)
        self.assertEqual(second.delivery_state, DeliveryState.DUPLICATE.value)
        self.assertEqual(len(bus._redis.streams), 1)


if __name__ == "__main__":
    unittest.main()
