"""Durable model invocation and tool call records.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE model_invocations (
        provider VARCHAR(200) NOT NULL,
        model VARCHAR(200) NOT NULL,
        id UUID NOT NULL,
        run_id UUID NOT NULL,
        status VARCHAR(16) DEFAULT 'REQUESTED' NOT NULL,
        requested_event_sequence INTEGER NOT NULL,
        completed_event_sequence INTEGER,
        step_number INTEGER,
        request JSONB NOT NULL,
        result JSONB,
        error_code VARCHAR(64),
        requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE,
        CONSTRAINT pk_model_invocations PRIMARY KEY (id),
        CONSTRAINT uq_model_invocations_run_id UNIQUE (run_id, id),
        CONSTRAINT uq_model_invocations_request_event UNIQUE (run_id, requested_event_sequence),
        CONSTRAINT uq_model_invocations_completion_event UNIQUE (run_id,
        completed_event_sequence),
        CONSTRAINT uq_model_invocations_step UNIQUE (run_id, step_number),
        CONSTRAINT fk_model_invocations_run_id_execution_events FOREIGN KEY(run_id,
        requested_event_sequence) REFERENCES execution_events (run_id, sequence) ON DELETE
        RESTRICT,
        CONSTRAINT fk_model_invocations_completion_event FOREIGN KEY(run_id,
        completed_event_sequence) REFERENCES execution_events (run_id, sequence) ON DELETE
        RESTRICT,
        CONSTRAINT fk_model_invocations_run_id_checkpoints FOREIGN KEY(run_id, step_number)
        REFERENCES checkpoints (run_id, step_number) ON DELETE RESTRICT,
        CONSTRAINT ck_model_invocations_request_object CHECK (jsonb_typeof(request) = 'object'),
        CONSTRAINT ck_model_invocations_result_object CHECK (result IS NULL OR
        jsonb_typeof(result) = 'object'),
        CONSTRAINT ck_model_invocations_error_code CHECK (error_code IS NULL OR error_code ~
        '^[a-z][a-z0-9_]{0,63}$'),
        CONSTRAINT ck_model_invocations_outcome CHECK ((status = 'REQUESTED' AND result IS NULL
        AND error_code IS NULL AND completed_at IS NULL AND completed_event_sequence IS NULL AND
        step_number IS NULL) OR (status IN ('SUCCEEDED', 'FAILED') AND completed_at IS NOT NULL
        AND completed_event_sequence IS NOT NULL AND step_number IS NOT NULL AND ((status =
        'SUCCEEDED' AND result IS NOT NULL AND error_code IS NULL) OR (status = 'FAILED' AND
        result IS NULL AND error_code IS NOT NULL)))),
        CONSTRAINT ck_model_invocations_ordered_time CHECK (completed_at IS NULL OR completed_at
        >= requested_at),
        CONSTRAINT ck_model_invocations_ordered_events CHECK (completed_event_sequence IS NULL
        OR completed_event_sequence > requested_event_sequence),
        CONSTRAINT ck_model_invocations_provider CHECK (length(trim(provider)) > 0 AND provider
        !~ '[[:cntrl:]]'),
        CONSTRAINT ck_model_invocations_model CHECK (length(trim(model)) > 0 AND model !~
        '[[:cntrl:]]'),
        CONSTRAINT fk_model_invocations_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id) ON
        DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE tool_calls (
        tool_name VARCHAR(200) NOT NULL,
        model_invocation_id UUID,
        id UUID NOT NULL,
        run_id UUID NOT NULL,
        status VARCHAR(16) DEFAULT 'REQUESTED' NOT NULL,
        requested_event_sequence INTEGER NOT NULL,
        completed_event_sequence INTEGER,
        step_number INTEGER,
        request JSONB NOT NULL,
        result JSONB,
        error_code VARCHAR(64),
        requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE,
        CONSTRAINT pk_tool_calls PRIMARY KEY (id),
        CONSTRAINT uq_tool_calls_run_id UNIQUE (run_id, id),
        CONSTRAINT uq_tool_calls_request_event UNIQUE (run_id, requested_event_sequence),
        CONSTRAINT uq_tool_calls_completion_event UNIQUE (run_id, completed_event_sequence),
        CONSTRAINT uq_tool_calls_step UNIQUE (run_id, step_number),
        CONSTRAINT fk_tool_calls_run_id_execution_events FOREIGN KEY(run_id,
        requested_event_sequence) REFERENCES execution_events (run_id, sequence) ON DELETE
        RESTRICT,
        CONSTRAINT fk_tool_calls_completion_event FOREIGN KEY(run_id, completed_event_sequence)
        REFERENCES execution_events (run_id, sequence) ON DELETE RESTRICT,
        CONSTRAINT fk_tool_calls_run_id_checkpoints FOREIGN KEY(run_id, step_number) REFERENCES
        checkpoints (run_id, step_number) ON DELETE RESTRICT,
        CONSTRAINT ck_tool_calls_request_object CHECK (jsonb_typeof(request) = 'object'),
        CONSTRAINT ck_tool_calls_result_object CHECK (result IS NULL OR jsonb_typeof(result) =
        'object'),
        CONSTRAINT ck_tool_calls_error_code CHECK (error_code IS NULL OR error_code ~
        '^[a-z][a-z0-9_]{0,63}$'),
        CONSTRAINT ck_tool_calls_outcome CHECK ((status = 'REQUESTED' AND result IS NULL AND
        error_code IS NULL AND completed_at IS NULL AND completed_event_sequence IS NULL AND
        step_number IS NULL) OR (status IN ('SUCCEEDED', 'FAILED') AND completed_at IS NOT NULL
        AND completed_event_sequence IS NOT NULL AND step_number IS NOT NULL AND ((status =
        'SUCCEEDED' AND result IS NOT NULL AND error_code IS NULL) OR (status = 'FAILED' AND
        result IS NULL AND error_code IS NOT NULL)))),
        CONSTRAINT ck_tool_calls_ordered_time CHECK (completed_at IS NULL OR completed_at >=
        requested_at),
        CONSTRAINT ck_tool_calls_ordered_events CHECK (completed_event_sequence IS NULL OR
        completed_event_sequence > requested_event_sequence),
        CONSTRAINT fk_tool_calls_run_id_model_invocations FOREIGN KEY(run_id,
        model_invocation_id) REFERENCES model_invocations (run_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_tool_calls_tool_name CHECK (length(trim(tool_name)) > 0 AND tool_name !~
        '[[:cntrl:]]'),
        CONSTRAINT fk_tool_calls_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE
        RESTRICT
        )
    """)
    op.execute("""
        CREATE FUNCTION guard_invocation_record() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE current_run runs%ROWTYPE;
                linked_event execution_events%ROWTYPE;
                boundary checkpoints%ROWTYPE;
                recorded_step run_steps%ROWTYPE;
                event_prefix text;
                expected_kind text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Invocation records cannot be deleted' USING ERRCODE = '23514';
            END IF;
            SELECT * INTO current_run FROM runs WHERE id=NEW.run_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Run not found' USING ERRCODE = '23503';
            END IF;
            IF current_run.status != 'RUNNING' THEN
                RAISE EXCEPTION 'Invocation writes require a running run' USING ERRCODE = '23514';
            END IF;
            event_prefix := CASE WHEN TG_TABLE_NAME='model_invocations'
                THEN 'model' ELSE 'tool' END;
            IF TG_OP = 'INSERT' THEN
                IF NEW.status != 'REQUESTED' THEN
                    RAISE EXCEPTION 'Invocations must begin requested' USING ERRCODE = '23514';
                END IF;
                SELECT * INTO linked_event FROM execution_events
                    WHERE run_id=NEW.run_id AND sequence=NEW.requested_event_sequence;
                expected_kind := event_prefix || '.requested';
            ELSE
                IF OLD.status != 'REQUESTED' OR NEW.status NOT IN ('SUCCEEDED','FAILED') THEN
                    RAISE EXCEPTION 'Invocation outcome is already recorded or invalid'
                        USING ERRCODE = '23514';
                END IF;
                IF (to_jsonb(NEW) - ARRAY['status','result','error_code','completed_at',
                       'completed_event_sequence','step_number']) IS DISTINCT FROM
                   (to_jsonb(OLD) - ARRAY['status','result','error_code','completed_at',
                       'completed_event_sequence','step_number']) THEN
                    RAISE EXCEPTION 'Invocation request is immutable' USING ERRCODE = '23514';
                END IF;
                SELECT * INTO linked_event FROM execution_events
                    WHERE run_id=NEW.run_id AND sequence=NEW.completed_event_sequence;
                expected_kind := event_prefix || CASE WHEN NEW.status='SUCCEEDED'
                    THEN '.completed' ELSE '.failed' END;
            END IF;
            IF linked_event.sequence IS NULL OR linked_event.kind != expected_kind
               OR linked_event.payload->>'record_id' IS DISTINCT FROM NEW.id::text
               OR linked_event.run_revision != current_run.revision
               OR linked_event.step_number IS NOT NULL THEN
                RAISE EXCEPTION 'Invalid invocation event correlation' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'INSERT' THEN
                NEW.requested_at := linked_event.created_at;
                IF TG_TABLE_NAME = 'tool_calls' THEN
                    IF NEW.model_invocation_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM model_invocations WHERE id=NEW.model_invocation_id
                            AND run_id=NEW.run_id AND status='SUCCEEDED'
                    ) THEN
                        RAISE EXCEPTION 'Invalid source model invocation' USING ERRCODE = '23514';
                    END IF;
                END IF;
            ELSE
                SELECT * INTO boundary FROM checkpoints
                    WHERE run_id=NEW.run_id AND step_number=NEW.step_number;
                SELECT * INTO recorded_step FROM run_steps
                    WHERE run_id=NEW.run_id AND number=NEW.step_number;
                IF boundary.event_sequence IS NULL OR recorded_step.number IS NULL
                   OR boundary.event_sequence <= NEW.completed_event_sequence
                   OR boundary.run_revision != current_run.revision
                   OR recorded_step.kind != expected_kind
                   OR recorded_step.details->>'record_id' IS DISTINCT FROM NEW.id::text THEN
                    RAISE EXCEPTION 'Invalid invocation completion boundary'
                        USING ERRCODE = '23514';
                END IF;
                NEW.completed_at := linked_event.created_at;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    for table in ("model_invocations", "tool_calls"):
        op.execute(f"""
            CREATE TRIGGER valid_invocation_record BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION guard_invocation_record()
        """)


def downgrade() -> None:
    op.drop_table("tool_calls")
    op.drop_table("model_invocations")
    op.execute("DROP FUNCTION guard_invocation_record()")
