"""Ordered execution history and checkpoint boundaries.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Prevent a lifecycle write slipping between baseline capture and trigger installation.
    op.execute("LOCK TABLE runs IN SHARE ROW EXCLUSIVE MODE")
    op.execute("""
        CREATE TABLE run_steps (
            run_id UUID NOT NULL,
            number INTEGER NOT NULL,
            kind VARCHAR(100) NOT NULL,
            details JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
            CONSTRAINT pk_run_steps PRIMARY KEY (run_id, number),
            CONSTRAINT ck_run_steps_positive_number CHECK (number > 0),
            CONSTRAINT ck_run_steps_valid_kind CHECK (kind ~ '^[a-z][a-z0-9_.]{0,99}$'),
            CONSTRAINT ck_run_steps_details_object CHECK (jsonb_typeof(details) = 'object'),
            CONSTRAINT fk_run_steps_run_id_runs
                FOREIGN KEY(run_id)
                REFERENCES runs (id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE execution_events (
            run_id UUID NOT NULL,
            sequence INTEGER DEFAULT '0' NOT NULL,
            kind VARCHAR(100) NOT NULL,
            run_revision INTEGER NOT NULL,
            step_number INTEGER,
            payload JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
            CONSTRAINT pk_execution_events PRIMARY KEY (run_id, sequence),
            CONSTRAINT fk_execution_events_run_id_run_steps
                FOREIGN KEY(run_id, step_number)
                REFERENCES run_steps (run_id, number) ON DELETE RESTRICT,
            CONSTRAINT ck_execution_events_positive_sequence CHECK (sequence > 0),
            CONSTRAINT ck_execution_events_nonnegative_revision CHECK (run_revision >= 0),
            CONSTRAINT ck_execution_events_payload_object CHECK (jsonb_typeof(payload) = 'object'),
            CONSTRAINT fk_execution_events_run_id_runs
                FOREIGN KEY(run_id)
                REFERENCES runs (id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE checkpoints (
            run_id UUID NOT NULL,
            event_sequence INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            run_revision INTEGER NOT NULL,
            run_status VARCHAR(32) NOT NULL,
            schema_version INTEGER NOT NULL,
            state JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
            CONSTRAINT pk_checkpoints PRIMARY KEY (run_id, event_sequence),
            CONSTRAINT fk_checkpoints_run_id_execution_events
                FOREIGN KEY(run_id, event_sequence)
                REFERENCES execution_events (run_id, sequence) ON DELETE RESTRICT,
            CONSTRAINT fk_checkpoints_run_id_run_steps
                FOREIGN KEY(run_id, step_number)
                REFERENCES run_steps (run_id, number) ON DELETE RESTRICT,
            CONSTRAINT uq_checkpoints_run_step UNIQUE (run_id, step_number),
            CONSTRAINT ck_checkpoints_positive_schema_version CHECK (schema_version > 0),
            CONSTRAINT ck_checkpoints_nonnegative_revision CHECK (run_revision >= 0),
            CONSTRAINT ck_checkpoints_running_boundary CHECK (run_status = 'RUNNING'),
            CONSTRAINT ck_checkpoints_state_object CHECK (jsonb_typeof(state) = 'object')
        )
    """)
    op.execute("""
        CREATE FUNCTION reject_history_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Execution history is immutable' USING ERRCODE = '23514';
        END;
        $$
    """)
    for table in ("run_steps", "execution_events", "checkpoints"):
        op.execute(f"""
            CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_history_mutation()
        """)
    op.execute("""
        CREATE FUNCTION order_execution_event() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE current_revision integer;
        BEGIN
            SELECT revision INTO current_revision FROM runs WHERE id=NEW.run_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Run not found' USING ERRCODE = '23503';
            END IF;
            IF NEW.sequence IS DISTINCT FROM 0 OR NEW.run_revision != current_revision THEN
                RAISE EXCEPTION 'Invalid event sequence or revision' USING ERRCODE = '23514';
            END IF;
            SELECT COALESCE(MAX(sequence), 0) + 1 INTO NEW.sequence
                FROM execution_events WHERE run_id=NEW.run_id;
            NEW.created_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER ordered_event BEFORE INSERT ON execution_events
        FOR EACH ROW EXECUTE FUNCTION order_execution_event()
    """)
    op.execute("""
        CREATE FUNCTION guard_execution_boundary() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE current_run runs%ROWTYPE;
                linked_event execution_events%ROWTYPE;
                next_step integer;
        BEGIN
            SELECT * INTO current_run FROM runs WHERE id=NEW.run_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Run not found' USING ERRCODE = '23503';
            END IF;
            IF current_run.status != 'RUNNING' THEN
                RAISE EXCEPTION 'Execution boundaries require a running run'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_TABLE_NAME = 'run_steps' THEN
                SELECT COALESCE(MAX(number), 0) + 1 INTO next_step
                    FROM run_steps WHERE run_id=NEW.run_id;
                IF NEW.number != next_step THEN
                    RAISE EXCEPTION 'Invalid step number' USING ERRCODE = '23514';
                END IF;
            ELSE
                SELECT * INTO linked_event FROM execution_events
                    WHERE run_id=NEW.run_id AND sequence=NEW.event_sequence;
                IF NOT FOUND OR linked_event.kind != 'checkpoint.created'
                   OR linked_event.step_number IS DISTINCT FROM NEW.step_number
                   OR linked_event.run_revision != NEW.run_revision
                   OR NEW.run_revision != current_run.revision
                   OR NEW.run_status != current_run.status THEN
                    RAISE EXCEPTION 'Invalid checkpoint boundary' USING ERRCODE = '23514';
                END IF;
            END IF;
            NEW.created_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    for table in ("run_steps", "checkpoints"):
        op.execute(f"""
            CREATE TRIGGER valid_boundary BEFORE INSERT ON {table}
            FOR EACH ROW EXECUTE FUNCTION guard_execution_boundary()
        """)
    # Phase 1A retained only the latest lifecycle state, not every historical edge.
    op.execute("""
        INSERT INTO execution_events (run_id, kind, run_revision, payload)
        SELECT id, 'run.snapshot', revision,
            jsonb_build_object('status', status, 'revision', revision,
                'agent_version_id', agent_version_id, 'history_complete', false,
                'created_at', created_at, 'state_changed_at', state_changed_at,
                'started_at', started_at, 'finished_at', finished_at)
        FROM runs
    """)
    op.execute("""
        CREATE FUNCTION record_run_lifecycle() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                INSERT INTO execution_events (run_id, kind, run_revision, payload)
                VALUES (NEW.id, 'run.created', NEW.revision,
                    jsonb_build_object('status', NEW.status, 'revision', NEW.revision,
                        'agent_version_id', NEW.agent_version_id,
                        'at', NEW.created_at));
            ELSE
                INSERT INTO execution_events (run_id, kind, run_revision, payload)
                VALUES (NEW.id, 'run.transitioned', NEW.revision,
                    jsonb_build_object('from_status', OLD.status, 'status', NEW.status,
                        'revision', NEW.revision, 'at', NEW.state_changed_at));
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER run_lifecycle_event AFTER INSERT OR UPDATE ON runs
        FOR EACH ROW EXECUTE FUNCTION record_run_lifecycle()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER run_lifecycle_event ON runs")
    op.execute("DROP FUNCTION record_run_lifecycle()")
    op.drop_table("checkpoints")
    op.drop_table("execution_events")
    op.drop_table("run_steps")
    op.execute("DROP FUNCTION guard_execution_boundary()")
    op.execute("DROP FUNCTION order_execution_event()")
    op.execute("DROP FUNCTION reject_history_mutation()")
