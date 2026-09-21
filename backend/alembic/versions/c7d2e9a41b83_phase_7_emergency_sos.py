"""Phase 7: emergency & SOS expansion

Revision ID: c7d2e9a41b83
Revises: 3f8a91c4d7e2
Create Date: 2026-09-20

Additive only: nullable columns on emergency_events / emergency_contacts,
four new tables, partial unique indexes for active-SOS dedup and
idempotency. No Phase 1-6 data is altered or removed.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'c7d2e9a41b83'
down_revision = '3f8a91c4d7e2'
branch_labels = None
depends_on = None

ACTIVE_SOS_SQL = (
    "status IN ('REQUESTED','ALERTING','CONTACTING','ACTIVE','HANDOFF_PENDING')"
)


def upgrade() -> None:
    # ---- emergency_events: new nullable columns ----
    op.add_column('emergency_events', sa.Column(
        'emergency_type', sa.String(length=20), nullable=False, server_default='MEDICAL'))
    op.add_column('emergency_events', sa.Column(
        'initiated_by_user_id', sa.String(length=36), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'idempotency_key', sa.String(length=64), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'correlation_id', sa.String(length=36), nullable=False, server_default=''))
    op.add_column('emergency_events', sa.Column(
        'location_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'network_status', sa.String(length=20), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'device_platform', sa.String(length=40), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'cancel_reason', sa.String(length=20), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'resolved_by_user_id', sa.String(length=36), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'initiated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('emergency_events', sa.Column(
        'resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        'fk_emergency_event_initiator', 'emergency_events',
        'users', ['initiated_by_user_id'], ['id'])
    op.create_foreign_key(
        'fk_emergency_event_resolver', 'emergency_events',
        'users', ['resolved_by_user_id'], ['id'])
    op.create_index('ix_emergency_events_created_at', 'emergency_events', ['created_at'])
    op.create_index(
        'uq_patient_active_sos', 'emergency_events', ['user_id'],
        unique=True, postgresql_where=ACTIVE_SOS_SQL)
    op.create_index(
        'uq_sos_idempotency', 'emergency_events', ['user_id', 'idempotency_key'],
        unique=True, postgresql_where='idempotency_key IS NOT NULL')

    # ---- emergency_contacts: priority / active / preferences ----
    op.add_column('emergency_contacts', sa.Column(
        'priority', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('emergency_contacts', sa.Column(
        'active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('emergency_contacts', sa.Column(
        'notification_preferences', sa.String(length=120), nullable=False,
        server_default='IN_APP'))
    op.add_column('emergency_contacts', sa.Column(
        'updated_at', sa.DateTime(timezone=True), nullable=False,
        server_default=sa.func.now()))

    # ---- emergency_profiles ----
    op.create_table(
        'emergency_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('blood_group', sa.String(length=8), nullable=True),
        sa.Column('allergies', sa.Text(), nullable=False, server_default=''),
        sa.Column('critical_conditions', sa.Text(), nullable=False, server_default=''),
        sa.Column('critical_medications', sa.Text(), nullable=False, server_default=''),
        sa.Column('emergency_notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('preferred_hospital_id', sa.String(length=36), nullable=True),
        sa.Column('organ_donor_status', sa.String(length=20), nullable=True),
        sa.Column('accessibility_needs', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_emergency_profile_user'),
        sa.ForeignKeyConstraint(
            ['preferred_hospital_id'], ['hospitals.id'],
            name='fk_emergency_profile_hospital'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_emergency_profile_user'),
    )

    # ---- emergency_handoffs ----
    op.create_table(
        'emergency_handoffs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('emergency_event_id', sa.String(length=36), nullable=False),
        sa.Column('hospital_id', sa.String(length=36), nullable=False),
        sa.Column('requested_by_user_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False,
                  server_default='HANDOFF_REQUESTED'),
        sa.Column('notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['emergency_event_id'], ['emergency_events.id'],
            name='fk_emergency_handoff_event'),
        sa.ForeignKeyConstraint(
            ['hospital_id'], ['hospitals.id'], name='fk_emergency_handoff_hospital'),
        sa.ForeignKeyConstraint(
            ['requested_by_user_id'], ['users.id'], name='fk_emergency_handoff_requester'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_emergency_handoff_event', 'emergency_handoffs', ['emergency_event_id'])
    op.create_index('ix_emergency_handoff_hospital', 'emergency_handoffs', ['hospital_id'])
    op.create_index('ix_emergency_handoff_status', 'emergency_handoffs', ['status'])

    # ---- emergency_notifications ----
    op.create_table(
        'emergency_notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('emergency_event_id', sa.String(length=36), nullable=True),
        sa.Column('contact_id', sa.String(length=36), nullable=True),
        sa.Column('recipient_user_id', sa.String(length=36), nullable=True),
        sa.Column('recipient_phone', sa.String(length=20), nullable=True),
        sa.Column('channel', sa.String(length=10), nullable=False, server_default='IN_APP'),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='QUEUED'),
        sa.Column('provider_name', sa.String(length=60), nullable=True),
        sa.Column('error_detail', sa.String(length=200), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['emergency_event_id'], ['emergency_events.id'],
            name='fk_emergency_notification_event'),
        sa.ForeignKeyConstraint(
            ['contact_id'], ['emergency_contacts.id'],
            name='fk_emergency_notification_contact'),
        sa.ForeignKeyConstraint(
            ['recipient_user_id'], ['users.id'], name='fk_emergency_notification_recipient'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_emergency_notification_event', 'emergency_notifications', ['emergency_event_id'])
    op.create_index(
        'ix_emergency_notification_recipient', 'emergency_notifications', ['recipient_user_id'])
    op.create_index(
        'ix_emergency_notification_status', 'emergency_notifications', ['status'])

    # ---- emergency_provider_events ----
    op.create_table(
        'emergency_provider_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('emergency_event_id', sa.String(length=36), nullable=False),
        sa.Column('provider_name', sa.String(length=60), nullable=False),
        sa.Column('action', sa.String(length=24), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False, server_default=''),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['emergency_event_id'], ['emergency_events.id'],
            name='fk_emergency_provider_event'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_emergency_provider_event', 'emergency_provider_events', ['emergency_event_id'])


def downgrade() -> None:
    op.drop_table('emergency_provider_events')
    op.drop_table('emergency_notifications')
    op.drop_table('emergency_handoffs')
    op.drop_table('emergency_profiles')
    op.drop_column('emergency_contacts', 'updated_at')
    op.drop_column('emergency_contacts', 'notification_preferences')
    op.drop_column('emergency_contacts', 'active')
    op.drop_column('emergency_contacts', 'priority')
    op.drop_index('uq_sos_idempotency', table_name='emergency_events')
    op.drop_index('uq_patient_active_sos', table_name='emergency_events')
    op.drop_index('ix_emergency_events_created_at', table_name='emergency_events')
    op.drop_constraint('fk_emergency_event_resolver', 'emergency_events', type_='foreignkey')
    op.drop_constraint('fk_emergency_event_initiator', 'emergency_events', type_='foreignkey')
    for col in (
        'resolved_at', 'cancelled_at', 'initiated_at', 'resolved_by_user_id',
        'cancel_reason', 'device_platform', 'network_status', 'location_timestamp',
        'correlation_id', 'idempotency_key', 'initiated_by_user_id', 'emergency_type',
    ):
        op.drop_column('emergency_events', col)
