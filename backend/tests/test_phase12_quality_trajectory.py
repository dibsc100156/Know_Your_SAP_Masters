import unittest

from app.core.harness_runs import HarnessRun, HarnessRuns
from app.core.quality_evaluator import QualityEvaluator


class FakePipeline:
    def __init__(self, redis_client):
        self.redis = redis_client

    def hset(self, *args, **kwargs):
        self.redis.hset(*args, **kwargs)
        return self

    def expire(self, *args, **kwargs):
        return self

    def sadd(self, key, value):
        self.redis.sadd(key, value)
        return self

    def zadd(self, key, mapping):
        self.redis.zadd(key, mapping)
        return self

    def execute(self):
        return True


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.sets = {}
        self.sorted_sets = {}

    def pipeline(self):
        return FakePipeline(self)

    def hset(self, key, field=None, value=None, mapping=None):
        self.hashes.setdefault(key, {})
        if mapping is not None:
            for k, v in mapping.items():
                self.hashes[key][k] = v
        else:
            self.hashes[key][field] = value

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def exists(self, key):
        return key in self.hashes

    def expire(self, key, ttl):
        return True

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)


class Phase12QualityTrajectoryTests(unittest.TestCase):
    def test_quality_evaluator_scores_from_trajectory_log(self):
        run = HarnessRun(
            run_id="run-1",
            query="vendor payment terms",
            user_role="AP_CLERK",
            status="completed",
            swarm_routing="monolithic",
            confidence_score=0.84,
            trajectory_log=[
                {"step": "phase_0_meta_path", "decision": "miss", "reasoning": "no template", "metadata": {}},
                {"step": "phase_1_schema_rag", "decision": "success", "reasoning": "tables found", "metadata": {}},
                {"step": "phase_2_sql_pattern", "decision": "success", "reasoning": "pattern found", "metadata": {}},
                {"step": "phase_8_finalization", "decision": "success", "reasoning": "answer assembled", "metadata": {}},
            ],
        )

        metrics = QualityEvaluator.evaluate_run(run)

        self.assertGreater(metrics["correctness_score"], 0.7)
        self.assertGreater(metrics["trajectory_adherence"], 0.5)
        self.assertEqual(metrics["trajectory_event_count"], 4.0)

    def test_harness_run_persists_trajectory_and_quality_metrics(self):
        hr = HarnessRuns(FakeRedis())
        run = hr.start_run(
            run_id="run-2",
            query="vendor payment terms",
            user_role="AP_CLERK",
            swarm_routing="monolithic",
        )

        hr.add_trajectory_event(run.run_id, "phase_1_schema_rag", "success", "schema lookup succeeded", {"tables": ["LFA1"]})
        hr.add_trajectory_event(run.run_id, "phase_2_sql_pattern", "success", "pattern lookup succeeded", {"patterns": 1})
        hr.set_quality_metrics(run.run_id, {
            "correctness_score": 0.88,
            "trajectory_adherence": 0.91,
            "phase_coverage": 0.5,
            "trajectory_event_count": 2.0,
        })

        loaded = hr.get_run(run.run_id)

        self.assertEqual(loaded.trajectory_event_count, 2)
        self.assertEqual(len(loaded.trajectory_log), 2)
        self.assertEqual(loaded.quality_metrics["correctness_score"], 0.88)
        self.assertEqual(loaded.quality_metrics["trajectory_adherence"], 0.91)


if __name__ == "__main__":
    unittest.main()
