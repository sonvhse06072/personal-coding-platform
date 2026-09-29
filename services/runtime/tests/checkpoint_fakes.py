"""In-memory transition contract for orchestrator tests; SQL atomicity is tested on PostgreSQL."""
from copy import deepcopy

from app.work_order_checkpoints import ready_work_order_ids


class CheckpointTransitions:
    def release_launch(self, plan_id, work_order_id, job_id):
        return True

    def transition_work_order(self, *, expected, checkpoint_key, kind, evidence, **fields):
        history = getattr(self, "checkpoint_history", [])
        self.checkpoint_history = history
        existing = next((row for row in history if row["checkpoint_key"] == checkpoint_key), None)
        if existing:
            assert existing["kind"] == kind and existing["state"] == fields["state"]
            return deepcopy(existing)
        rows = self.work_orders(expected["plan_id"])
        current = next(row for row in rows if row["work_order_id"] == expected["work_order_id"])
        assert current["state"] == expected["state"]
        states = {row["work_order_id"]: row["state"] for row in rows if row.get("lifecycle", "active") == "active"}
        states[expected["work_order_id"]] = fields["state"]
        plan = getattr(self, "plan", {}).get("plan", {})
        definitions = {item["id"]: item for item in plan.get("work_orders", [])}
        dependencies = definitions.get(expected["work_order_id"], {}).get("dependencies", [])
        checkpoint = {
            "checkpoint_key": checkpoint_key, "kind": kind, "state": fields["state"],
            "plan_id": expected["plan_id"], "work_order_id": expected["work_order_id"],
            "job_id": fields.get("job_id", expected.get("job_id")),
            "evidence": {**deepcopy(evidence), "dependencies": {dep: states.get(dep) for dep in dependencies},
                         "next": ready_work_order_ids(plan, states)},
        }
        self.update_work_order(expected["plan_id"], expected["work_order_id"], **fields)
        history.append(checkpoint)
        return deepcopy(checkpoint)
